package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.CameraCreateRequest;
import com.omecca.omeccabackend.dto.CameraResponse;
import com.omecca.omeccabackend.dto.CameraUpdateRequest;
import com.omecca.omeccabackend.entity.Camera;
import com.omecca.omeccabackend.entity.enums.CameraStatus;
import com.omecca.omeccabackend.repository.CameraRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@Service
@RequiredArgsConstructor
public class CameraService {

    private final CameraRepository cameraRepository;

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

        return CameraResponse.from(camera);
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
