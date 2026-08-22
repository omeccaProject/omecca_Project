package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Event;
import com.omecca.omeccabackend.entity.enums.EventType;
import java.util.Optional;
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

    // [추가] Forza DEMO처럼 "새로고침할 때마다 같은 시나리오가 반복 재생"되는 차량(trackId)의
    // 이전 기록을 지우고 새로 1건만 남기기 위한 용도. 반환값은 실제로 삭제된 행 수.
    long deleteByTrackId(String trackId);

    // [추가] 프론트엔드(map.js)가 "CCTV 영상 보기"로 연결된 영상에서 사전/사후 이미지를
    // 캡쳐한 뒤, 이미 생성되어 있는 이 trackId의 "가장 최근" 이벤트를 찾아서 그 이벤트에
    // frameRefBefore/frameRefAfter를 채워 넣기 위한 조회. 같은 trackId로 여러 건이 있을
    // 수 있으므로(예: 실제 UTIC 반복 감지) 가장 최근 것 하나만 갱신한다.
    Optional<Event> findFirstByTrackIdOrderByOccurredAtDesc(String trackId);
}
