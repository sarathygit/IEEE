"""Evaluate the hybrid engine against each of its constituent tiers.

Compares, on the same injected evaluation set at a matched false-positive
budget: rules only, Isolation Forest only, LOF only, and the fused hybrid.

Run:  python evaluate_hybrid.py
Writes evaluation_hybrid.json
"""

import json
import logging

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor

from evaluate import (ALL_FEATURES, SEED, build_preprocessor, fit_forest,
                      calibrated_scores, inject_synthetics, binary_metrics)
from hybrid import derive_thresholds, evaluate_rules, fuse, decide

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("finguard.hybrid")

TARGET_FPR = 0.0086   # the deployed model's measured false-positive rate


def calibrate(raw, lo, hi):
    return np.clip((raw - lo) / (hi - lo), 0.0, 1.0)


def at_fpr(y, score, target=TARGET_FPR):
    """Threshold a score array so its FPR on clean traffic equals target."""
    thr = float(np.quantile(score[y == 0], 1.0 - target))
    m = binary_metrics(y, (score >= thr).astype(int))
    m["threshold"] = round(thr, 4)
    return m


def main():
    rng = np.random.default_rng(SEED)
    df = pd.read_csv("../upi_transactions_2024.csv")
    X = df[ALL_FEATURES].copy()
    X_train, X_test = train_test_split(X, test_size=0.2, random_state=SEED)
    synth = inject_synthetics(X_test, rng)
    X_eval = pd.concat([X_test, synth[ALL_FEATURES]], ignore_index=True)
    y = np.concatenate([np.zeros(len(X_test)), np.ones(len(synth))])
    log.info("Eval set: %d clean + %d injected", len(X_test), len(synth))

    results = {}

    # ---- Tier 2: Isolation Forest --------------------------------------
    iso = fit_forest(X_train, ALL_FEATURES)
    s_iso = calibrated_scores(iso, X_eval)

    # ---- Tier 3: LOF ----------------------------------------------------
    pre = build_preprocessor(ALL_FEATURES)
    Xt_tr = pre.fit_transform(X_train[ALL_FEATURES])
    Xt_ev = pre.transform(X_eval[ALL_FEATURES])
    sub = rng.choice(Xt_tr.shape[0], 40_000, replace=False)
    lof = LocalOutlierFactor(n_neighbors=20, novelty=True).fit(Xt_tr[sub])
    lof_tr = -lof.decision_function(Xt_tr[sub])
    lo, hi = float(lof_tr.min()), float(np.percentile(lof_tr, 99.95))
    s_lof = calibrate(-lof.decision_function(Xt_ev), lo, hi)

    # ---- Tier 1: rule engine -------------------------------------------
    thresholds = derive_thresholds(X_train["amount (INR)"].to_numpy())
    log.info("Rule thresholds: %s", {k: round(v) for k, v in thresholds.items()})
    rule_risk, hard = evaluate_rules(X_eval, thresholds)

    # ---- Fusion ---------------------------------------------------------
    s_hybrid = fuse(s_iso, s_lof, rule_risk)

    # ---- Comparison at matched FPR --------------------------------------
    log.info("=== Per-tier vs hybrid, all at FPR ~= %.4f ===", TARGET_FPR)
    table = {}

    m = binary_metrics(y, hard.astype(int))
    m["note"] = "hard rules fire deterministically; FPR not tunable"
    table["rules_only"] = m
    log.info("  rules only   P=%.3f R=%.3f F1=%.3f FPR=%.4f",
             m["precision"], m["recall"], m["f1"], m["fpr"])

    for name, s in [("iforest_only", s_iso), ("lof_only", s_lof),
                    ("hybrid", s_hybrid)]:
        m = at_fpr(y, s)
        m["roc_auc"] = float(roc_auc_score(y, s))
        table[name] = m
        log.info("  %-12s P=%.3f R=%.3f F1=%.3f FPR=%.4f AUC=%.4f thr=%.3f",
                 name.replace("_", " "), m["precision"], m["recall"], m["f1"],
                 m["fpr"], m["roc_auc"], m["threshold"])

    # hybrid including the hard-rule escalation path
    thr = table["hybrid"]["threshold"]
    flags = decide(s_hybrid, hard, thr)
    m = binary_metrics(y, flags)
    m["roc_auc"] = table["hybrid"]["roc_auc"]
    m["threshold"] = thr
    table["hybrid_with_rule_escalation"] = m
    log.info("  hybrid+rules P=%.3f R=%.3f F1=%.3f FPR=%.4f",
             m["precision"], m["recall"], m["f1"], m["fpr"])

    results["comparison"] = table

    # ---- per-archetype breakdown ---------------------------------------
    per = {}
    n_clean = len(X_test)
    for arch in synth["archetype"].unique():
        mask = (synth["archetype"] == arch).to_numpy()
        per[arch] = {
            "iforest": float((s_iso[n_clean:][mask] >= table["iforest_only"]["threshold"]).mean()),
            "lof": float((s_lof[n_clean:][mask] >= table["lof_only"]["threshold"]).mean()),
            "hybrid": float(flags[n_clean:][mask].mean()),
        }
        log.info("  %-24s IF=%.2f  LOF=%.2f  HYBRID=%.2f", arch,
                 per[arch]["iforest"], per[arch]["lof"], per[arch]["hybrid"])
    results["per_archetype"] = per
    results["rule_thresholds"] = thresholds
    from hybrid import W_IFOREST, W_LOF
    results["fusion_weights"] = {"iforest": W_IFOREST, "lof": W_LOF}

    with open("evaluation_hybrid.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info("Written to evaluation_hybrid.json")


if __name__ == "__main__":
    main()
