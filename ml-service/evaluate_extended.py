"""Extended experiments for the journal-length manuscript.

Adds two studies the conference version lacks:

  E4. THRESHOLD SENSITIVITY - sweep tau over [0.60, 0.99] and trace the
      recall/FPR/precision trade-off, so the deployed operating point is
      justified quantitatively rather than by assertion. Also reports the
      block rate on genuine traffic, which is the operationally binding
      constraint for an inline blocker.

  E5. SCORER SUBSTITUTION - re-run the full pipeline with LOF substituted
      for the Isolation Forest at matched FPR, to substantiate (rather than
      merely assert) the claim that the interception architecture is
      model-agnostic and that scorer choice is the current bottleneck.

Run:  python evaluate_extended.py
Writes evaluation_extended.json
"""

import json
import logging

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor

from evaluate import (ALL_FEATURES, SEED, PRODUCTION_THRESHOLD,
                      build_preprocessor, fit_forest, calibrated_scores,
                      inject_synthetics, binary_metrics)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("finguard.eval.ext")


def main():
    rng = np.random.default_rng(SEED)
    results = {}

    df = pd.read_csv("../upi_transactions_2024.csv")
    X = df[ALL_FEATURES].copy()
    X_train, X_test = train_test_split(X, test_size=0.2, random_state=SEED)
    synth = inject_synthetics(X_test, rng)
    X_eval = pd.concat([X_test, synth[ALL_FEATURES]], ignore_index=True)
    y = np.concatenate([np.zeros(len(X_test)), np.ones(len(synth))])

    prod = fit_forest(X_train, ALL_FEATURES)
    scores = calibrated_scores(prod, X_eval)

    # ---- E4: threshold sensitivity --------------------------------------
    log.info("=== E4: threshold sensitivity ===")
    sweep = []
    for tau in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99]:
        m = binary_metrics(y, (scores >= tau).astype(int))
        # Operational framing: of 100k genuine daily transactions, how many
        # legitimate customers would be blocked and locked out?
        m["tau"] = tau
        m["blocked_per_100k_genuine"] = round(m["fpr"] * 100_000)
        sweep.append(m)
        log.info("  tau=%.2f  recall=%.3f  FPR=%.4f  prec=%.3f  "
                 "genuine blocked/100k=%d",
                 tau, m["recall"], m["fpr"], m["precision"],
                 m["blocked_per_100k_genuine"])
    results["threshold_sweep"] = sweep

    # ---- E5: scorer substitution (LOF in the same pipeline) -------------
    log.info("=== E5: scorer substitution (LOF) ===")
    pre = build_preprocessor(ALL_FEATURES)
    Xt_tr = pre.fit_transform(X_train[ALL_FEATURES])
    Xt_ev = pre.transform(X_eval[ALL_FEATURES])

    sub = rng.choice(Xt_tr.shape[0], 40_000, replace=False)
    lof = LocalOutlierFactor(n_neighbors=20, novelty=True).fit(Xt_tr[sub])
    lof_raw = -lof.decision_function(Xt_ev)

    # Calibrate LOF with the SAME winsorised convention used in production so
    # the comparison is like-for-like, not an artefact of score scaling.
    lof_tr = -lof.decision_function(Xt_tr[sub])
    lo, hi = float(lof_tr.min()), float(np.percentile(lof_tr, 99.95))
    lof_cal = np.clip((lof_raw - lo) / (hi - lo), 0.0, 1.0)

    # Match the deployed model's FPR so recall is compared at equal
    # operational cost.
    target_fpr = float((scores[y == 0] >= PRODUCTION_THRESHOLD).mean())
    lof_tau = float(np.quantile(lof_cal[y == 0], 1.0 - target_fpr))
    m_lof = binary_metrics(y, (lof_cal >= lof_tau).astype(int))
    m_lof["tau_matched"] = round(lof_tau, 4)
    m_lof["target_fpr"] = round(target_fpr, 5)
    m_lof["roc_auc"] = float(roc_auc_score(y, lof_cal))

    m_if = binary_metrics(y, (scores >= PRODUCTION_THRESHOLD).astype(int))
    m_if["roc_auc"] = float(roc_auc_score(y, scores))

    per_arch = {}
    for name in synth["archetype"].unique():
        mask = (synth["archetype"] == name).to_numpy()
        per_arch[name] = {
            "iforest_recall": float((scores[len(X_test):][mask]
                                     >= PRODUCTION_THRESHOLD).mean()),
            "lof_recall": float((lof_cal[len(X_test):][mask] >= lof_tau).mean()),
        }
        log.info("  %-24s IF=%.3f  LOF=%.3f", name,
                 per_arch[name]["iforest_recall"], per_arch[name]["lof_recall"])

    results["scorer_substitution"] = {
        "isolation_forest": m_if, "lof": m_lof, "per_archetype": per_arch}
    log.info("  At matched FPR=%.4f: IF recall=%.3f -> LOF recall=%.3f",
             target_fpr, m_if["recall"], m_lof["recall"])

    with open("evaluation_extended.json", "w") as f:
        json.dump(results, f, indent=2)
    log.info("Written to evaluation_extended.json")


if __name__ == "__main__":
    main()
