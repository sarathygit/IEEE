package com.finguard.switchsvc.service;

import com.finguard.switchsvc.entity.TransactionLog;
import com.finguard.switchsvc.repository.TransactionLogRepository;
import com.finguard.switchsvc.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * Writes that must SURVIVE the fraud rollback.
 *
 * When PaymentService throws FraudulentTransactionException, its transaction
 * (holding the debit/credit) is rolled back. The account lock and the
 * BLOCKED_FRAUD audit row must persist regardless, so they are committed
 * here first, in an independent REQUIRES_NEW transaction that suspends the
 * caller's transaction and commits before the exception is ever thrown.
 */
@Service
public class AccountSecurityService {

    private static final Logger log = LoggerFactory.getLogger(AccountSecurityService.class);

    private final UserRepository userRepository;
    private final TransactionLogRepository transactionLogRepository;

    public AccountSecurityService(UserRepository userRepository,
                                  TransactionLogRepository transactionLogRepository) {
        this.userRepository = userRepository;
        this.transactionLogRepository = transactionLogRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void lockAccountAndRecordBlock(Long userId, TransactionLog blockedLog) {
        userRepository.findById(userId).ifPresent(user -> {
            user.setAccountLocked(true);
            userRepository.save(user);
            log.warn("Account row LOCKED for user id={} vpa={}", user.getId(), user.getVpa());
        });
        transactionLogRepository.save(blockedLog);
    }
}
