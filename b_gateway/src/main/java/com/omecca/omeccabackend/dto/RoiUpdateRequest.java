package com.omecca.omeccabackend.dto;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.Getter;
import lombok.Setter;

/**
 * ROI(감지 구역/가상 라인) 수정 요청. 전부 선택값 — 보낸 필드만 갱신한다(부분 수정),
 * CameraUpdateRequest와 동일한 패턴. roiType은 문자열로 받아 서비스에서 RoiType으로 검증/변환한다.
 */
@Getter
@Setter
public class RoiUpdateRequest {
    private String camId;
    private String roiType;
    private String name;
    private JsonNode geometryJson;
}
