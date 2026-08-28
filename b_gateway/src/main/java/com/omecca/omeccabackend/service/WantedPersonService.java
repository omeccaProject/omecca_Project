package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.WantedPersonResponse;
import com.omecca.omeccabackend.entity.User;
import com.omecca.omeccabackend.entity.WantedPerson;
import com.omecca.omeccabackend.entity.enums.WantedPersonStatus;
import com.omecca.omeccabackend.repository.UserRepository;
import com.omecca.omeccabackend.repository.WantedPersonRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/**
 * 수배자 얼굴 등록 서비스.
 *
 * 등록 흐름 (등록 API를 부를 때마다 매번):
 *   1. 원본 사진을 uploadDir/wanted/ 에 저장 (감사 목적 - 나중에 "그때 등록한 사진"을
 *      그대로 다시 볼 수 있어야 하므로 known_faces/ 원본과는 별도로 보관)
 *   2. WantedPerson row를 PENDING 상태로 먼저 저장 (등록 시도 자체의 기록을 남김 -
 *      아래 3번이 실패해도 "누가 언제 어떤 사진으로 시도했는지"는 사라지지 않는다)
 *   3. c_person_risk/register_single_face.py를 서브프로세스로 동기 실행해서
 *      known_faces/에 사진을 정식 등록 + face_embeddings.pkl에 임베딩 append
 *   4. 3번 종료 코드로 REGISTERED/FAILED 확정, stderr는 failureReason으로 저장
 *
 * camera_watcher.py(파이썬)가 "지속 실행 프로세스"를 관리하는 것과 달리, 이건 "1회성
 * 실행 후 종료"라 별도 워처 없이 이 서비스가 직접 ProcessBuilder로 동기 호출하고
 * 끝날 때까지 기다린다(타임아웃 30초 - cnn 폴백까지 가면 몇 초 걸릴 수 있어 여유를 둠).
 */
@Service
@RequiredArgsConstructor
public class WantedPersonService {

    private static final Set<String> ALLOWED_IMAGE_EXTENSIONS = Set.of("jpg", "jpeg", "png");

    private final WantedPersonRepository wantedPersonRepository;
    private final UserRepository userRepository;

    @Value("${app.upload-dir:uploads}")
    private String uploadDir;

    // b_report의 REPORT_PROJECT_DIR/REPORT_PYTHON_EXECUTABLE과 동일한 설정 패턴.
    @Value("${app.wanted-person.project-dir:../c_person_risk}")
    private String pythonProjectDir;

    // [중요] 이 값을 그냥 "python"/"python3"로 두면, 자바 프로세스는 venv라는 개념을
    // 몰라서 시스템 기본 파이썬을 그대로 실행한다 - face_recognition이 venv 안에만
    // 설치돼 있으면 여기서도 "ModuleNotFoundError: No module named 'face_recognition'"가
    // 그대로 재현된다(camera_watcher.py를 venv 활성화 없이 실행했을 때 겪었던 것과 동일한
    // 원인). 반드시 .env에 venv 파이썬의 절대경로를 넣어야 한다:
    //   WANTED_PERSON_PYTHON_EXECUTABLE=C:\Users\본인계정\Desktop\lastpj\omecca_Project\venv\Scripts\python.exe
    // (DB_USERNAME/DB_PASSWORD처럼 팀 공용 값이 아니라 본인 로컬 경로이므로 각자 .env에 설정)
    @Value("${app.wanted-person.python-executable:python}")
    private String pythonExecutable;

    @Transactional
    public WantedPersonResponse register(String wantedId, String name, MultipartFile file, Long currentUserId) {
        String trimmedId = wantedId.trim();
        String trimmedName = name.trim();

        if (wantedPersonRepository.existsByWantedId(trimmedId)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 등록된 수배자 ID입니다: " + trimmedId);
        }
        // known_faces 파일명 파싱 규칙(build_face_db.py)이 "_"로 분리해 id/name을 꺼내므로,
        // 이름에 "_"가 들어가면 등록 자체는 되지만 나중에 known_faces 폴더를 build_face_db.py로
        // 재빌드할 때 이름이 잘못 파싱될 수 있다 - 미리 막아서 혼란을 방지한다.
        if (trimmedName.contains("_")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "이름에 밑줄(_) 문자는 사용할 수 없습니다.");
        }
        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "등록할 사진이 없습니다.");
        }

        String original = StringUtils.hasText(file.getOriginalFilename()) ? file.getOriginalFilename() : "photo";
        String ext = original.contains(".") ? original.substring(original.lastIndexOf('.') + 1).toLowerCase() : "";
        if (!ALLOWED_IMAGE_EXTENSIONS.contains(ext)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "지원하지 않는 이미지 형식입니다. 허용: " + ALLOWED_IMAGE_EXTENSIONS);
        }

        String registeredByName = userRepository.findById(currentUserId)
                .map(User::getName)
                .orElse(null);

        Path savedPhotoPath;
        String photoUrl;
        try {
            Path wantedDir = Path.of(uploadDir, "wanted").toAbsolutePath().normalize();
            Files.createDirectories(wantedDir);
            String storedFilename = UUID.randomUUID() + "." + ext;
            savedPhotoPath = wantedDir.resolve(storedFilename);
            file.transferTo(savedPhotoPath);
            photoUrl = "/media/wanted/" + storedFilename;
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "사진 저장에 실패했습니다: " + e.getMessage());
        }

        WantedPerson entity = WantedPerson.builder()
                .wantedId(trimmedId)
                .name(trimmedName)
                .photoUrl(photoUrl)
                .status(WantedPersonStatus.PENDING)
                .registeredBy(currentUserId)
                .registeredByName(registeredByName)
                .build();
        entity = wantedPersonRepository.save(entity);

        runEmbeddingScript(entity, trimmedId, trimmedName, savedPhotoPath);

        return WantedPersonResponse.from(entity);
    }

    private void runEmbeddingScript(WantedPerson entity, String wantedId, String name, Path photoPath) {
        List<String> command = List.of(
                pythonExecutable, "register_single_face.py",
                "--id", wantedId,
                "--name", name,
                "--photo", photoPath.toString()
        );
        try {
            Process process = new ProcessBuilder(command)
                    .directory(Path.of(pythonProjectDir).toAbsolutePath().normalize().toFile())
                    .redirectErrorStream(false)
                    .start();

            String stderr = readStream(process.getErrorStream());
            boolean finished = process.waitFor(30, TimeUnit.SECONDS);
            int exitCode = finished ? process.exitValue() : -1;

            if (finished && exitCode == 0) {
                entity.setStatus(WantedPersonStatus.REGISTERED);
                entity.setFailureReason(null);
            } else {
                entity.setStatus(WantedPersonStatus.FAILED);
                entity.setFailureReason(finished
                        ? (StringUtils.hasText(stderr) ? stderr.trim() : "임베딩 생성 실패(원인 불명)")
                        : "임베딩 생성 시간 초과(30초)");
                if (!finished) {
                    process.destroyForcibly();
                }
            }
        } catch (IOException | InterruptedException e) {
            entity.setStatus(WantedPersonStatus.FAILED);
            entity.setFailureReason("스크립트 실행 실패: " + e.getMessage());
            Thread.currentThread().interrupt();
        }
        wantedPersonRepository.save(entity);
    }

    private String readStream(java.io.InputStream is) throws IOException {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) {
            return reader.lines().collect(Collectors.joining("\n"));
        }
    }

    @Transactional(readOnly = true)
    public List<WantedPersonResponse> findAll() {
        return wantedPersonRepository.findAllByOrderByCreatedAtDesc().stream()
                .map(WantedPersonResponse::from)
                .toList();
    }

    @Transactional
    public void delete(Long id) {
        WantedPerson entity = wantedPersonRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "wanted person not found"));

        // face_embeddings.pkl에서도 반드시 같이 지워야 한다 - DB row만 지우면 감지
        // 시스템은 여전히 그 사람을 계속 수배자로 인식한다.
        List<String> command = List.of(pythonExecutable, "remove_face.py", "--id", entity.getWantedId());
        try {
            Process process = new ProcessBuilder(command)
                    .directory(Path.of(pythonProjectDir).toAbsolutePath().normalize().toFile())
                    .start();
            process.waitFor(15, TimeUnit.SECONDS);
        } catch (IOException | InterruptedException e) {
            // pkl에서 제거가 실패해도 DB 기록 삭제는 계속 진행한다(관제요원이 UI에서 삭제를
            // 시도했다는 사실 자체는 남겨야 함) - 대신 로그로 남겨 운영자가 수동 확인하게 한다.
            System.err.println("[WantedPersonService] remove_face.py 실행 실패: " + e.getMessage());
            Thread.currentThread().interrupt();
        }

        if (StringUtils.hasText(entity.getPhotoUrl())) {
            try {
                String filename = entity.getPhotoUrl().substring(entity.getPhotoUrl().lastIndexOf('/') + 1);
                Files.deleteIfExists(Path.of(uploadDir, "wanted", filename).toAbsolutePath().normalize());
            } catch (IOException ignored) {
                // 사진 파일 정리 실패는 치명적이지 않음 - DB 기록 삭제는 계속 진행
            }
        }

        wantedPersonRepository.delete(entity);
    }
}
