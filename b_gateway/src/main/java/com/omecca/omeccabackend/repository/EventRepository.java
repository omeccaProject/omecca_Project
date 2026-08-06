package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Event;
import com.omecca.omeccabackend.entity.enums.EventType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EventRepository extends JpaRepository<Event, Long> {

    @Query("""
            SELECT e FROM Event e
            WHERE (:camId IS NULL OR e.camId = :camId)
              AND (:eventType IS NULL OR e.eventType = :eventType)
            """)
    Page<Event> findByFilters(
            @Param("camId") String camId,
            @Param("eventType") EventType eventType,
            Pageable pageable
    );

    // 특정 관심 대상(target)의 사건 타임라인
    Page<Event> findByTarget_IdOrderByOccurredAtAsc(Long targetId, Pageable pageable);
}
