package com.omecca.omeccabackend.entity;

import com.omecca.omeccabackend.entity.enums.EventType;
import com.omecca.omeccabackend.entity.enums.ObjectClass;
import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "event")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Event {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "cam_id", nullable = false, length = 50)
    private String camId;

    @Column(name = "track_id", length = 50)
    private String trackId;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false)
    private EventType eventType;

    @Enumerated(EnumType.STRING)
    @Column(name = "object_class", nullable = false)
    private ObjectClass objectClass;

    // bbox 좌표 4개 컬럼 (원래 설계 기준)
    @Column(name = "bbox_x")
    private Integer bboxX;
    @Column(name = "bbox_y")
    private Integer bboxY;
    @Column(name = "bbox_w")
    private Integer bboxW;
    @Column(name = "bbox_h")
    private Integer bboxH;

    @Column(precision = 4, scale = 3)
    private BigDecimal confidence;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @Column(name = "received_at", nullable = false)
    private LocalDateTime receivedAt;

    // 위치 좌표 (원래 설계 기준 - 문자열이 아닌 위경도)
    private BigDecimal lat;
    private BigDecimal lng;

    @Column(name = "is_registered_target", nullable = false)
    @Builder.Default
    private Boolean isRegisteredTarget = false;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "target_id")
    private Target target;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "roi_id")
    private Roi roi;

    // 이벤트 유형별 가변 필드 (plateNumber, matchedDbId, faceMatchScore,
    // stationaryDurationSec, trajectoryFeatures 등) - JSON 문자열로 저장
    @Column(columnDefinition = "JSON")
    private String meta;

    @Column(name = "frame_ref_before")
    private String frameRefBefore;

    @Column(name = "frame_ref_after")
    private String frameRefAfter;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
        if (this.receivedAt == null) {
            this.receivedAt = LocalDateTime.now();
        }
        if (this.isRegisteredTarget == null) {
            this.isRegisteredTarget = false;
        }
    }
}
