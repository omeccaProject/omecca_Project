package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.EventCreateRequest;
import com.omecca.omeccabackend.dto.EventResponse;
import com.omecca.omeccabackend.entity.Report;
import com.omecca.omeccabackend.service.EventService;
import com.omecca.omeccabackend.service.ReportGenerationService;
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
@RequestMapping("/api/events")
@RequiredArgsConstructor
public class EventController {

    private final EventService eventService;
    private final ReportGenerationService reportGenerationService;
    private final ReportService reportService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public EventResponse create(@Valid @RequestBody EventCreateRequest request) {
        return eventService.create(request);
    }

    @GetMapping
    public Page<EventResponse> list(
            @RequestParam(required = false) String camId,
            @RequestParam(required = false) String eventType,
            @PageableDefault(size = 20, sort = "occurredAt", direction = Sort.Direction.DESC) Pageable pageable
    ) {
        return eventService.findAll(camId, eventType, pageable);
    }

    @GetMapping("/{id}")
    public EventResponse get(@PathVariable Long id) {
        return eventService.findById(id);
    }

    // [추가] Forza DEMO 같은 "반복 재생 시나리오" 차량의 이전 기록을 지우고 새로 1건만
    // 남기기 위한 endpoint. e_tracking/gatewayForward.js가 새 이벤트를 POST하기 직전에
    // 이 endpoint를 먼저 호출한다. X-API-Key 필요(ApiKeyFilter가 /api/events/** 전체를 검사).
    @DeleteMapping("/by-track/{trackId}")
    public java.util.Map<String, Object> deleteByTrackId(@PathVariable String trackId) {
        long deletedCount = eventService.deleteByTrackId(trackId);
        return java.util.Map.of("trackId", trackId, "deletedCount", deletedCount);
    }

    // [추가] map.js가 "CCTV 영상 보기"로 연결된 영상에서 캡쳐한 사전/사후 이미지를
    // e_tracking/server가 저장한 뒤 호출하는 endpoint. 이 trackId의 가장 최근 이벤트에
    // frameRefBefore/frameRefAfter만 채워 넣는다(이벤트 자체는 새로 만들지 않음).
    // body: { frameRefBefore?, frameRefAfter? } - 둘 중 하나만 와도 된다.
    @PatchMapping("/by-track/{trackId}/captures")
    public EventResponse updateCaptures(
            @PathVariable String trackId,
            @RequestBody java.util.Map<String, String> body
    ) {
        return eventService.updateCapturesByTrackId(
                trackId,
                body != null ? body.get("frameRefBefore") : null,
                body != null ? body.get("frameRefAfter") : null
        );
    }

    // [신규] e_tracking/test_suspicious_driving.py의 update_event_plate()가 호출한다 -
    // DUI 이벤트가 이미 떠 있는 상태에서 번호판이 나중(다음 카메라)에 확정되면, 새
    // 이벤트를 만들지 않고 이 trackId의 가장 최근 이벤트 meta.plateNumber만 채워 넣는다.
    // body: { plate }.
    @PatchMapping("/by-track/{trackId}/plate")
    public EventResponse updatePlate(
            @PathVariable String trackId,
            @RequestBody java.util.Map<String, String> body
    ) {
        return eventService.updatePlateByTrackId(
                trackId,
                body != null ? body.get("plate") : null
        );
    }

    // 대시보드 "📄 PDF 리포트 생성" 버튼이 호출하는 엔드포인트. b_report를 그 자리에서
    // 실행해 실제 PDF를 만들고(이미 만들어진 적 있으면 그걸 재사용), 완성된 PDF 바이너리를
    // 바로 응답으로 돌려준다 - 프론트는 이 응답 하나로 즉시 다운로드를 트리거하면 된다.
    @PostMapping("/{id}/report")
    public ResponseEntity<Resource> generateReport(@PathVariable Long id) {
        Report report = reportGenerationService.generateForEvent(id);
        Resource resource = reportService.loadPdf(report.getId());
        String filename = resource.getFilename() != null ? resource.getFilename() : ("report-" + report.getId() + ".pdf");

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .contentType(MediaType.APPLICATION_PDF)
                .body(resource);
    }
}