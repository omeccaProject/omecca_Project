package com.omecca.omeccabackend.dto;

import lombok.Getter;
import lombok.Setter;

/**
 * 카메라 수정 요청. 전부 선택값 — 보낸 필드만 갱신한다(부분 수정).
 * status는 문자열로 받아 서비스에서 CameraStatus로 검증/변환한다.
 */
@Getter
@Setter
public class CameraUpdateRequest {
    private String name;
    private String status;
    private String streamUrl;
    private String streamFormat;
}
