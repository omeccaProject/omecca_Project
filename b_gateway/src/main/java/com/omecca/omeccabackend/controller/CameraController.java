package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.CameraCreateRequest;
import com.omecca.omeccabackend.dto.CameraResponse;
import com.omecca.omeccabackend.dto.CameraUpdateRequest;
import com.omecca.omeccabackend.service.CameraService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

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
