package com.omecca.omeccabackend.dto;

import com.omecca.omeccabackend.entity.Camera;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class CameraResponse {

    private Long id;
    private String camId;
    private String name;
    private String status;
    private String streamUrl;
    private String streamFormat;
    private Boolean debrisDetectionEnabled;
    private Boolean violationDetectionEnabled;
    private LocalDateTime createdAt;

    public static CameraResponse from(Camera camera) {
        return CameraResponse.builder()
                .id(camera.getId())
                .camId(camera.getCamId())
                .name(camera.getName())
                .status(camera.getStatus().name())
                .streamUrl(camera.getStreamUrl())
                .streamFormat(camera.getStreamFormat())
                .debrisDetectionEnabled(camera.getDebrisDetectionEnabled())
                .violationDetectionEnabled(camera.getViolationDetectionEnabled())
                .createdAt(camera.getCreatedAt())
                .build();
    }
}
