package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Report;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ReportRepository extends JpaRepository<Report, Long> {
    Optional<Report> findByEvent_Id(Long eventId);

    // [추가] 이벤트를 지우기 전에 그 이벤트를 참조하는 리포트를 먼저 지우기 위한 용도
    // (report.event_id가 FK라서, 리포트가 남아있으면 이벤트 삭제가 외래키 제약 위반으로 실패한다).
    long deleteByEvent_TrackId(String trackId);
}