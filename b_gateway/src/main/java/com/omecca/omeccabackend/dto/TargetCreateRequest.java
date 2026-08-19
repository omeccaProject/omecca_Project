package com.omecca.omeccabackend.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;

/**
 * 관심 대상(target) 등록 요청 DTO.
 * targetType=VEHICLE이면 plateNumber, targetType=PERSON이면 personRefId를 채워야 함
 * (둘 다 필수는 아니지만 최소 하나는 있어야 실제 추적에 쓸 수 있음 — 서비스에서 검증).
 */
@Getter
@Setter
public class TargetCreateRequest {

    /** PERSON / VEHICLE */
    @NotBlank
    private String targetType;

    private String plateNumber;

    private String personRefId;

    private String label;

    /** 차량 색상 (targetType=VEHICLE일 때 선택 입력). 예: 흰색, 검정, 은색 */
    private String color;

    /** 차종 - 구체적으로. 예: 싼타페, 아반떼AD, 아반떼CN7 (targetType=VEHICLE일 때 선택 입력) */
    private String vehicleModel;

    @NotBlank
    private String registeredBy;
}