package com.omecca.omeccabackend.dto;

import com.omecca.omeccabackend.entity.Report;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class ReportResponse {

    private Long id;
    private Long eventId;
    private String pdfPath;
    private String status;
    private LocalDateTime generatedAt;
    private LocalDateTime createdAt;

    public static ReportResponse from(Report report) {
        return ReportResponse.builder()
                .id(report.getId())
                .eventId(report.getEvent().getId())
                .pdfPath(report.getPdfPath())
                .status(report.getStatus().name())
                .generatedAt(report.getGeneratedAt())
                .createdAt(report.getCreatedAt())
                .build();
    }
}
