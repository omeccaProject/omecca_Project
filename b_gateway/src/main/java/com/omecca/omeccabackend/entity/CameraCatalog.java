package com.omecca.omeccabackend.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * UTIC(서울시 교통정보센터) 카메라 사전 등록 카탈로그. e_tracking/SmartCCTV/web/data/
 * utic-cameras-seoul.json(cam_id·이름·위치, 303대)과 utic-video-sources.json(실제로
 * 확인된 영상 URL)을 한 번 사람이 대조해서, 실시간 영상 URL까지 확인된 카메라만 여기 시드해
 * 둔다("카메라 관리"에서 등록할 카메라 후보 목록 - 실제 등록된 camera 테이블과는 다른 테이블).
 *
 * "카메라 관리" 화면에서 cam_id나 이름을 입력하면 이 테이블을 검색해서 자동완성 추천을 주고,
 * 하나를 고르면 streamUrl/streamFormat이 자동으로 채워진다 - 매번 URL을 직접 복사/붙여넣기
 * 하지 않아도 되게 하는 게 목적이다. camera 테이블에 실제 등록(INSERT)하기 전까지는 여기 있는
 * 카메라도 화면에 아무 영향이 없다(단순 검색용 참조 데이터).
 */
@Entity
@Table(name = "camera_catalog")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CameraCatalog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "cam_id", nullable = false, unique = true, length = 50)
    private String camId;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(name = "stream_url", nullable = false, length = 500)
    private String streamUrl;

    @Column(name = "stream_format", length = 20)
    private String streamFormat;

    /** 영상을 실제로 제공하는 기관/방식. 예: 서울교통정보센터 */
    @Column(name = "source_type", length = 50)
    private String sourceType;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
