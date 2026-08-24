package com.finguard.switchsvc.service;

import com.finguard.switchsvc.dto.PaymentRequest;
import com.finguard.switchsvc.dto.PaymentResponse;
import com.finguard.switchsvc.dto.ScoreRequest;
import com.finguard.switchsvc.dto.ScoreResponse;
import com.finguard.switchsvc.entity.Balance;
import com.finguard.switchsvc.entity.TransactionLog;
import com.finguard.switchsvc.entity.User;
import com.finguard.switchsvc.exception.FraudulentTransactionException;
import com.finguard.switchsvc.exception.PaymentException;
import com.finguard.switchsvc.repository.BalanceRepository;
import com.finguard.switchsvc.repository.TransactionLogRepository;
import com.finguard.switchsvc.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.time.DayOfWeek;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.HexFormat;
import java.util.UUID;

/**
 * The inline interception pipeline (architecture steps 2-6).
 *
 * Everything below runs inside ONE database transaction on the request
 * thread. The pessimistic lock taken on the payer's balance row is the
 * "thread freeze": the account is immobilized while the ML core deliberates.
 *
 *   1. resolve + authenticate payer, resolve payee
 *   2. lock both balance rows (deterministic id order - no deadlocks)
 *   3. apply the debit/credit to the persistence context (uncommitted)
 *   4. suspend: synchronous hop to the Python core's /score
 *   5. verdict == fraud  -> commit the account lock + BLOCKED audit row in an
 *      independent transaction, then throw FraudulentTransactionException,
 *      which rolls the uncommitted ledger movement back atomically
 *   6. verdict == clean  -> write the SUCCESS audit row and commit everything
 */
@Service
public class PaymentService {

    private static final Logger log = LoggerFactory.getLogger(PaymentService.class);
    private static final ZoneId UPI_ZONE = ZoneId.of("Asia/Kolkata");

    private final UserRepository userRepository;
    private final BalanceRepository balanceRepository;
    private final TransactionLogRepository transactionLogRepository;
    private final FraudScoringClient fraudScoringClient;
    private final AccountSecurityService accountSecurityService;

    public PaymentService(UserRepository userRepository,
                          BalanceRepository balanceRepository,
                          TransactionLogRepository transactionLogRepository,
                          FraudScoringClient fraudScoringClient,
                          AccountSecurityService accountSecurityService) {
        this.userRepository = userRepository;
        this.balanceRepository = balanceRepository;
        this.transactionLogRepository = transactionLogRepository;
        this.fraudScoringClient = fraudScoringClient;
        this.accountSecurityService = accountSecurityService;
    }

    @Transactional
    public PaymentResponse processPayment(PaymentRequest req) {
        long t0 = System.nanoTime();
        String txnRef = "FG" + UUID.randomUUID().toString().replace("-", "").substring(0, 16).toUpperCase();

        if (req.payerVpa().equalsIgnoreCase(req.payeeVpa())) {
            throw PaymentException.selfTransfer();
        }

        // --- 1. resolve + authenticate ---
        User payer = userRepository.findByVpa(req.payerVpa())
                .orElseThrow(() -> PaymentException.userNotFound(req.payerVpa()));
        if (payer.isAccountLocked()) {
            throw PaymentException.accountLocked(payer.getVpa());
        }
        verifyMpin(payer, req.mpin());

        User payee = userRepository.findByVpa(req.payeeVpa())
                .orElseThrow(() -> PaymentException.userNotFound(req.payeeVpa()));

        // --- 2. freeze: pessimistic locks, always in ascending user-id order
        //        so two opposing concurrent payments can never deadlock ---
        Balance payerBalance;
        Balance payeeBalance;
        if (payer.getId() < payee.getId()) {
            payerBalance = lockBalance(payer);
            payeeBalance = lockBalance(payee);
        } else {
            payeeBalance = lockBalance(payee);
            payerBalance = lockBalance(payer);
        }

        if (payerBalance.getAmountInr().compareTo(req.amountInr()) < 0) {
            throw PaymentException.insufficientFunds();
        }

        // --- 3. provisional ledger movement (uncommitted until verdict) ---
        payerBalance.debit(req.amountInr());
        payeeBalance.credit(req.amountInr());

        // --- 4. suspend the thread: synchronous microservice hop ---
        ScoreResponse verdict = fraudScoringClient.score(buildScoreRequest(req, payer, payee));

        long elapsedMs = (System.nanoTime() - t0) / 1_000_000;

        // --- 5. fraud: persist lock + audit independently, then roll back ---
        if (verdict.is_fraud() == 1) {
            TransactionLog blockedLog = new TransactionLog(
                    txnRef, payer.getVpa(), payee.getVpa(), req.amountInr(),
                    req.transactionType(), req.merchantCategory(),
                    req.deviceType(), req.networkType(),
                    verdict.anomaly_score(), 1,
                    TransactionLog.Status.BLOCKED_FRAUD, elapsedMs);
            accountSecurityService.lockAccountAndRecordBlock(payer.getId(), blockedLog);
            throw new FraudulentTransactionException(txnRef, verdict.anomaly_score());
        }

        // --- 6. clean: audit + commit ---
        transactionLogRepository.save(new TransactionLog(
                txnRef, payer.getVpa(), payee.getVpa(), req.amountInr(),
                req.transactionType(), req.merchantCategory(),
                req.deviceType(), req.networkType(),
                verdict.anomaly_score(), 0,
                TransactionLog.Status.SUCCESS, elapsedMs));

        log.info("COMMIT {}: {} -> {} INR {} (score={}, {} ms end-to-end)",
                txnRef, payer.getVpa(), payee.getVpa(), req.amountInr(),
                verdict.anomaly_score(), elapsedMs);

        return new PaymentResponse(txnRef, "SUCCESS",
                "Payment completed successfully", req.amountInr(), payee.getVpa(),
                verdict.anomaly_score(), elapsedMs, payerBalance.getAmountInr());
    }

    private Balance lockBalance(User user) {
        return balanceRepository.findByUserIdForUpdate(user.getId())
                .orElseThrow(() -> PaymentException.userNotFound(user.getVpa()));
    }

    /**
     * Assembles the 13-feature vector for the ML core. Client telemetry
     * supplies device/network; user profile rows supply demographics; the
     * switch clock (IST) supplies temporal features. `transaction_status`
     * does not exist yet by design - the verdict decides it.
     */
    private ScoreRequest buildScoreRequest(PaymentRequest req, User payer, User payee) {
        ZonedDateTime now = ZonedDateTime.now(UPI_ZONE);
        DayOfWeek dow = now.getDayOfWeek();
        boolean weekend = dow == DayOfWeek.SATURDAY || dow == DayOfWeek.SUNDAY;

        return new ScoreRequest(
                req.amountInr().doubleValue(),
                now.getHour(),
                weekend ? 1 : 0,
                req.transactionType(),
                req.merchantCategory(),
                payer.getAgeGroup(),
                payee.getAgeGroup(),
                payer.getState(),
                payer.getBank(),
                payee.getBank(),
                req.deviceType(),
                req.networkType(),
                capitalize(dow.name())
        );
    }

    private void verifyMpin(User payer, String mpin) {
        byte[] expected = payer.getMpinHash().getBytes(StandardCharsets.UTF_8);
        byte[] actual = hashMpin(payer.getVpa(), mpin).getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(expected, actual)) {
            throw PaymentException.invalidMpin();
        }
    }

    /** SHA-256(vpa:mpin) hex. Prototype-grade; production would use a KDF. */
    public static String hashMpin(String vpa, String mpin) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest((vpa + ":" + mpin).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static String capitalize(String upper) {
        return upper.charAt(0) + upper.substring(1).toLowerCase();
    }
}
