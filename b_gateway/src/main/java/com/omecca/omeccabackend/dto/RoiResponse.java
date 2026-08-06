package com.omecca.omeccabackend.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.omecca.omeccabackend.entity.Roi;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class RoiResponse {

    private Long id;
    private String camId;
    private String roiType;
    private String name;
    private JsonNode geometryJson;
    private LocalDateTime createdAt;

    public static RoiResponse from(Roi roi, ObjectMapper objectMapper) {
        JsonNode geometryNode = null;
        if (roi.getGeometryJson() != null) {
            try {
                geometryNode = objectMapper.readTree(roi.getGeometryJson());
            } catch (Exception ignored) {
                // 저장된 geometry가 손상된 경우 null로 반환 (조회 자체는 막지 않음)
            }
        }

        return RoiResponse.builder()
                .id(roi.getId())
                .camId(roi.getCamId())
                .roiType(roi.getRoiType().name())
                .name(roi.getName())
                .geometryJson(geometryNode)
                .createdAt(roi.getCreatedAt())
                .build();
    }
}