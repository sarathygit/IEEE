package com.finguard.switchsvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * FinGuard-AI :: Module 3 - Enterprise Switch Layer (port 8080).
 *
 * Receives UPI payment requests from the React client, suspends the request
 * thread while the Python Predictive Intelligence Core scores the transaction
 * inline, then either commits the ledger movement or rolls it back atomically.
 */
@SpringBootApplication
public class FinGuardSwitchApplication {

    public static void main(String[] args) {
        SpringApplication.run(FinGuardSwitchApplication.class, args);
    }
}
