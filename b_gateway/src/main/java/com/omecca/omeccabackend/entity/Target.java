package com.omecca.omeccabackend.entity;

import com.omecca.omeccabackend.entity.enums.TargetStatus;
import com.omecca.omeccabackend.entity.enums.TargetType;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "target")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Target {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "target_type", nullable = false)
    private TargetType targetType;

    @Column(name = "plate_number", length = 20)
    private String plateNumber;

    @Column(name = "person_ref_id", length = 50)
    private String personRefId;

    @Column(length = 100)
    private String label;

    /** 차량 색상 (targetType=VEHICLE일 때만 의미 있음). 예: 흰색, 검정, 은색 */
    @Column(name = "color", length = 30)
    private String color;

    /** 차종 - 브랜드/모델/트림까지 구체적으로. 예: 싼타페, 아반떼AD, 아반떼CN7 */
    @Column(name = "vehicle_model", length = 50)
    private String vehicleModel;

    @Column(name = "registered_by", nullable = false, length = 50)
    private String registeredBy;

    @Enumerated(EnumType.STRING)
    @Builder.Default
    @Column(nullable = false)
    private TargetStatus status = TargetStatus.ACTIVE;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "closed_at")
    private LocalDateTime closedAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
