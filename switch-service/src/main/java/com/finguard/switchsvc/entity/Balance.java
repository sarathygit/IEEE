package com.finguard.switchsvc.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;

/**
 * Ledger row for one account. Money is BigDecimal(15,2) - never floating
 * point. Rows are acquired with PESSIMISTIC_WRITE during payment processing,
 * which is what physically "freezes" the account while the ML core deliberates.
 */
@Entity
@Table(name = "balances")
public class Balance {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private User user;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal amountInr;

    protected Balance() {
        // JPA
    }

    public Balance(User user, BigDecimal amountInr) {
        this.user = user;
        this.amountInr = amountInr;
    }

    public Long getId() { return id; }
    public User getUser() { return user; }
    public BigDecimal getAmountInr() { return amountInr; }

    public void debit(BigDecimal amount) {
        this.amountInr = this.amountInr.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        this.amountInr = this.amountInr.add(amount);
    }
}
