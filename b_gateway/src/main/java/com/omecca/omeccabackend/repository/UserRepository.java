package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.User;
import com.omecca.omeccabackend.entity.enums.UserStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByUsername(String username);

    boolean existsByUsername(String username);

    List<User> findByStatus(UserStatus status);
}