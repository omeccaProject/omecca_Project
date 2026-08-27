package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.CameraCreateRequest;
import com.omecca.omeccabackend.dto.CameraResponse;
import com.omecca.omeccabackend.dto.CameraUpdateRequest;
import com.omecca.omeccabackend.entity.Camera;
import com.omecca.omeccabackend.entity.enums.CameraStatus;
import com.omecca.omeccabackend.repository.CameraRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CameraService {

    private static final Set<String> ALLOWED_VIDEO_EXTENSIONS = Set.of("mp4", "webm", "mov");

    private final CameraRepository cameraRepository;

    // 업로드된 동영상 파일을 저장할 디렉터리. "동영상을 CCTV로 등록"할 때 여기 저장하고
    // StaticResourceConfig가 /media/videos/**로 그대로 서빙한다.
    @Value("${app.upload-dir:uploads}")
    private String uploadDir;

    @Transactional
    public CameraResponse create(CameraCreateRequest request) {
        String camId = request.getCamId().trim();
        if (cameraRepository.existsByCamId(camId)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 등록된 cam_id입니다: " + camId);
        }

        // 실시간 영상 URL 없이 등록되는 카메라(아직 실제로 연결 안 된 카메라)는 기본값을
        // INACTIVE로 시작한다 - "미연결"인데 "운영 중"으로 보이는 모순된 상태를 방지하기 위함.
        // URL이 있으면(등록 즉시 실제로 연결 가능하다는 뜻) 기존처럼 ACTIVE로 시작한다.
        boolean hasStream = StringUtils.hasText(request.getStreamUrl());

        Camera camera = Camera.builder()
                .camId(camId)
                .name(request.getName().trim())
                .status(hasStream ? CameraStatus.ACTIVE : CameraStatus.INACTIVE)
                .streamUrl(hasStream ? request.getStreamUrl().trim() : null)
                .streamFormat(StringUtils.hasText(request.getStreamFormat()) ? request.getStreamFormat().trim() : null)
                .debrisDetectionEnabled(Boolean.TRUE.equals(request.getDebrisDetectionEnabled()))
                .violationDetectionEnabled(Boolean.TRUE.equals(request.getViolationDetectionEnabled())
                        || Boolean.TRUE.equals(request.getUturnDetectionEnabled())
                        || Boolean.TRUE.equals(request.getSignalDetectionEnabled()))
                .uturnDetectionEnabled(Boolean.TRUE.equals(request.getUturnDetectionEnabled())
                        || (request.getUturnDetectionEnabled() == null && Boolean.TRUE.equals(request.getViolationDetectionEnabled())))
                .signalDetectionEnabled(Boolean.TRUE.equals(request.getSignalDetectionEnabled())
                        || (request.getSignalDetectionEnabled() == null && Boolean.TRUE.equals(request.getViolationDetectionEnabled())))
                .personRiskDetectionEnabled(Boolean.TRUE.equals(request.getPersonRiskDetectionEnabled()))
                .build();

        return CameraResponse.from(cameraRepository.save(camera));
    }

    @Transactional(readOnly = true)
    public List<CameraResponse> findAll() {
        return cameraRepository.findAll().stream().map(CameraResponse::from).toList();
    }

    @Transactional
    public CameraResponse update(Long id, CameraUpdateRequest request) {
        Camera camera = getCamera(id);

        if (StringUtils.hasText(request.getName())) {
            camera.setName(request.getName().trim());
        }
        if (StringUtils.hasText(request.getStatus())) {
            camera.setStatus(parseStatus(request.getStatus()));
        }
        // streamUrl/streamFormat은 빈 문자열을 보내면 "실시간 연결 해제"로 취급해 null로 지운다.
        if (request.getStreamUrl() != null) {
            camera.setStreamUrl(StringUtils.hasText(request.getStreamUrl()) ? request.getStreamUrl().trim() : null);
        }
        if (request.getStreamFormat() != null) {
            camera.setStreamFormat(StringUtils.hasText(request.getStreamFormat()) ? request.getStreamFormat().trim() : null);
        }
        if (request.getDebrisDetectionEnabled() != null) {
            camera.setDebrisDetectionEnabled(request.getDebrisDetectionEnabled());
        }
        if (request.getViolationDetectionEnabled() != null) {
            camera.setViolationDetectionEnabled(request.getViolationDetectionEnabled());
            if (request.getUturnDetectionEnabled() == null) {
                camera.setUturnDetectionEnabled(request.getViolationDetectionEnabled());
            }
            if (request.getSignalDetectionEnabled() == null) {
                camera.setSignalDetectionEnabled(request.getViolationDetectionEnabled());
            }
        }
        if (request.getUturnDetectionEnabled() != null) {
            camera.setUturnDetectionEnabled(request.getUturnDetectionEnabled());
            camera.setViolationDetectionEnabled(
                    Boolean.TRUE.equals(camera.getUturnDetectionEnabled()) || Boolean.TRUE.equals(camera.getSignalDetectionEnabled())
            );
        }
        if (request.getSignalDetectionEnabled() != null) {
            camera.setSignalDetectionEnabled(request.getSignalDetectionEnabled());
            camera.setViolationDetectionEnabled(
                    Boolean.TRUE.equals(camera.getUturnDetectionEnabled()) || Boolean.TRUE.equals(camera.getSignalDetectionEnabled())
            );
        }
        if (request.getPersonRiskDetectionEnabled() != null) {
            camera.setPersonRiskDetectionEnabled(request.getPersonRiskDetectionEnabled());
        }

        return CameraResponse.from(camera);
    }

    // 동영상 파일을 "카메라 등록용 영상 URL"로 쓸 수 있게 서버에 저장하고, StaticResourceConfig가
    // 서빙하는 /media/videos/<파일명> 경로를 돌려준다. 프론트가 이 URL을 그대로 streamUrl에
    // 넣어 카메라를 등록하므로, Camera 엔티티에 별도의 "업로드냐 스트림이냐" 구분 필드는 두지 않는다.
    public String uploadVideo(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "업로드할 파일이 없습니다.");
        }

        String original = StringUtils.hasText(file.getOriginalFilename()) ? file.getOriginalFilename() : "video";
        String ext = original.contains(".") ? original.substring(original.lastIndexOf('.') + 1).toLowerCase() : "";
        if (!ALLOWED_VIDEO_EXTENSIONS.contains(ext)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "지원하지 않는 형식입니다. 허용: " + ALLOWED_VIDEO_EXTENSIONS);
        }

        try {
            Path videosDir = Path.of(uploadDir, "videos").toAbsolutePath().normalize();
            Files.createDirectories(videosDir);

            String filename = UUID.randomUUID() + "." + ext;
            Path target = videosDir.resolve(filename);
            file.transferTo(target);

            return "/media/videos/" + filename;
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "영상 저장에 실패했습니다: " + e.getMessage());
        }
    }

    @Transactional
    public void delete(Long id) {
        Camera camera = getCamera(id);
        cameraRepository.delete(camera);
    }

    private Camera getCamera(Long id) {
        return cameraRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "camera not found"));
    }

    private CameraStatus parseStatus(String value) {
        try {
            return CameraStatus.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid status: " + value);
        }
    }
}