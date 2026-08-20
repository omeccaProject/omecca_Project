package com.omecca.omeccabackend.entity;

import com.omecca.omeccabackend.entity.enums.CameraStatus;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 카메라 마스터 데이터. 지금까지는 "cam_id"가 event/roi 테이블에 자유 텍스트로만 존재해서,
 * 실제로 설치된 카메라가 몇 대인지·이름이 뭔지·실시간 영상이 있는지를 시스템이 전혀 몰랐다.
 * 이 테이블이 그 기준 정보를 관리한다.
 *
 * 주의: event.cam_id / roi.cam_id에는 아직 이 테이블을 참조하는 외래키를 걸지 않았다.
 * 팀원 모듈이 이미 자유 문자열로 cam_id를 보내고 있어서, FK를 걸면 여기 등록 안 된
 * cam_id로 오는 이벤트가 전부 저장 실패(외래키 위반)한다. 팀 전체가 실제 쓰는 cam_id
 * 목록을 먼저 확정해서 시드해 넣은 뒤에 FK를 추가하는 게 안전하다.
 */
@Entity
@Table(name = "camera")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Camera {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "cam_id", nullable = false, unique = true, length = 50)
    private String camId;

    @Column(nullable = false, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Builder.Default
    @Column(nullable = false)
    private CameraStatus status = CameraStatus.ACTIVE;

    @Column(name = "stream_url", length = 500)
    private String streamUrl;

    @Column(name = "stream_format", length = 20)
    private String streamFormat;

    // 이 카메라에서 낙하물(DEBRIS) 자동 감지를 돌릴지 여부. true면 camera_watcher.py가
    // yolo_infer.py를 이 카메라의 streamUrl로 자동으로 붙여서 돌린다.
    @Column(name = "debris_detection_enabled", nullable = false)
    @Builder.Default
    private Boolean debrisDetectionEnabled = Boolean.FALSE;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
