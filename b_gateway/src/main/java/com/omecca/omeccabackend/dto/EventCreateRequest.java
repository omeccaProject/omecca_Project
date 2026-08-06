package com.omecca.omeccabackend.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 공통 이벤트 스키마 규격서와 1:1로 매핑되는 요청 DTO.
 * {
 *   "camId": "...", "trackId": "...", "eventType": "...", "objectClass": "...",
 *   "bbox": [x, y, w, h], "confidence": 0.93, "occurredAt": "...",
 *   "location": { "lat": .., "lng": .. },
 *   "isRegisteredTarget": false, "targetId": null, "roiId": null,
 *   "meta": { ... }, "frameRefBefore": "...", "frameRefAfter": "..."
 * }
 */
@Getter
@Setter
public class EventCreateRequest {

    @NotBlank
    private String camId;

    private String trackId;

    @NotBlank
    private String eventType;

    @NotBlank
    private String objectClass;

    /** [x, y, w, h] 형태의 4개 정수 배열 */
    private Integer[] bbox;

    private BigDecimal confidence;

    @NotNull
    private LocalDateTime occurredAt;

    private LocationDto location;

    private Boolean isRegisteredTarget;

    private Long targetId;

    private Long roiId;

    private JsonNode meta;

    private String frameRefBefore;

    private String frameRefAfter;
}
