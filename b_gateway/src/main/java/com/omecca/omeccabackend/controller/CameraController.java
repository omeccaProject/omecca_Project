package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.CameraCreateRequest;
import com.omecca.omeccabackend.dto.CameraResponse;
import com.omecca.omeccabackend.dto.CameraUpdateRequest;
import com.omecca.omeccabackend.service.CameraService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

/**
 * 카메라 마스터 데이터 CRUD. 실제로 설치된 카메라가 뭐가 있는지/실시간 영상이 연결돼
 * 있는지를 여기서 관리한다. b_gateway의 다른 등록형 API(target/roi)와 동일하게
 * X-API-Key로 보호된다(ApiKeyFilter 기본 동작 — 별도 설정 추가 안 함).
 */
@RestController
@RequestMapping("/api/cameras")
@RequiredArgsConstructor
public class CameraController {

    private final CameraService cameraService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public CameraResponse create(@Valid @RequestBody CameraCreateRequest request) {
        return cameraService.create(request);
    }

    @GetMapping
    public List<CameraResponse> list() {
        return cameraService.findAll();
    }

    // 동영상 파일을 업로드해서 카메라 등록용 URL을 발급받는다. 프론트는 이 URL을 그대로
    // CameraCreateRequest.streamUrl에 넣어 "카메라"로 등록한다 - 실시간 스트림과 동일하게 취급.
    @PostMapping("/upload")
    public Map<String, String> upload(@RequestParam("file") MultipartFile file) {
        String url = cameraService.uploadVideo(file);
        return Map.of("url", url);
    }

    @PatchMapping("/{id}")
    public CameraResponse update(@PathVariable Long id, @RequestBody CameraUpdateRequest request) {
        return cameraService.update(id, request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        cameraService.delete(id);
    }
}
