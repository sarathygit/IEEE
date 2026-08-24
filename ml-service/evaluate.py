"""
FinGuard-AI :: IEEE Evaluation Suite
====================================

Three experiments on the production feature pipeline, all fully seeded and
reproducible:

  1. SYNTHETIC FRAUD INJECTION - the public dataset's fraud_flag labels are
     statistical noise (ROC-AUC ~= 0.48), so supervised evaluation against
     them is meaningless. Instead we inject four synthetic fraud archetypes
     into clean held-out traffic and measure detection against those.
     Archetype B (velocity) is a DELIBERATE negative control: the deployed
     model scores transactions independently and is expected to miss it.

  2. ABLATION STUDY - retrain the forest on three nested feature sets
     (typed inputs -> +telemetry -> +server enrichment) to quantify what
     each enrichment layer contributes.

  3. BASELINE COMPARISON - same task, same features, against static rules,
     Local Outlier Factor, and One-Class SVM.

Run (from ml-service/, venv active):
    python evaluate.py --input ../upi_transactions_2024.csv

Outputs human-readable tables to stdout and machine-readable JSON to
evaluation_results.json.
"""

import argparse
import json
import logging
import time

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import OneClassSVM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("finguard.eval")

SEED = 42
PRODUCTION_THRESHOLD = 0.85
CALIBRATION_PERCENTILE = 99.95

NUMERIC = ["amount (INR)", "hour_of_day", "is_weekend"]
CATEGORICAL = ["transaction type", "merchant_category", "sender_age_group",
               "receiver_age_group", "sender_state", "sender_bank",
               "receiver_bank", "device_type", "network_type", "day_of_week"]
ALL_FEATURES = NUMERIC + CATEGORICAL

# Nested feature sets for the ablation study. Layer definitions mirror the
# system's real enrichment pipeline (form -> telemetry.js -> switch).
ABLATION_LAYERS = {
    "L1 form-only": ["amount (INR)", "transaction type", "merchant_category"],
    "L2 +telemetry": ["amount (INR)", "transaction type", "merchant_category",
                       "device_type", "network_type"],
    "L3 +server enrichment": ALL_FEATURES,
}

N_PER_ARCHETYPE = 100


# --------------------------------------------------------------------------
# Model plumbing (identical conventions to train.py)
# --------------------------------------------------------------------------

def build_preprocessor(feature_cols):
    num = [c for c in feature_cols if c in NUMERIC]
    cat = [c for c in feature_cols if c in CATEGORICAL]
    return ColumnTransformer([
        ("num", StandardScaler(), num),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
    ])


def fit_forest(X_train, feature_cols):
    pre = build_preprocessor(feature_cols)
    Xt = pre.fit_transform(X_train[feature_cols])
    model = IsolationForest(n_estimators=200, contamination=0.002,
                            random_state=SEED, n_jobs=-1).fit(Xt)
    raw = -model.decision_function(Xt)
    smin = float(raw.min())
    smax = float(np.percentile(raw, CALIBRATION_PERCENTILE))
    return {"pre": pre, "model": model, "smin": smin, "smax": smax,
            "cols": feature_cols}


def calibrated_scores(bundle, X):
    raw = -bundle["model"].decision_function(
        bundle["pre"].transform(X[bundle["cols"]]))
    return np.clip((raw - bundle["smin"]) / (bundle["smax"] - bundle["smin"]), 0.0, 1.0)


# --------------------------------------------------------------------------
# Synthetic fraud injection
# --------------------------------------------------------------------------

def inject_synthetics(clean_test, rng):
    """Perturbation-based injection: sample real clean rows, then overwrite
    the fields that define each archetype. Non-archetype fields keep their
    realistic sampled values, so synthetics are not trivially separable."""

    def sample_base(n):
        return clean_test.sample(n=n, random_state=rng.integers(1 << 31)).copy()

    # A - off-hour high-value drain: large amount, dead of night, web origin.
    a = sample_base(N_PER_ARCHETYPE)
    a["amount (INR)"] = rng.uniform(25_000, 60_000, len(a)).round(2)
    a["hour_of_day"] = rng.choice([1, 2, 3, 4], len(a))
    a["transaction type"] = "P2P"
    a["device_type"] = "Web"

    # B - velocity spike (NEGATIVE CONTROL): each transfer individually
    # normal (modest amount, business hours, common device). A velocity
    # attack is 10+ of these in minutes - information the per-transaction
    # model does not receive. Expected recall ~ 0.
    b = sample_base(N_PER_ARCHETYPE)
    b["amount (INR)"] = rng.uniform(2_000, 6_000, len(b)).round(2)
    b["hour_of_day"] = rng.choice([13, 14, 15, 16], len(b))
    b["transaction type"] = "P2P"
    b["device_type"] = "Android"
    b["network_type"] = "4G"

    # C - MCC/category anomaly: implausibly large amount for an everyday
    # category, otherwise normal context.
    c = sample_base(N_PER_ARCHETYPE)
    c["amount (INR)"] = rng.uniform(50_000, 100_000, len(c)).round(2)
    c["merchant_category"] = "Grocery"
    c["transaction type"] = "P2M"
    c["hour_of_day"] = rng.choice(range(10, 21), len(c))

    # D - anomalous context, modest amount: odd hour + web + wifi. Tests
    # whether context alone (without a large amount) can trip the model.
    d = sample_base(N_PER_ARCHETYPE)
    d["amount (INR)"] = rng.uniform(2_000, 9_000, len(d)).round(2)
    d["hour_of_day"] = rng.choice([0, 1, 2, 3, 4], len(d))
    d["transaction type"] = "P2P"
    d["device_type"] = "Web"
    d["network_type"] = "WiFi"

    frames = {"A off-hour drain": a, "B velocity (neg-ctrl)": b,
              "C category anomaly": c, "D context anomaly": d}
    for name, frame in frames.items():
        frame["archetype"] = name
    return pd.concat(frames.values(), ignore_index=True)


# --------------------------------------------------------------------------
# Metrics helpers
# --------------------------------------------------------------------------

def binary_metrics(y_true, y_flag):
    y_true, y_flag = np.asarray(y_true), np.asarray(y_flag)
    tp = int(((y_true == 1) & (y_flag == 1)).sum())
    fp = int(((y_true == 0) & (y_flag == 1)).sum())
    fn = int(((y_true == 1) & (y_flag == 0)).sum())
    tn = int(((y_true == 0) & (y_flag == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": precision, "recall": recall, "f1": f1, "fpr": fpr}


def recall_at_fpr(y_true, scores, target_fpr=0.01):
    """Threshold each scorer at the SAME false-positive budget so scorers
    with incomparable score scales can be compared fairly."""
    clean = scores[np.asarray(y_true) == 0]
    thr = float(np.quantile(clean, 1.0 - target_fpr))
    flags = (scores >= thr).astype(int)
    m = binary_metrics(y_true, flags)
    m["threshold"] = thr
    return m


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="../upi_transactions_2024.csv")
    parser.add_argument("--output", default="evaluation_results.json")
    args = parser.parse_args()

    rng = np.random.default_rng(SEED)
    results = {}

    df = pd.read_csv(args.input)
    X = df[ALL_FEATURES].copy()
    X_train, X_test = train_test_split(X, test_size=0.2, random_state=SEED)
    log.info("Train %d rows | clean test %d rows", len(X_train), len(X_test))

    synth = inject_synthetics(X_test, rng)
    log.info("Injected %d synthetic frauds (4 x %d)", len(synth), N_PER_ARCHETYPE)

    y_true = np.concatenate([np.zeros(len(X_test)), np.ones(len(synth))])
    X_eval = pd.concat([X_test, synth[ALL_FEATURES]], ignore_index=True)

    # ---- Experiment 1: production model vs synthetic frauds --------------
    log.info("=== Experiment 1: synthetic fraud injection ===")
    t0 = time.time()
    prod = fit_forest(X_train, ALL_FEATURES)
    log.info("Production-config forest fitted in %.1fs", time.time() - t0)

    scores = calibrated_scores(prod, X_eval)
    flags = (scores >= PRODUCTION_THRESHOLD).astype(int)

    overall = binary_metrics(y_true, flags)
    overall["roc_auc"] = float(roc_auc_score(y_true, scores))
    results["injection_overall"] = overall

    per_arch = {}
    synth_scores = scores[len(X_test):]
    for name in synth["archetype"].unique():
        mask = (synth["archetype"] == name).to_numpy()
        s = synth_scores[mask]
        per_arch[name] = {
            "n": int(mask.sum()),
            "mean_score": float(s.mean()),
            "recall_at_085": float((s >= PRODUCTION_THRESHOLD).mean()),
        }
    results["injection_per_archetype"] = per_arch
    results["clean_test_fpr_at_085"] = float(
        (scores[:len(X_test)] >= PRODUCTION_THRESHOLD).mean())

    for name, m in per_arch.items():
        log.info("  %-24s recall@0.85=%.3f mean_score=%.3f",
                 name, m["recall_at_085"], m["mean_score"])
    log.info("  OVERALL  P=%.3f R=%.3f F1=%.3f FPR=%.4f AUC=%.4f",
             overall["precision"], overall["recall"], overall["f1"],
             overall["fpr"], overall["roc_auc"])

    # ---- Experiment 2: ablation over enrichment layers -------------------
    log.info("=== Experiment 2: enrichment-layer ablation ===")
    ablation = {}
    for layer, cols in ABLATION_LAYERS.items():
        t0 = time.time()
        b = fit_forest(X_train, cols)
        s = calibrated_scores(b, X_eval)
        clean_s, synth_s = s[:len(X_test)], s[len(X_test):]
        entry = {
            "n_features_raw": len(cols),
            "roc_auc": float(roc_auc_score(y_true, s)),
            "recall_at_085": float((synth_s >= PRODUCTION_THRESHOLD).mean()),
            "fpr_at_085": float((clean_s >= PRODUCTION_THRESHOLD).mean()),
            "mean_clean": float(clean_s.mean()),
            "mean_synth": float(synth_s.mean()),
            "separation": float(synth_s.mean() - clean_s.mean()),
        }
        # per-archetype recall inside each layer
        entry["per_archetype_recall"] = {
            name: float((synth_s[(synth["archetype"] == name).to_numpy()]
                         >= PRODUCTION_THRESHOLD).mean())
            for name in synth["archetype"].unique()
        }
        ablation[layer] = entry
        log.info("  %-24s AUC=%.4f R@0.85=%.3f FPR=%.4f sep=%.3f (%.1fs)",
                 layer, entry["roc_auc"], entry["recall_at_085"],
                 entry["fpr_at_085"], entry["separation"], time.time() - t0)
    results["ablation"] = ablation

    # ---- Experiment 3: baselines -----------------------------------------
    log.info("=== Experiment 3: baseline comparison ===")
    baselines = {}

    # 3a. static rules: amount > p99(train)  OR  (amount > p95 AND hour <= 5)
    p99 = float(X_train["amount (INR)"].quantile(0.99))
    p95 = float(X_train["amount (INR)"].quantile(0.95))
    rule_flags = ((X_eval["amount (INR)"] > p99) |
                  ((X_eval["amount (INR)"] > p95) & (X_eval["hour_of_day"] <= 5))
                  ).astype(int).to_numpy()
    m = binary_metrics(y_true, rule_flags)
    m["note"] = f"p99={p99:.0f}, p95={p95:.0f}"
    baselines["static rules"] = m
    log.info("  rules       P=%.3f R=%.3f F1=%.3f FPR=%.4f",
             m["precision"], m["recall"], m["f1"], m["fpr"])

    pre_full = build_preprocessor(ALL_FEATURES)
    Xt_train_full = pre_full.fit_transform(X_train[ALL_FEATURES])
    Xt_eval_full = pre_full.transform(X_eval[ALL_FEATURES])

    # 3b. Local Outlier Factor (novelty mode; subsampled train for tractability)
    t0 = time.time()
    sub = rng.choice(Xt_train_full.shape[0], 40_000, replace=False)
    lof = LocalOutlierFactor(n_neighbors=20, novelty=True).fit(Xt_train_full[sub])
    lof_scores = -lof.decision_function(Xt_eval_full)
    m = recall_at_fpr(y_true, lof_scores)
    m["roc_auc"] = float(roc_auc_score(y_true, lof_scores))
    m["train_subsample"] = 40_000
    baselines["LOF"] = m
    log.info("  LOF         AUC=%.4f R@1%%FPR=%.3f (%.1fs)",
             m["roc_auc"], m["recall"], time.time() - t0)

    # 3c. One-Class SVM (RBF; subsampled - O(n^2) kernel)
    t0 = time.time()
    sub = rng.choice(Xt_train_full.shape[0], 15_000, replace=False)
    oc = OneClassSVM(nu=0.002, kernel="rbf", gamma="scale").fit(Xt_train_full[sub])
    oc_scores = -oc.decision_function(Xt_eval_full)
    m = recall_at_fpr(y_true, oc_scores)
    m["roc_auc"] = float(roc_auc_score(y_true, oc_scores))
    m["train_subsample"] = 15_000
    baselines["OC-SVM"] = m
    log.info("  OC-SVM      AUC=%.4f R@1%%FPR=%.3f (%.1fs)",
             m["roc_auc"], m["recall"], time.time() - t0)

    # 3d. Isolation Forest under the same 1% FPR budget (fair comparison)
    m = recall_at_fpr(y_true, scores)
    m["roc_auc"] = overall["roc_auc"]
    baselines["Isolation Forest"] = m
    log.info("  IsoForest   AUC=%.4f R@1%%FPR=%.3f",
             m["roc_auc"], m["recall"])

    results["baselines"] = baselines

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    log.info("Results written to %s", args.output)


if __name__ == "__main__":
    main()
