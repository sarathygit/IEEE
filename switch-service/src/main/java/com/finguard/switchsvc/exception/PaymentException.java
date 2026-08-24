package com.finguard.switchsvc.exception;

import org.springframework.http.HttpStatus;

/**
 * Business-rule rejections that are NOT fraud verdicts: unknown VPA, wrong
 * MPIN, insufficient funds, locked account, scoring node unreachable. Each
 * carries the HTTP status the REST layer should surface.
 */
public class PaymentException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    private PaymentException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public static PaymentException userNotFound(String vpa) {
        return new PaymentException(HttpStatus.NOT_FOUND, "USER_NOT_FOUND",
                "No account registered for VPA: " + vpa);
    }

    public static PaymentException invalidMpin() {
        return new PaymentException(HttpStatus.UNAUTHORIZED, "INVALID_MPIN",
                "MPIN verification failed");
    }

    public static PaymentException accountLocked(String vpa) {
        return new PaymentException(HttpStatus.LOCKED, "ACCOUNT_LOCKED",
                "Account " + vpa + " is locked following a security block. Contact support.");
    }

    public static PaymentException insufficientFunds() {
        return new PaymentException(HttpStatus.UNPROCESSABLE_ENTITY, "INSUFFICIENT_FUNDS",
                "Insufficient balance for this transaction");
    }

    public static PaymentException selfTransfer() {
        return new PaymentException(HttpStatus.UNPROCESSABLE_ENTITY, "SELF_TRANSFER",
                "Payer and payee VPA cannot be the same");
    }

    /**
     * Fail-closed policy: if the ML core is down or times out, the payment is
     * rejected rather than waved through unscored. Availability is sacrificed
     * before safety.
     */
    public static PaymentException scoringUnavailable(Throwable cause) {
        PaymentException e = new PaymentException(HttpStatus.SERVICE_UNAVAILABLE,
                "SCORING_UNAVAILABLE",
                "Fraud scoring service unreachable; transaction rejected (fail-closed)");
        e.initCause(cause);
        return e;
    }

    public HttpStatus getStatus() { return status; }
    public String getCode() { return code; }
}
