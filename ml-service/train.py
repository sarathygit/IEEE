"""
FinGuard-AI :: Module 1 - Local Isolation Forest Training Pipeline

Run entirely on the local machine against the full Kaggle UPI transaction
CSV. Produces a single .joblib bundle (preprocessor + fitted model + score
normalization constants + feature schema) that Module 2's FastAPI service
loads once at startup for live /score inference.

Usage:
    python train.py --input ../upi_transactions_2024.csv --output models/isolation_forest_bundle.joblib

IMPORTANT - feature/label boundary:
    `transaction_status` (SUCCESS/FAILED) is deliberately EXCLUDED from the
    feature set. In production, FastAPI scores a transaction BEFORE the
    Spring Boot switch commits or rolls it back (see architecture step 3-6),
    so that column does not exist yet at scoring time. Training on it would
    leak a post-hoc outcome into a pre-transaction model and the trained
    model would be unusable against the real /score payload.

    `fraud_flag` is likewise never passed to IsolationForest.fit() - the
    model stays unsupervised. The label is only used afterward, on a held-out
    split, to report how well the anomaly score lines up with real fraud
    (ROC-AUC, average precision, and a confusion matrix at the production
    threshold) and to set a sane `contamination` estimate.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("finguard.train")

# Threshold must match the production cutoff used by FastAPI /score
# (Section 3, step 5 of the architecture: is_fraud = 1 if score >= 0.85).
PRODUCTION_THRESHOLD = 0.85

ID_COLUMNS = ["transaction id", "timestamp"]
LABEL_COLUMN = "fraud_flag"
LEAKAGE_COLUMNS = ["transaction_status"]  # known only after the transaction resolves

NUMERIC_FEATURES = ["amount (INR)", "hour_of_day", "is_weekend"]
CATEGORICAL_FEATURES = [
    "transaction type",
    "merchant_category",
    "sender_age_group",
    "receiver_age_group",
    "sender_state",
    "sender_bank",
    "receiver_bank",
    "device_type",
    "network_type",
    "day_of_week",
]
REQUIRED_COLUMNS = set(
    ID_COLUMNS + [LABEL_COLUMN] + LEAKAGE_COLUMNS + NUMERIC_FEATURES + CATEGORICAL_FEATURES
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train FinGuard-AI Isolation Forest model.")
    parser.add_argument(
        "--input", type=Path, default=Path("../upi_transactions_2024.csv"),
        help="Path to the raw Kaggle UPI transactions CSV.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("models/isolation_forest_bundle.joblib"),
        help="Path to write the serialized model bundle.",
    )
    parser.add_argument(
        "--test-size", type=float, default=0.2,
        help="Fraction of rows held out for evaluation against fraud_flag.",
    )
    parser.add_argument(
        "--random-state", type=int, default=42,
        help="Random seed for the train/test split and the forest.",
    )
    parser.add_argument(
        "--n-estimators", type=int, default=200,
        help="Number of trees in the Isolation Forest.",
    )
    parser.add_argument(
        "--contamination", type=float, default=None,
        help="Expected anomaly proportion. Defaults to the observed fraud_flag "
             "rate in the training split (label used only for this hyperparameter, "
             "never fed into fit()).",
    )
    parser.add_argument(
        "--calibration-percentile", type=float, default=99.95,
        help="Percentile of the training raw-score distribution used as the "
             "normalization ceiling (score 1.0). Winsorizing here instead of "
             "taking the absolute max stops one freak training point from "
             "compressing the whole operational scoring range - without it, "
             "even maximal-amount transactions plateau below the 0.85 "
             "production threshold. Raw scores beyond this percentile "
             "saturate to 1.0.",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        log.error("Input CSV not found at %s", path.resolve())
        sys.exit(1)

    log.info("Loading dataset from %s", path.resolve())
    df = pd.read_csv(path)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        log.error("CSV is missing expected columns: %s", sorted(missing))
        sys.exit(1)

    null_counts = df[list(REQUIRED_COLUMNS)].isnull().sum()
    if null_counts.any():
        log.warning("Null values detected, dropping affected rows:\n%s", null_counts[null_counts > 0])
        df = df.dropna(subset=list(REQUIRED_COLUMNS))

    log.info("Loaded %d rows. fraud_flag rate: %.4f%%", len(df), 100 * df[LABEL_COLUMN].mean())
    return df


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )


def anomaly_scores(model: IsolationForest, X: np.ndarray) -> np.ndarray:
    """Raw, unnormalized anomaly signal: higher = more anomalous.

    sklearn's decision_function is the inverse convention (lower = more
    anomalous), so it is negated here before any min-max scaling happens.
    """
    return -model.decision_function(X)


def main() -> None:
    args = parse_args()

    df = load_dataset(args.input)

    feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    X = df[feature_columns]
    y = df[LABEL_COLUMN].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state, stratify=y,
    )
    log.info("Train rows: %d | Test rows: %d", len(X_train), len(X_test))

    contamination = args.contamination if args.contamination is not None else float(y_train.mean())
    contamination = min(max(contamination, 1e-4), 0.5)  # IsolationForest requires (0, 0.5]
    log.info("Using contamination=%.6f", contamination)

    preprocessor = build_preprocessor()
    model = IsolationForest(
        n_estimators=args.n_estimators,
        contamination=contamination,
        random_state=args.random_state,
        n_jobs=-1,
    )
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", model)])

    log.info("Fitting Isolation Forest (unsupervised - labels not used in fit)...")
    pipeline.fit(X_train)

    # Calibrate the [0, 1] score mapping off the training distribution so the
    # same transform is reproducible at inference time in FastAPI.
    train_raw_scores = anomaly_scores(model, preprocessor.transform(X_train))
    score_min = float(train_raw_scores.min())
    score_max = float(np.percentile(train_raw_scores, args.calibration_percentile))
    log.info(
        "Raw anomaly score calibration: min=%.4f, ceiling(p%.2f)=%.4f (absolute max %.4f)",
        score_min, args.calibration_percentile, score_max, float(train_raw_scores.max()),
    )

    def normalize(raw: np.ndarray) -> np.ndarray:
        scaled = (raw - score_min) / (score_max - score_min)
        return np.clip(scaled, 0.0, 1.0)

    test_raw_scores = anomaly_scores(model, preprocessor.transform(X_test))
    test_scores = normalize(test_raw_scores)
    test_predictions = (test_scores >= PRODUCTION_THRESHOLD).astype(int)

    log.info("--- Held-out evaluation against fraud_flag (label NOT used in training) ---")
    if y_test.nunique() > 1:
        log.info("ROC-AUC:            %.4f", roc_auc_score(y_test, test_scores))
        log.info("Average precision:  %.4f", average_precision_score(y_test, test_scores))
    else:
        log.warning("Test split has only one class present; AUC/AP are undefined.")

    tn, fp, fn, tp = confusion_matrix(y_test, test_predictions, labels=[0, 1]).ravel()
    log.info(
        "Confusion matrix @ threshold=%.2f -> TP=%d FP=%d FN=%d TN=%d",
        PRODUCTION_THRESHOLD, tp, fp, fn, tn,
    )
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    log.info("Precision=%.4f Recall=%.4f", precision, recall)

    bundle = {
        "preprocessor": preprocessor,
        "model": model,
        "score_min": score_min,
        "score_max": score_max,
        "production_threshold": PRODUCTION_THRESHOLD,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "feature_columns": feature_columns,
        "sklearn_version": sklearn.__version__,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "contamination": contamination,
        "n_estimators": args.n_estimators,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.output)
    log.info("Model bundle written to %s", args.output.resolve())


if __name__ == "__main__":
    main()
