package com.omecca.omeccabackend.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

/**
 * ROI(감지 구역/가상 라인) 등록 요청 DTO.
 * roiType=ZONE → 낙하물/방치물 판정용 정지 구역, roiType=LINE → 신호위반·유턴 판정용 가상 라인.
 */
@Getter
@Setter
public class RoiCreateRequest {

    @NotBlank
    private String camId;

    /** ZONE / LINE */
    @NotBlank
    private String roiType;

    @NotBlank
    private String name;

    /** 좌표 폴리곤(ZONE) 또는 좌표 2점(LINE) 등을 담는 JSON. 형식은 담당 모듈(김관용/박지원)과 합의된 구조 그대로 저장. */
    @NotNull
    private JsonNode geometryJson;
}