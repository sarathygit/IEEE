package com.finguard.switchsvc.repository;

import com.finguard.switchsvc.entity.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByVpa(String vpa);
}
