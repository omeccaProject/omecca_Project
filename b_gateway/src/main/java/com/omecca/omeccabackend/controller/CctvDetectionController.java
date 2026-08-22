package com.omecca.omeccabackend.controller;

import lombok.Data;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * YOLO/ByteTrack(Python, e_tracking)이 프레임마다 보내는 차량 bbox를 실시간으로
 * 그대로 방송만 하는 endpoint. /api/events(EventController)와는 완전히 별개다:
 *
 *   - DB에 저장하지 않는다. 초당 수십 건씩 오는 "지금 이 순간의 화면 위치" 데이터라
 *     event 테이블(영구 사건 기록)에 어울리지 않고, 저장하면 테이블이 순식간에
 *     도배된다.
 *   - eventType/objectClass 같은 사건 분류도 하지 않는다 - "차량이 있다"는 사실이
 *     아니라 "지금 어디 있는지" 좌표만 전달하는 순수 스트리밍 채널이다.
 *
 * 대시보드(React)는 이미 같은 STOMP 브로커(/ws, WebSocketConfig 참고)에 연결돼
 * 있으므로, 새 WebSocket 서버를 만들지 않고 topic만 하나(/topic/cctv/detections)
 * 추가한다 - useEventSocket.js가 쓰는 것과 같은 소켓을 그대로 재사용한다.
 *
 * X-API-Key 필요(ApiKeyFilter가 /api/** 전체를 이미 검사하고 있어서 별도 설정 불필요).
 */
@RestController
@RequestMapping("/api/cctv")
public class CctvDetectionController {

    private final SimpMessagingTemplate messagingTemplate;

    public CctvDetectionController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    // 1프레임 = 1회 호출(배치) - 차량마다 따로 POST하면 연결이 너무 잦아져서
    // (예: 6대 x 30fps = 초당 180회) 비효율적이므로, 그 프레임에서 감지된 전체
    // 차량 목록을 한 번에 받는다. Python 쪽도 이 형태로 한 번만 보내도록 맞췄다.
    @PostMapping("/detections")
    public Map<String, Object> receive(@RequestBody DetectionBatch payload) {
        messagingTemplate.convertAndSend("/topic/cctv/detections", payload);
        return Map.of("ok", true, "count", payload.getDetections() != null ? payload.getDetections().size() : 0);
    }

    @Data
    public static class DetectionBatch {
        private String camId;
        private Integer frameWidth;  // Python 영상 프레임의 실제 픽셀 너비 (프론트에서 bbox 스케일링에 사용)
        private Integer frameHeight;
        private List<Detection> detections;
    }

    @Data
    public static class Detection {
        private Integer trackId;
        private Bbox bbox;
    }

    @Data
    public static class Bbox {
        private Double x1;
        private Double y1;
        private Double x2;
        private Double y2;
    }
}