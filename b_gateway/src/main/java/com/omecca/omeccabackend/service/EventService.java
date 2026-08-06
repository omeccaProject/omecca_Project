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
