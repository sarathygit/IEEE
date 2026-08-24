package com.finguard.switchsvc.config;

import com.finguard.switchsvc.entity.Balance;
import com.finguard.switchsvc.entity.User;
import com.finguard.switchsvc.repository.BalanceRepository;
import com.finguard.switchsvc.repository.UserRepository;
import com.finguard.switchsvc.service.PaymentService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

/**
 * Seeds the in-memory H2 ledger on startup. Demo MPINs (printed below) are
 * hashed through the same code path production authentication uses.
 */
@Configuration
public class DemoDataSeeder {

    private static final Logger log = LoggerFactory.getLogger(DemoDataSeeder.class);

    /** Size of the synthetic account pool used by the concurrency benchmark. */
    @org.springframework.beans.factory.annotation.Value("${finguard.demo.load-pool-size:0}")
    private int loadPoolSize;

    @Bean
    CommandLineRunner seedDemoData(UserRepository users, BalanceRepository balances) {
        return args -> seed(users, balances);
    }

    @Transactional
    void seed(UserRepository users, BalanceRepository balances) {
        if (users.count() > 0) {
            return;
        }
        record Seed(String name, String vpa, String mpin, String age,
                    String state, String bank, String balance) {}

        Seed[] seeds = {
            new Seed("Arjun Mehta",  "arjun@fgbank",  "4321", "26-35", "Delhi",       "Axis",  "58000.00"),
            new Seed("Priya Nair",   "priya@fgbank",  "9876", "36-45", "Karnataka",   "HDFC",  "125000.00"),
            new Seed("Grocery Mart", "grocery@fgpay", "1111", "26-35", "Delhi",       "SBI",   "310000.00"),
            new Seed("Ravi Kumar",   "ravi@fgbank",   "2468", "56+",   "Maharashtra", "Kotak", "9000.00"),
        };

        for (Seed s : seeds) {
            User u = users.save(new User(s.name(), s.vpa(),
                    PaymentService.hashMpin(s.vpa(), s.mpin()),
                    s.age(), s.state(), s.bank()));
            balances.save(new Balance(u, new BigDecimal(s.balance())));
            log.info("Seeded {} ({}) balance INR {} [demo MPIN {}]",
                    s.vpa(), s.name(), s.balance(), s.mpin());
        }

        // Load-test fixture: a pool of identical accounts (MPIN 1234) so the
        // concurrency benchmark can exercise both the uncontended path
        // (distinct payer per thread) and the contended path (all threads on
        // one payer, serializing on its pessimistic row lock).
        if (loadPoolSize > 0) {
            for (int i = 1; i <= loadPoolSize; i++) {
                String vpa = String.format("load%02d@fgbank", i);
                User u = users.save(new User("Load Account " + i, vpa,
                        PaymentService.hashMpin(vpa, "1234"),
                        "26-35", "Delhi", "Axis"));
                balances.save(new Balance(u, new BigDecimal("1000000.00")));
            }
            log.info("Seeded {} load-test accounts (load01..load{} @fgbank, MPIN 1234)",
                    loadPoolSize, String.format("%02d", loadPoolSize));
        }
    }
}
