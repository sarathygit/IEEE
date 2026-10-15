package com.finguard.switchsvc.controller;

import com.finguard.switchsvc.dto.PaymentRequest;
import com.finguard.switchsvc.dto.PaymentResponse;
import com.finguard.switchsvc.entity.TransactionLog;
import com.finguard.switchsvc.repository.TransactionLogRepository;
import com.finguard.switchsvc.repository.UserRepository;
import com.finguard.switchsvc.repository.BalanceRepository;
import com.finguard.switchsvc.service.PaymentService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * REST surface of the Enterprise Switch (architecture step 2).
 * CORS is configured centrally in {@link com.finguard.switchsvc.config.CorsConfig}.
 */
@RestController
@RequestMapping("/api/v1/upi")
public class UpiPaymentController {

    private final PaymentService paymentService;
    private final TransactionLogRepository transactionLogRepository;
    private final UserRepository userRepository;
    private final BalanceRepository balanceRepository;

    public UpiPaymentController(PaymentService paymentService,
                                TransactionLogRepository transactionLogRepository,
                                UserRepository userRepository,
                                BalanceRepository balanceRepository) {
        this.paymentService = paymentService;
        this.transactionLogRepository = transactionLogRepository;
        this.userRepository = userRepository;
        this.balanceRepository = balanceRepository;
    }

    /** The inline-intercepted payment endpoint (architecture steps 2-7). */
    @PostMapping("/pay")
    public ResponseEntity<PaymentResponse> pay(@Valid @RequestBody PaymentRequest request) {
        return ResponseEntity.ok(paymentService.processPayment(request));
    }

    /** Account snapshot for the React viewport (balance + lock state). */
    @GetMapping("/account/{vpa}")
    public ResponseEntity<Map<String, Object>> account(@PathVariable String vpa) {
        return userRepository.findByVpa(vpa)
                .map(user -> {
                    Map<String, Object> body = new LinkedHashMap<>();
                    body.put("vpa", user.getVpa());
                    body.put("fullName", user.getFullName());
                    body.put("bank", user.getBank());
                    body.put("accountLocked", user.isAccountLocked());
                    balanceRepository.findByUserId(user.getId())
                            .ifPresent(b -> body.put("balanceInr", b.getAmountInr()));
                    return ResponseEntity.ok(body);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    /** Recent audit trail for the demo dashboard. */
    @GetMapping("/transactions")
    public List<TransactionLog> recentTransactions() {
        return transactionLogRepository.findTop20ByOrderByCreatedAtDesc();
    }
}
