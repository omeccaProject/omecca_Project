package com.omecca.omeccabackend.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class CameraCreateRequest {

    /** 탐지 모듈이 이벤트에 실어 보내는 cam_id와 일치해야 함 (예: CAM-01, L010263) */
    @NotBlank
    private String camId;

    /** 화면에 보여줄 이름/위치 (예: 이수역, 강남대로 교차로) */
    @NotBlank
    private String name;

    /** 실시간 영상 URL. 아직 실시간 연결이 없으면 비워둠(null) */
    private String streamUrl;

    /** HLS / MP4 등. streamUrl이 없으면 같이 비워둠 */
    private String streamFormat;

    /** 낙하물 자동 감지 사용 여부. 안 보내면 false로 시작 */
    private Boolean debrisDetectionEnabled;

    /** 위반감지(신호위반/불법유턴) 자동 감지 사용 여부 (레거시) */
    private Boolean violationDetectionEnabled;

    /** 불법유턴 자동 감지 사용 여부 */
    private Boolean uturnDetectionEnabled;

    /** 신호위반 자동 감지 사용 여부 */
    private Boolean signalDetectionEnabled;

    /** 수배자/흉기(C파트) 자동 감지 사용 여부. 안 보내면 false로 시작 */
    private Boolean personRiskDetectionEnabled;
}