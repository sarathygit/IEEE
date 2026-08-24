package com.finguard.switchsvc.dto;

import java.math.BigDecimal;

/**
 * Outcome returned to the React viewport. `status` drives the Green Success
 * Screen ("SUCCESS") vs the Red Security Block Alert ("BLOCKED_FRAUD").
 */
public record PaymentResponse(
        String txnRef,
        String status,
        String message,
        BigDecimal amountInr,
        String payeeVpa,
        double anomalyScore,
        long processingMs,
        BigDecimal remainingBalance
) {
}
