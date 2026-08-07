package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Report;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ReportRepository extends JpaRepository<Report, Long> {
    Optional<Report> findByEvent_Id(Long eventId);
}
