"""Train and serialise the hybrid scoring bundle.

Produces models/hybrid_bundle.joblib containing every artefact the live
service needs: the shared preprocessor, both fitted detectors with their
individual calibration constants, the derived rule thresholds, the fusion
weights and the production decision threshold.

Run (from ml-service/):  python train_hybrid.py
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor

from evaluate import ALL_FEATURES, SEED, build_preprocessor
from hybrid import W_IFOREST, W_LOF, derive_thresholds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("finguard.train.hybrid")

CALIB_PCT = 99.95
LOF_REFERENCE_N = 40_000
PRODUCTION_THRESHOLD = 0.802   # from the matched-FPR sweep in evaluate_hybrid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="../upi_transactions_2024.csv")
    ap.add_argument("--output", default="models/hybrid_bundle.joblib")
    args = ap.parse_args()

    rng = np.random.default_rng(SEED)
    df = pd.read_csv(args.input)
    X = df[ALL_FEATURES].copy()
    X_train, _ = train_test_split(X, test_size=0.2, random_state=SEED)
    log.info("Training rows: %d", len(X_train))

    # shared preprocessing for both ML tiers
    pre = build_preprocessor(ALL_FEATURES)
    Xt = pre.fit_transform(X_train[ALL_FEATURES])

    # ---- Tier 2: Isolation Forest --------------------------------------
    log.info("Fitting Isolation Forest (tier 2)...")
    iso = IsolationForest(n_estimators=200, contamination=0.002,
                          random_state=SEED, n_jobs=-1).fit(Xt)
    iso_raw = -iso.decision_function(Xt)
    iso_lo = float(iso_raw.min())
    iso_hi = float(np.percentile(iso_raw, CALIB_PCT))
    log.info("  calibration: [%.4f, %.4f]", iso_lo, iso_hi)

    # ---- Tier 3: LOF ----------------------------------------------------
    log.info("Fitting Local Outlier Factor (tier 3, %d-point reference)...",
             LOF_REFERENCE_N)
    sub = rng.choice(Xt.shape[0], LOF_REFERENCE_N, replace=False)
    Xt_ref = Xt[sub]
    lof = LocalOutlierFactor(n_neighbors=20, novelty=True).fit(Xt_ref)
    lof_raw = -lof.decision_function(Xt_ref)
    lof_lo = float(lof_raw.min())
    lof_hi = float(np.percentile(lof_raw, CALIB_PCT))
    log.info("  calibration: [%.4f, %.4f]", lof_lo, lof_hi)

    # ---- Tier 1: rule thresholds ---------------------------------------
    rule_thresholds = derive_thresholds(X_train["amount (INR)"].to_numpy())
    log.info("Rule thresholds: %s",
             {k: round(v) for k, v in rule_thresholds.items()})

    bundle = {
        "preprocessor": pre,
        "iforest": iso,
        "iforest_min": iso_lo,
        "iforest_max": iso_hi,
        "lof": lof,
        "lof_min": lof_lo,
        "lof_max": lof_hi,
        "rule_thresholds": rule_thresholds,
        "w_iforest": W_IFOREST,
        "w_lof": W_LOF,
        "production_threshold": PRODUCTION_THRESHOLD,
        "feature_columns": ALL_FEATURES,
        "numeric_features": ["amount (INR)", "hour_of_day", "is_weekend"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "n_estimators": 200,
        "lof_reference_n": LOF_REFERENCE_N,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out)
    size_mb = out.stat().st_size / 1e6
    log.info("Hybrid bundle written to %s (%.1f MB)", out.resolve(), size_mb)


if __name__ == "__main__":
    main()
