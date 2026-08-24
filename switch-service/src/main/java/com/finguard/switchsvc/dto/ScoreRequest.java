package com.finguard.switchsvc.dto;

/**
 * Payload for the Python ML core's POST /score - must match the FastAPI
 * TransactionFeatures contract field-for-field (snake_case via Jackson
 * property naming below). All 13 fields are known before settlement.
 */
public record ScoreRequest(
        double amount_inr,
        int hour_of_day,
        int is_weekend,
        String transaction_type,
        String merchant_category,
        String sender_age_group,
        String receiver_age_group,
        String sender_state,
        String sender_bank,
        String receiver_bank,
        String device_type,
        String network_type,
        String day_of_week
) {
}
