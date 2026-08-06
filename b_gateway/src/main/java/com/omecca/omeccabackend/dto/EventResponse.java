package com.omecca.omeccabackend.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.omecca.omeccabackend.entity.Event;
import lombok.Builder;
import lombok.Getter;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Getter
@Builder
public class EventResponse {

    private Long id;
    private String camId;
    private String trackId;
    private String eventType;
    private String objectClass;
    private Integer[] bbox;
    private BigDecimal confidence;
    private LocalDateTime occurredAt;
    private LocalDateTime receivedAt;
    private LocationDto location;
    private Boolean isRegisteredTarget;
    private Long targetId;
    private Long roiId;
    private JsonNode meta;
    private String frameRefBefore;
    private String frameRefAfter;
    private LocalDateTime createdAt;

    public static EventResponse from(Event event, ObjectMapper objectMapper) {
        LocationDto location = null;
        if (event.getLat() != null || event.getLng() != null) {
            location = new LocationDto();
            location.setLat(event.getLat());
            location.setLng(event.getLng());
        }

        JsonNode metaNode = null;
        if (event.getMeta() != null) {
            try {
                metaNode = objectMapper.readTree(event.getMeta());
            } catch (Exception ignored) {
                // 저장된 meta가 손상된 경우 null로 반환 (조회 자체는 막지 않음)
            }
        }

        return EventResponse.builder()
                .id(event.getId())
                .camId(event.getCamId())
                .trackId(event.getTrackId())
                .eventType(event.getEventType().name())
                .objectClass(event.getObjectClass().name())
                .bbox(new Integer[]{event.getBboxX(), event.getBboxY(), event.getBboxW(), event.getBboxH()})
                .confidence(event.getConfidence())
                .occurredAt(event.getOccurredAt())
                .receivedAt(event.getReceivedAt())
                .location(location)
                .isRegisteredTarget(event.getIsRegisteredTarget())
                .targetId(event.getTarget() != null ? event.getTarget().getId() : null)
                .roiId(event.getRoi() != null ? event.getRoi().getId() : null)
                .meta(metaNode)
                .frameRefBefore(event.getFrameRefBefore())
                .frameRefAfter(event.getFrameRefAfter())
                .createdAt(event.getCreatedAt())
                .build();
    }
}
