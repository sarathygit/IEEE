package com.finguard.switchsvc.repository;

import com.finguard.switchsvc.entity.Balance;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface BalanceRepository extends JpaRepository<Balance, Long> {

    /**
     * Acquires the ledger row under a PESSIMISTIC_WRITE (SELECT ... FOR UPDATE)
     * lock. This is the concrete mechanism behind "freezing" the account for
     * the duration of the inline fraud score: no concurrent transaction can
     * touch this balance until the verdict commits or rolls back.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select b from Balance b where b.user.id = :userId")
    Optional<Balance> findByUserIdForUpdate(@Param("userId") Long userId);

    Optional<Balance> findByUserId(Long userId);
}
