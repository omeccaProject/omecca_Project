package com.omecca.omeccabackend.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.omecca.omeccabackend.entity.Camera;
import com.omecca.omeccabackend.entity.Event;
import com.omecca.omeccabackend.entity.Report;
import com.omecca.omeccabackend.repository.CameraRepository;
import com.omecca.omeccabackend.repository.EventRepository;
import com.omecca.omeccabackend.repository.ReportRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * 대시보드 상세화면의 "📄 PDF 리포트 생성" 버튼이 눌렸을 때, b_report(파이썬 CLI)를
 * 그 자리에서 실행해 실제 PDF를 만들고 바로 다운로드시켜주는 서비스.
 *
 * 원래는 이벤트가 생성될 때마다 자동으로(백그라운드에서) 리포트를 만들게 했었는데,
 * 기획서 방향("상세화면에서 전/후 이미지·위치 확인하고 PDF 바로 출력")과 안 맞아서
 * "관제요원이 버튼을 눌렀을 때만" 생성하는 방식으로 바꿨다 - 그래서 여기엔 @Async나
 * 이벤트 리스너가 없고, 컨트롤러가 이 메서드를 직접 호출해서 끝날 때까지 기다린다
 * (사용자가 버튼 누르고 결과를 기다리는 흐름이라 동기 처리가 오히려 맞다).
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ReportGenerationService {

    private final EventRepository eventRepository;
    private final ReportRepository reportRepository;
    private final CameraRepository cameraRepository;
    private final ObjectMapper objectMapper;

    @Value("${report.generation.enabled:true}")
    private boolean enabled;

    // b_gateway 실행 위치(보통 b_gateway/) 기준 상대경로. omecca_Project 하위에
    // b_gateway/b_report/b_dashboard가 형제 폴더라는 구조를 그대로 가정한다.
    @Value("${report.generation.project-dir:../b_report}")
    private String projectDir;

    // frameRefBefore/After 값("mock/sample_before_1.jpg" 같은 상대경로)을 실제 파일로
    // 풀어낼 때 기준이 되는 디렉터리 - 대시보드가 <img src="/mock/..."> 로 보여주는 것과
    // 같은 파일을 b_report가 OpenCV로 읽어야 하기 때문. 실제 탐지 모듈이 캡쳐 이미지를
    // 다른 곳에 저장하게 되면 이 값만 환경변수(REPORT_FRAME_BASE_DIR)로 바꿔주면 된다.
    @Value("${report.generation.frame-base-dir:../b_dashboard/public}")
    private String frameBaseDir;

    @Value("${report.generation.gateway-url:http://localhost:8080}")
    private String gatewayUrl;

    @Value("${report.generation.python-executable:python3}")
    private String pythonExecutableConfig;

    private static final Map<String, String> EVENT_TITLE_KO = Map.of(
            "WANTED_PERSON", "수배자 인식",
            "WEAPON", "흉기 인식",
            "UNREGISTERED_VEHICLE", "미등록 차량",
            "DEBRIS", "도로 낙하물",
            "DUI_PATTERN", "음주운전 의심",
            "SIGNAL_VIOLATION", "신호 위반",
            "UTURN_VIOLATION", "불법 유턴"
    );

    /**
     * eventId에 대한 리포트를 반환한다. 이미 생성된 적이 있으면(재클릭 등) 새로 만들지
     * 않고 기존 걸 그대로 재사용한다 - 같은 이벤트/같은 이미지로 다시 만들어봐야 결과가
     * 똑같기 때문에 매번 파이썬 프로세스를 새로 띄울 필요가 없다.
     */
    public Report generateForEvent(Long eventId) {
        Event event = eventRepository.findById(eventId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "event not found"));

        Optional<Report> existing = reportRepository.findByEvent_Id(eventId);
        if (existing.isPresent()) {
            return existing.get();
        }

        if (!enabled) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "리포트 생성 기능이 꺼져 있습니다");
        }

        String before = event.getFrameRefBefore();
        String after = event.getFrameRefAfter();
        if (before == null || before.isBlank() || after == null || after.isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "이 이벤트에는 전/후 이미지가 없어 리포트를 생성할 수 없습니다");
        }

        Path beforePath = Path.of(frameBaseDir, before).toAbsolutePath().normalize();
        Path afterPath = Path.of(frameBaseDir, after).toAbsolutePath().normalize();
        if (!Files.exists(beforePath) || !Files.exists(afterPath)) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
                    "이미지 파일을 찾을 수 없습니다 (before=" + beforePath + ", after=" + afterPath + ")");
        }

        runReportGenerator(event, beforePath, afterPath);

        // b_report가 생성 직후 스스로 POST /api/reports를 호출해서 등록한다 - 그 결과를
        // 다시 조회해서 돌려준다. 혹시라도 등록에 실패했으면(예: 응답 대기 중 타임아웃)
        // 명확한 에러를 던진다.
        return reportRepository.findByEvent_Id(eventId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                        "PDF는 생성됐지만 리포트 등록에 실패했습니다"));
    }

    private void runReportGenerator(Event event, Path beforePath, Path afterPath) {
        List<String> command = buildCommand(event, beforePath, afterPath);
        log.info("[리포트 생성] eventId={} - b_report 호출: {}", event.getId(), String.join(" ", command));

        Process process;
        try {
            ProcessBuilder pb = new ProcessBuilder(command);
            pb.directory(new File(projectDir).getAbsoluteFile());
            pb.redirectErrorStream(true);
            process = pb.start();
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                    "b_report 실행 파일을 찾을 수 없거나 실행할 수 없습니다: " + e.getMessage());
        }

        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append('\n');
            }
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "b_report 출력 읽기 실패: " + e.getMessage());
        }

        boolean finished;
        try {
            // 버튼을 누른 사용자가 화면 앞에서 기다리는 흐름이라 너무 길게 기다리게 하면
            // 안 되지만, PDF 생성(ReportLab)+OpenCV 이미지 처리는 보통 수 초면 끝나므로
            // 30초면 충분히 여유 있는 상한선이다.
            finished = process.waitFor(30, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "리포트 생성이 중단되었습니다");
        }
        if (!finished) {
            process.destroyForcibly();
            throw new ResponseStatusException(HttpStatus.GATEWAY_TIMEOUT, "리포트 생성이 30초를 초과해 중단되었습니다");
        }

        int exitCode = process.exitValue();
        if (exitCode != 0) {
            log.warn("[리포트 생성] eventId={} - 실패(exit={})\n{}", event.getId(), exitCode, output);
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                    "리포트 생성에 실패했습니다 (b_report 종료코드 " + exitCode + ")");
        }
        log.info("[리포트 생성] eventId={} - 성공\n{}", event.getId(), output);
    }

    private List<String> buildCommand(Event event, Path beforePath, Path afterPath) {
        List<String> cmd = new ArrayList<>();
        cmd.add(resolvePythonExecutable());
        cmd.add("-m");
        cmd.add("src.main");
        cmd.add("--event-id");
        cmd.add(String.valueOf(event.getId()));
        cmd.add("--title");
        cmd.add(EVENT_TITLE_KO.getOrDefault(event.getEventType().name(), event.getEventType().name()) + " 증거 리포트");
        cmd.add("--event-type");
        cmd.add(event.getEventType().name());
        cmd.add("--occurred-at");
        cmd.add(event.getOccurredAt().toString());
        cmd.add("--location");
        cmd.add(buildLocationLabel(event));

        String plate = extractPlate(event);
        if (plate != null) {
            cmd.add("--plate");
            cmd.add(plate);
        }
        if (event.getCamId() != null) {
            cmd.add("--cam-id");
            cmd.add(event.getCamId());
        }
        if (event.getTrackId() != null) {
            cmd.add("--track-id");
            cmd.add(event.getTrackId());
        }
        if (event.getConfidence() != null) {
            cmd.add("--confidence");
            cmd.add(event.getConfidence().toString());
        }
        if (event.getBboxX() != null && event.getBboxY() != null && event.getBboxW() != null && event.getBboxH() != null) {
            cmd.add("--bbox");
            cmd.add(String.valueOf(event.getBboxX()));
            cmd.add(String.valueOf(event.getBboxY()));
            cmd.add(String.valueOf(event.getBboxW()));
            cmd.add(String.valueOf(event.getBboxH()));
        }

        cmd.add("--before");
        cmd.add(beforePath.toString());
        cmd.add("--after");
        cmd.add(afterPath.toString());
        cmd.add("--output-dir");
        cmd.add("./output");
        cmd.add("--gateway-url");
        cmd.add(gatewayUrl);
        return cmd;
    }

    // 대시보드 상세화면(EventDetailModal.jsx)과 같은 이유로 같은 방식을 씀: a_core가
    // 위경도(lat/lng)를 항상 null로 보내서(위치는 아직 e_tracking 미연동) PDF의
    // "카메라 / 위치"란도 계속 "-"만 찍혔다. 위경도가 없으면 "카메라 관리"에 등록된
    // 카메라 이름(예: "국립국악원")으로 대신 채운다 - 위경도가 실제로 들어오게 되면
    // 그쪽이 그대로 우선된다.
    private String buildLocationLabel(Event event) {
        BigDecimal lat = event.getLat();
        BigDecimal lng = event.getLng();
        if (lat != null && lng != null) {
            return lat.toPlainString() + ", " + lng.toPlainString();
        }
        if (event.getCamId() != null) {
            Optional<Camera> camera = cameraRepository.findByCamId(event.getCamId());
            if (camera.isPresent() && camera.get().getName() != null && !camera.get().getName().isBlank()) {
                return camera.get().getName();
            }
        }
        return "-";
    }

    private String extractPlate(Event event) {
        if (event.getMeta() == null) {
            return null;
        }
        JsonNode metaNode;
        try {
            metaNode = objectMapper.readTree(event.getMeta());
        } catch (Exception e) {
            return null;
        }
        for (String key : new String[]{"plateNumber", "licensePlate", "plate"}) {
            if (metaNode.hasNonNull(key)) {
                return metaNode.get(key).asText();
            }
        }
        return null;
    }

    // b_report/.venv 안에 가상환경이 만들어져 있으면(README 설치 가이드대로 세팅한 경우)
    // 그 안의 파이썬을 우선 사용한다 - opencv-python-headless/reportlab 등 의존성이
    // 시스템 파이썬에는 없을 가능성이 커서다. 없으면 설정된 기본값(python3)으로 폴백.
    private String resolvePythonExecutable() {
        Path venvPython = Path.of(projectDir, ".venv", "bin", "python3").toAbsolutePath().normalize();
        if (Files.isExecutable(venvPython)) {
            return venvPython.toString();
        }
        Path venvPythonAlt = Path.of(projectDir, ".venv", "bin", "python").toAbsolutePath().normalize();
        if (Files.isExecutable(venvPythonAlt)) {
            return venvPythonAlt.toString();
        }
        return pythonExecutableConfig;
    }
}
