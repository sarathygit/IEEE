package com.finguard.switchsvc.exception;

/**
 * Thrown when the ML core classifies a transaction as fraudulent
 * (is_fraud == 1). Because it is a RuntimeException escaping an
 * @Transactional boundary, Spring marks the ledger transaction
 * rollback-only: the debit/credit applied before scoring is undone
 * atomically. The account lock and BLOCKED_FRAUD audit row survive -
 * they are written in an independent REQUIRES_NEW transaction first.
 */
public class FraudulentTransactionException extends RuntimeException {

    private final String txnRef;
    private final double anomalyScore;

    public FraudulentTransactionException(String txnRef, double anomalyScore) {
        super("Transaction " + txnRef + " blocked by FinGuard-AI (anomaly score "
                + anomalyScore + "). Ledger rolled back, account locked.");
        this.txnRef = txnRef;
        this.anomalyScore = anomalyScore;
    }

    public String getTxnRef() { return txnRef; }
    public double getAnomalyScore() { return anomalyScore; }
}
