package com.omecca.omeccabackend.dto;

import com.omecca.omeccabackend.entity.Target;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class TargetResponse {

    private Long id;
    private String targetType;
    private String plateNumber;
    private String personRefId;
    private String label;
    private String color;
    private String vehicleModel;
    private String registeredBy;
    private String status;
    private LocalDateTime createdAt;
    private LocalDateTime closedAt;

    public static TargetResponse from(Target target) {
        return TargetResponse.builder()
                .id(target.getId())
                .targetType(target.getTargetType().name())
                .plateNumber(target.getPlateNumber())
                .personRefId(target.getPersonRefId())
                .label(target.getLabel())
                .color(target.getColor())
                .vehicleModel(target.getVehicleModel())
                .registeredBy(target.getRegisteredBy())
                .status(target.getStatus().name())
                .createdAt(target.getCreatedAt())
                .closedAt(target.getClosedAt())
                .build();
    }
}