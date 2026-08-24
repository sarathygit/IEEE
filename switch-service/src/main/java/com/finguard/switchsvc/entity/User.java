package com.finguard.switchsvc.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * A UPI account holder. Profile attributes (age group, state, bank) double as
 * ML features: the switch enriches each /score payload from this row so the
 * client never has to send - or be trusted with - profile data.
 */
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String fullName;

    /** Virtual Payment Address, e.g. "arjun@fgbank" - the UPI routing key. */
    @Column(nullable = false, unique = true)
    private String vpa;

    /** SHA-256 hex digest of the MPIN. Plaintext MPINs are never stored. */
    @Column(nullable = false)
    private String mpinHash;

    @Column(nullable = false)
    private String ageGroup;

    @Column(nullable = false)
    private String state;

    @Column(nullable = false)
    private String bank;

    /** Set to true by the fraud path; locked accounts cannot transact. */
    @Column(nullable = false)
    private boolean accountLocked = false;

    protected User() {
        // JPA
    }

    public User(String fullName, String vpa, String mpinHash,
                String ageGroup, String state, String bank) {
        this.fullName = fullName;
        this.vpa = vpa;
        this.mpinHash = mpinHash;
        this.ageGroup = ageGroup;
        this.state = state;
        this.bank = bank;
    }

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
    public String getVpa() { return vpa; }
    public String getMpinHash() { return mpinHash; }
    public String getAgeGroup() { return ageGroup; }
    public String getState() { return state; }
    public String getBank() { return bank; }
    public boolean isAccountLocked() { return accountLocked; }
    public void setAccountLocked(boolean accountLocked) { this.accountLocked = accountLocked; }
}
