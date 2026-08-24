package com.finguard.switchsvc.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import java.math.BigDecimal;

/**
 * Inbound payment from the React client: payment inputs plus background
 * device telemetry. Profile-derived ML features (age groups, states, banks)
 * are NOT accepted from the client - the switch resolves them from the DB so
 * a hostile client cannot spoof its own risk profile.
 */
public record PaymentRequest(

        @NotBlank(message = "payerVpa is required")
        String payerVpa,

        @NotBlank(message = "payeeVpa is required")
        String payeeVpa,

        @NotNull(message = "amountInr is required")
        @DecimalMin(value = "1.00", message = "amount must be at least INR 1")
        @Digits(integer = 13, fraction = 2, message = "amount must have at most 2 decimal places")
        BigDecimal amountInr,

        @NotBlank(message = "mpin is required")
        @Pattern(regexp = "\\d{4,6}", message = "mpin must be 4-6 digits")
        String mpin,

        @NotBlank(message = "transactionType is required")
        String transactionType,

        @NotBlank(message = "merchantCategory is required")
        String merchantCategory,

        // --- background device telemetry ---

        @NotBlank(message = "deviceType is required")
        String deviceType,

        @NotBlank(message = "networkType is required")
        String networkType,

        @NotBlank(message = "deviceSignature is required")
        String deviceSignature,

        @NotBlank(message = "geoLocationHash is required")
        String geoLocationHash
) {
}
