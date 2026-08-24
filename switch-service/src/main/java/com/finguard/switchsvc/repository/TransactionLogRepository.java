package com.finguard.switchsvc.repository;

import com.finguard.switchsvc.entity.TransactionLog;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface TransactionLogRepository extends JpaRepository<TransactionLog, Long> {

    List<TransactionLog> findTop20ByOrderByCreatedAtDesc();
}
