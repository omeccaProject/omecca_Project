package com.omecca.omeccabackend.entity;

import com.omecca.omeccabackend.entity.enums.ReportStatus;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "report")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Report {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "event_id", nullable = false, unique = true)
    private Event event;

    @Column(name = "pdf_path", nullable = false)
    private String pdfPath;

    @Enumerated(EnumType.STRING)
    @Builder.Default
    @Column(nullable = false)
    private ReportStatus status = ReportStatus.PENDING;

    @Column(name = "generated_at")
    private LocalDateTime generatedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
