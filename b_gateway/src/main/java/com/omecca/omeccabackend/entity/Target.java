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
