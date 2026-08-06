package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.ReportCreateRequest;
import com.omecca.omeccabackend.dto.ReportResponse;
import com.omecca.omeccabackend.service.ReportService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/reports")
@RequiredArgsConstructor
public class ReportController {

    private final ReportService reportService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ReportResponse create(@Valid @RequestBody ReportCreateRequest request) {
        return reportService.create(request);
    }

    @GetMapping
    public Page<ReportResponse> list(
            @PageableDefault(size = 20, sort = "generatedAt", direction = Sort.Direction.DESC) Pageable pageable
    ) {
        return reportService.findAll(pageable);
    }

    @GetMapping("/{id}")
    public ReportResponse get(@PathVariable Long id) {
        return reportService.findById(id);
    }

    @GetMapping("/{id}/download")
    public ResponseEntity<Resource> download(@PathVariable Long id) {
        Resource resource = reportService.loadPdf(id);
        String filename = resource.getFilename() != null ? resource.getFilename() : ("report-" + id + ".pdf");

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .contentType(MediaType.APPLICATION_PDF)
                .body(resource);
    }
}
