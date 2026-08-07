package com.omecca.omeccabackend.entity;

import com.omecca.omeccabackend.entity.enums.RoiType;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "roi")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Roi {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "cam_id", nullable = false, length = 50)
    private String camId;

    @Enumerated(EnumType.STRING)
    @Column(name = "roi_type", nullable = false)
    private RoiType roiType;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(name = "geometry_json", nullable = false, columnDefinition = "JSON")
    private String geometryJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
