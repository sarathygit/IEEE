"""
FinGuard-AI :: Module 2 - Predictive Intelligence Core (FastAPI)

Serves the HYBRID scoring engine: a deterministic rule tier, an Isolation
Forest (global/partition-based) and a Local Outlier Factor detector
(local/density-based), fused into a single explainable verdict. The bundle
produced by train_hybrid.py is loaded once at startup.

Run (from ml-service/):
    uvicorn app:app --host 127.0.0.1 --port 8000

Request contract (all fields known BEFORE the transaction settles - the
post-hoc `transaction_status` column is intentionally absent, matching the
training feature boundary in train.py):

    POST /score
    {
        "amount_inr": 42000.0,
        "hour_of_day": 3,
        "is_weekend": 1,
        "transaction_type": "P2P",
        "merchant_category": "Other",
        "sender_age_group": "56+",
        "receiver_age_group": "18-25",
        "sender_state": "Delhi",
        "sender_bank": "Kotak",
        "receiver_bank": "ICICI",
        "device_type": "Web",
        "network_type": "WiFi",
        "day_of_week": "Sunday"
    }

Response (per-tier breakdown makes the verdict explainable):
    { "anomaly_score": 0.9372, "is_fraud": 1, "threshold": 0.802,
      "iforest_score": 0.81, "lof_score": 0.96, "rule_risk": 0.55,
      "hard_rule_fired": true, "processing_ms": 3.1, ... }

Category strings never seen in training are tolerated: the bundled
OneHotEncoder was fitted with handle_unknown="ignore", so an unseen bank or
state encodes to all-zeros for that block (which reads as unusual to both
detectors) instead of erroring the hot path.
"""

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from hybrid import evaluate_rules, fuse, decide
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("finguard.score")

# Resolve relative to this file so the service works no matter the launch cwd.
BUNDLE_PATH = Path(__file__).resolve().parent / "models" / "hybrid_bundle.joblib"

# Populated once at startup; treated as read-only afterwards (safe across
# uvicorn's async request handling - inference never mutates the bundle).
_state: dict = {}


class TransactionFeatures(BaseModel):
    """Pre-settlement transaction metadata sent by the Spring Boot switch."""

    amount_inr: float = Field(gt=0, description="Transaction amount in INR")
    hour_of_day: int = Field(ge=0, le=23)
    is_weekend: int = Field(ge=0, le=1)
    transaction_type: str
    merchant_category: str
    sender_age_group: str
    receiver_age_group: str
    sender_state: str
    sender_bank: str
    receiver_bank: str
    device_type: str
    network_type: str
    day_of_week: str

    def to_feature_row(self) -> dict:
        """Map the API's snake_case contract onto the training column names."""
        return {
            "amount (INR)": self.amount_inr,
            "hour_of_day": self.hour_of_day,
            "is_weekend": self.is_weekend,
            "transaction type": self.transaction_type,
            "merchant_category": self.merchant_category,
            "sender_age_group": self.sender_age_group,
            "receiver_age_group": self.receiver_age_group,
            "sender_state": self.sender_state,
            "sender_bank": self.sender_bank,
            "receiver_bank": self.receiver_bank,
            "device_type": self.device_type,
            "network_type": self.network_type,
            "day_of_week": self.day_of_week,
        }


class ScoreResponse(BaseModel):
    anomaly_score: float
    is_fraud: int
    threshold: float
    processing_ms: float
    model_trained_at: str
    # Per-tier breakdown: the hybrid's decision is explainable, unlike a
    # single opaque score. The switch logs these for audit.
    iforest_score: float
    lof_score: float
    rule_risk: float
    hard_rule_fired: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not BUNDLE_PATH.exists():
        # Fail fast and loud: a scoring node without a model must never
        # accept traffic, otherwise the switch would block on dead requests.
        raise RuntimeError(
            f"Hybrid bundle not found at {BUNDLE_PATH}. Run train_hybrid.py first."
        )
    t0 = time.perf_counter()
    bundle = joblib.load(BUNDLE_PATH)
    _state.update(bundle)
    log.info(
        "Hybrid bundle loaded in %.1f ms (trained_at=%s, sklearn=%s, "
        "threshold=%.3f, weights iforest=%.2f lof=%.2f)",
        (time.perf_counter() - t0) * 1000,
        bundle["trained_at"], bundle["sklearn_version"],
        bundle["production_threshold"], bundle["w_iforest"], bundle["w_lof"],
    )

    # Warm-up inference: the first transform/predict pays one-time lazy-init
    # costs inside pandas/sklearn (~20-30 ms). Paying it here keeps the first
    # real transaction inside the sub-50 ms budget.
    warmup = pd.DataFrame(
        [{col: (0.0 if col in bundle["numeric_features"] else "warmup")
          for col in bundle["feature_columns"]}]
    )[bundle["feature_columns"]]
    t1 = time.perf_counter()
    _wf = bundle["preprocessor"].transform(warmup)
    bundle["iforest"].decision_function(_wf)
    bundle["lof"].decision_function(_wf)
    evaluate_rules(warmup, bundle["rule_thresholds"])
    log.info("Warm-up inference (all 3 tiers) completed in %.1f ms",
             (time.perf_counter() - t1) * 1000)
    yield
    _state.clear()


app = FastAPI(
    title="FinGuard-AI Predictive Intelligence Core",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the dashboard to poll /health for its status bar. Scoring traffic
# itself is server-to-server (Spring Boot) and unaffected by CORS.
#
# CORS_ALLOWED_ORIGINS is a comma-separated list; the default reproduces the
# previous hard-coded Vite/CRA dev-server allow-list, so local development is
# unchanged. Entries are matched exactly, except that a single leading "*."
# label becomes a regex so preview deployments resolve
# (e.g. "https://*.vercel.app").
_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    if o.strip()
]
_exact = [o for o in _origins if "*" not in o]
_wild = [
    re.escape(o).replace(r"\*", r"[^.]+") for o in _origins if "*" in o
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_exact,
    allow_origin_regex="|".join(_wild) if _wild else None,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe for the Spring Boot switch."""
    if "iforest" not in _state:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "status": "UP",
        "engine": "hybrid (rules + isolation forest + LOF)",
        "model_trained_at": _state["trained_at"],
        "threshold": _state["production_threshold"],
        "fusion_weights": {"iforest": _state["w_iforest"], "lof": _state["w_lof"]},
        "n_estimators": _state["n_estimators"],
        "lof_reference_n": _state["lof_reference_n"],
    }


@app.post("/score", response_model=ScoreResponse)
def score(txn: TransactionFeatures) -> ScoreResponse:
    if "iforest" not in _state:
        raise HTTPException(status_code=503, detail="Model not loaded")

    t0 = time.perf_counter()

    X = pd.DataFrame([txn.to_feature_row()])[_state["feature_columns"]]
    features = _state["preprocessor"].transform(X)

    # --- Tier 2: Isolation Forest (global, partition-based) -------------
    iso_raw = -_state["iforest"].decision_function(features)[0]
    s_iso = float(np.clip(
        (iso_raw - _state["iforest_min"])
        / (_state["iforest_max"] - _state["iforest_min"]), 0.0, 1.0))

    # --- Tier 3: LOF (local, density-based) ----------------------------
    lof_raw = -_state["lof"].decision_function(features)[0]
    s_lof = float(np.clip(
        (lof_raw - _state["lof_min"])
        / (_state["lof_max"] - _state["lof_min"]), 0.0, 1.0))

    # --- Tier 1: deterministic rule engine ------------------------------
    rule_risk, hard = evaluate_rules(X, _state["rule_thresholds"])

    # --- Fusion: weighted ML blend, floored by the rule risk ------------
    anomaly_score = float(fuse(np.array([s_iso]), np.array([s_lof]), rule_risk)[0])

    threshold = _state["production_threshold"]
    is_fraud = int(decide(np.array([anomaly_score]), hard, threshold)[0])
    elapsed_ms = (time.perf_counter() - t0) * 1000

    log.info(
        "scored txn: amount=%.2f hour=%d type=%s -> iforest=%.3f lof=%.3f "
        "rule=%.3f | fused=%.4f is_fraud=%d hard_rule=%s (%.2f ms)",
        txn.amount_inr, txn.hour_of_day, txn.transaction_type,
        s_iso, s_lof, float(rule_risk[0]), anomaly_score, is_fraud,
        bool(hard[0]), elapsed_ms,
    )
    return ScoreResponse(
        anomaly_score=round(anomaly_score, 6),
        is_fraud=is_fraud,
        threshold=threshold,
        processing_ms=round(elapsed_ms, 3),
        model_trained_at=_state["trained_at"],
        iforest_score=round(s_iso, 6),
        lof_score=round(s_lof, 6),
        rule_risk=round(float(rule_risk[0]), 6),
        hard_rule_fired=bool(hard[0]),
    )
