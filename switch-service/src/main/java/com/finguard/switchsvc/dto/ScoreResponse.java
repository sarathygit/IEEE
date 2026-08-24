package com.finguard.switchsvc.dto;

/** Verdict returned by the Python ML core's POST /score. */
public record ScoreResponse(
        double anomaly_score,
        int is_fraud,
        double threshold,
        double processing_ms,
        String model_trained_at
) {
}
