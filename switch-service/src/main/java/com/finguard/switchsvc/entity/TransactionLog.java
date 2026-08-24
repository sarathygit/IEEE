package com.finguard.switchsvc.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Immutable audit record for every payment attempt - committed, blocked, or
 * failed. BLOCKED rows are written in an independent transaction
 * (REQUIRES_NEW) so they survive the ledger rollback they describe.
 */
@Entity
@Table(name = "transaction_logs")
public class TransactionLog {

    public enum Status { SUCCESS, BLOCKED_FRAUD, FAILED }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String txnRef;

    @Column(nullable = false)
    private String senderVpa;

    @Column(nullable = false)
    private String receiverVpa;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal amountInr;

    @Column(nullable = false)
    private String transactionType;

    @Column(nullable = false)
    private String merchantCategory;

    @Column(nullable = false)
    private String deviceType;

    @Column(nullable = false)
    private String networkType;

    /** Normalized [0,1] anomaly score returned by the ML core. */
    @Column(nullable = false)
    private double anomalyScore;

    @Column(nullable = false)
    private int fraudVerdict;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status;

    /** End-to-end switch processing time, for the sub-50ms budget audit. */
    @Column(nullable = false)
    private long processingMs;

    @Column(nullable = false)
    private Instant createdAt;

    protected TransactionLog() {
        // JPA
    }

    public TransactionLog(String txnRef, String senderVpa, String receiverVpa,
                          BigDecimal amountInr, String transactionType,
                          String merchantCategory, String deviceType,
                          String networkType, double anomalyScore,
                          int fraudVerdict, Status status, long processingMs) {
        this.txnRef = txnRef;
        this.senderVpa = senderVpa;
        this.receiverVpa = receiverVpa;
        this.amountInr = amountInr;
        this.transactionType = transactionType;
        this.merchantCategory = merchantCategory;
        this.deviceType = deviceType;
        this.networkType = networkType;
        this.anomalyScore = anomalyScore;
        this.fraudVerdict = fraudVerdict;
        this.status = status;
        this.processingMs = processingMs;
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public String getTxnRef() { return txnRef; }
    public String getSenderVpa() { return senderVpa; }
    public String getReceiverVpa() { return receiverVpa; }
    public BigDecimal getAmountInr() { return amountInr; }
    public String getTransactionType() { return transactionType; }
    public String getMerchantCategory() { return merchantCategory; }
    public String getDeviceType() { return deviceType; }
    public String getNetworkType() { return networkType; }
    public double getAnomalyScore() { return anomalyScore; }
    public int getFraudVerdict() { return fraudVerdict; }
    public Status getStatus() { return status; }
    public long getProcessingMs() { return processingMs; }
    public Instant getCreatedAt() { return createdAt; }
}
