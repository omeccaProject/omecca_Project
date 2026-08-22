package com.omecca.omeccabackend.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.omecca.omeccabackend.dto.EventCreateRequest;
import com.omecca.omeccabackend.dto.EventResponse;
import com.omecca.omeccabackend.entity.Event;
import com.omecca.omeccabackend.entity.Roi;
import com.omecca.omeccabackend.entity.Target;
import com.omecca.omeccabackend.entity.enums.EventType;
import com.omecca.omeccabackend.entity.enums.ObjectClass;
import com.omecca.omeccabackend.repository.EventRepository;
import com.omecca.omeccabackend.repository.ReportRepository;
import com.omecca.omeccabackend.repository.RoiRepository;
import com.omecca.omeccabackend.repository.TargetRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@RequiredArgsConstructor
public class EventService {

    private final EventRepository eventRepository;
    private final ReportRepository reportRepository;
    private final TargetRepository targetRepository;
    private final RoiRepository roiRepository;
    private final SimpMessagingTemplate messagingTemplate;
    private final ObjectMapper objectMapper;

    @Transactional
    public EventResponse create(EventCreateRequest request) {
        EventType eventType = parseEnum(EventType.class, request.getEventType(), "eventType");
        ObjectClass objectClass = parseEnum(ObjectClass.class, request.getObjectClass(), "objectClass");

        Target target = null;
        if (request.getTargetId() != null) {
            target = targetRepository.findById(request.getTargetId())
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "targetId not found"));
        }

        Roi roi = null;
        if (request.getRoiId() != null) {
            roi = roiRepository.findById(request.getRoiId())
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "roiId not found"));
        }

        Integer[] bbox = request.getBbox();
        if (bbox != null && bbox.length != 4) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bbox must have exactly 4 elements [x,y,w,h]");
        }

        Event event = Event.builder()
                .camId(request.getCamId())
                .trackId(request.getTrackId())
                .eventType(eventType)
                .objectClass(objectClass)
                .bboxX(bbox != null ? bbox[0] : null)
                .bboxY(bbox != null ? bbox[1] : null)
                .bboxW(bbox != null ? bbox[2] : null)
                .bboxH(bbox != null ? bbox[3] : null)
                .confidence(request.getConfidence())
                .occurredAt(request.getOccurredAt())
                .lat(request.getLocation() != null ? request.getLocation().getLat() : null)
                .lng(request.getLocation() != null ? request.getLocation().getLng() : null)
                .isRegisteredTarget(Boolean.TRUE.equals(request.getIsRegisteredTarget()))
                .target(target)
                .roi(roi)
                .meta(toJson(request.getMeta()))
                .frameRefBefore(request.getFrameRefBefore())
                .frameRefAfter(request.getFrameRefAfter())
                .build();

        Event saved = eventRepository.save(event);
        EventResponse response = EventResponse.from(saved, objectMapper);
        messagingTemplate.convertAndSend("/topic/events", response);

        return response;
    }

    @Transactional(readOnly = true)
    public Page<EventResponse> findAll(String camId, String eventTypeParam, Pageable pageable) {
        EventType eventType = null;
        if (eventTypeParam != null && !eventTypeParam.isBlank()) {
            eventType = parseEnum(EventType.class, eventTypeParam, "eventType");
        }
        return eventRepository.findByFilters(emptyToNull(camId), eventType, pageable)
                .map(e -> EventResponse.from(e, objectMapper));
    }

    @Transactional(readOnly = true)
    public EventResponse findById(Long id) {
        Event event = eventRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "event not found"));
        return EventResponse.from(event, objectMapper);
    }

    // [추가] Forza DEMO처럼 "새로고침할 때마다 같은 시나리오가 반복 재생"되는 차량(trackId)의
    // 이전 기록을 지우고, 그 자리에 새 이벤트를 다시 만드는 용도(e_tracking/gatewayForward.js가
    // POST 직전에 호출). trackId가 비어있으면 아무것도 지우지 않는다(전체 삭제 방지 안전장치).
    //
    // [버그 수정: HTTP 500] report.event_id가 FK(nullable=false)라서, 그 이벤트로 PDF
    // 리포트를 한 번이라도 생성한 적이 있으면 이벤트를 먼저 지우려 할 때 외래키 제약
    // 위반으로 실패했다(500). 이벤트를 지우기 전에 그 이벤트를 참조하는 리포트부터 먼저
    // 지운다 - 순서가 중요하다(리포트 먼저, 이벤트 나중).
    //
    // [버그 수정: "새로고침해도 이벤트가 안 사라지는 문제" - 근본 원인] 지금까지는 삭제를
    // DB에서만 하고 아무 신호도 안 보냈다. 대시보드(b_dashboard)는 "새 이벤트가 생겼다"는
    // WebSocket 알림만 받을 뿐, "이벤트가 지워졌다"는 알림을 받을 방법이 전혀 없었다 -
    // 그래서 대시보드가 자기 페이지 로드 시점에 딱 한 번 GET한 옛날 목록을 계속 화면에
    // 들고 있었고, 그 GET이 우연히 이 삭제보다 먼저 끝나면 지워진 이벤트가 그대로
    // 남아있는 것처럼 보였다(타이밍에 따라 결과가 들쭉날쭉했던 이유). 이제 삭제할 때도
    // /topic/events/deleted로 방송해서, 대시보드가 실시간으로 화면에서 직접 제거하도록
    // 만든다 - GET 타이밍에 더 이상 의존하지 않는다.
    @Transactional
    public long deleteByTrackId(String trackId) {
        if (trackId == null || trackId.isBlank()) {
            return 0;
        }
        reportRepository.deleteByEvent_TrackId(trackId);
        long deletedCount = eventRepository.deleteByTrackId(trackId);
        if (deletedCount > 0) {
            messagingTemplate.convertAndSend(
                    "/topic/events/deleted",
                    java.util.Map.of("trackId", trackId, "deletedCount", deletedCount)
            );
        }
        return deletedCount;
    }

    private String emptyToNull(String value) {
        return (value == null || value.isBlank()) ? null : value;
    }

    private <E extends Enum<E>> E parseEnum(Class<E> type, String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, fieldName + " is required");
        }
        try {
            return Enum.valueOf(type, value.trim().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid " + fieldName + ": " + value);
        }
    }

    private String toJson(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(node);
        } catch (JsonProcessingException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid json field: meta");
        }
    }
}