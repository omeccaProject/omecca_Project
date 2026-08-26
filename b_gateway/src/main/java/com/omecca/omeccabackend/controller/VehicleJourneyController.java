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
 * test_suspicious_driving.py(Python)가 실시간으로 계산하는
 * 관제용 차량 이동 경로(Journey)를 받아서
 * STOMP /topic/cctv/journey 로 실시간 방송한다.
 */
@RestController
@RequestMapping("/api/cctv")
public class VehicleJourneyController {

    private final SimpMessagingTemplate messagingTemplate;

    public VehicleJourneyController(
            SimpMessagingTemplate messagingTemplate
    ) {
        this.messagingTemplate = messagingTemplate;
    }

    /**
     * Python → Spring
     *
     * Python의 test_suspicious_driving.py가
     * 새 여정 시작 / CCTV 이동 / 여정 종료 시 호출한다.
     *
     * POST /api/cctv/journey
     */
    @PostMapping("/journey")
    public Map<String, Object> receive(
            @RequestBody JourneyState payload
    ) {

        // ============================================================
        // 1. Python → Spring 수신 확인
        // ============================================================

        System.out.println(
                "\n=================================================="
        );

        System.out.println(
                "[JOURNEY SERVER] Python Journey 데이터 수신"
        );

        System.out.println(
                "[JOURNEY SERVER] active      = "
                        + payload.getActive()
        );

        System.out.println(
                "[JOURNEY SERVER] camId       = "
                        + payload.getCurrentCamId()
        );

        System.out.println(
                "[JOURNEY SERVER] camName     = "
                        + payload.getCurrentCamName()
        );

        System.out.println(
                "[JOURNEY SERVER] latitude    = "
                        + payload.getCurrentLat()
        );

        System.out.println(
                "[JOURNEY SERVER] longitude   = "
                        + payload.getCurrentLng()
        );

        System.out.println(
                "[JOURNEY SERVER] pointCount  = "
                        + (
                            payload.getPoints() != null
                                ? payload.getPoints().size()
                                : 0
                        )
        );

        // ============================================================
        // 2. 실제 Polyline 좌표 확인
        // ============================================================

        if (payload.getPoints() != null) {

            for (int i = 0; i < payload.getPoints().size(); i++) {

                LatLng point = payload.getPoints().get(i);

                System.out.println(
                        "[JOURNEY SERVER] point["
                                + i
                                + "] = lat:"
                                + point.getLat()
                                + ", lng:"
                                + point.getLng()
                );
            }
        }

        // ============================================================
        // 3. Spring → Browser STOMP 방송
        // ============================================================

        messagingTemplate.convertAndSend(
                "/topic/cctv/journey",
                payload
        );

        System.out.println(
                "[JOURNEY SERVER] STOMP 방송 완료"
        );

        System.out.println(
                "[JOURNEY SERVER] topic = /topic/cctv/journey"
        );

        System.out.println(
                "==================================================\n"
        );

        // ============================================================
        // 4. Python에 응답
        // ============================================================

        return Map.of(
                "ok",
                true,

                "active",
                Boolean.TRUE.equals(
                        payload.getActive()
                ),

                "pointCount",
                payload.getPoints() != null
                        ? payload.getPoints().size()
                        : 0
        );
    }

    /**
     * ============================================================
     * Journey 상태
     * ============================================================
     */
    @Data
    public static class JourneyState {

        /**
         * 현재 여정이 진행 중인지 여부
         *
         * true  → 차량 표시
         * false → 차량/Polyline 제거
         */
        private Boolean active;

        /**
         * 현재 차량이 위치한 CCTV
         */
        private String currentCamId;

        private String currentCamName;

        /**
         * 현재 차량 위치
         *
         * CCTV 설치 위치를 차량 위치로 사용
         */
        private Double currentLat;

        private Double currentLng;

        /**
         * 지금까지 누적된 전체 차량 이동 경로
         *
         * [
         *   { lat: ..., lng: ... },
         *   { lat: ..., lng: ... },
         *   ...
         * ]
         *
         * 프론트에서는 이 배열을 Leaflet Polyline으로 표시한다.
         */
        private List<LatLng> points;
    }

    /**
     * ============================================================
     * 위도 / 경도 좌표
     * ============================================================
     */
    @Data
    public static class LatLng {

        private Double lat;

        private Double lng;
    }
}