package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Target;
import com.omecca.omeccabackend.entity.enums.TargetStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface TargetRepository extends JpaRepository<Target, Long> {

    List<Target> findByStatus(TargetStatus status);

    Page<Target> findByStatus(TargetStatus status, Pageable pageable);

    List<Target> findByPlateNumber(String plateNumber);
}