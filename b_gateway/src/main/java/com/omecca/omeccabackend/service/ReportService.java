package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.ReportCreateRequest;
import com.omecca.omeccabackend.dto.ReportResponse;
import com.omecca.omeccabackend.entity.Event;
import com.omecca.omeccabackend.entity.Report;
import com.omecca.omeccabackend.entity.enums.ReportStatus;
import com.omecca.omeccabackend.repository.EventRepository;
import com.omecca.omeccabackend.repository.ReportRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
public class ReportService {

    private final ReportRepository reportRepository;
    private final EventRepository eventRepository;

    @Transactional
    public ReportResponse create(ReportCreateRequest request) {
        Event event = eventRepository.findById(request.getEventId())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "eventId not found"));

        reportRepository.findByEvent_Id(event.getId()).ifPresent(r -> {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "report already exists for event");
        });

        // b_report는 PDF 생성을 마친 뒤 이 API를 호출하는 흐름이므로 기본값은 GENERATED.
        // 비동기 생성 파이프라인으로 바뀌면 PENDING으로 먼저 등록 후 별도 업데이트 API로 전환 가능.
        ReportStatus status = request.getStatus() != null
                ? parseStatus(request.getStatus())
                : ReportStatus.GENERATED;

        Report report = Report.builder()
                .event(event)
                .pdfPath(request.getPdfPath())
                .status(status)
                .generatedAt(status == ReportStatus.GENERATED ? LocalDateTime.now() : null)
                .build();

        return ReportResponse.from(reportRepository.save(report));
    }

    @Transactional(readOnly = true)
    public Page<ReportResponse> findAll(Pageable pageable) {
        return reportRepository.findAll(pageable).map(ReportResponse::from);
    }

    @Transactional(readOnly = true)
    public ReportResponse findById(Long id) {
        return ReportResponse.from(getReport(id));
    }

    @Transactional(readOnly = true)
    public Resource loadPdf(Long id) {
        Report report = getReport(id);
        Path path = Path.of(report.getPdfPath());
        if (!Files.exists(path)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "pdf file not found on disk");
        }
        return new FileSystemResource(path);
    }

    private Report getReport(Long id) {
        return reportRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "report not found"));
    }

    private ReportStatus parseStatus(String value) {
        try {
            return ReportStatus.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid status: " + value);
        }
    }
}
