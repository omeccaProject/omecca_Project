package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.CameraCatalogResponse;
import com.omecca.omeccabackend.service.CameraCatalogService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * UTIC 카메라 사전 등록 카탈로그 검색(자동완성 전용, 읽기 전용). "카메라 관리" 화면에서
 * cam_id/이름을 입력하는 즉시 후보를 찾아 streamUrl을 자동으로 채워주기 위한 API다.
 * /api/cameras와 동일하게 X-API-Key로 보호된다(ApiKeyFilter 기본 동작).
 */
@RestController
@RequestMapping("/api/camera-catalog")
@RequiredArgsConstructor
public class CameraCatalogController {

    private final CameraCatalogService cameraCatalogService;

    @GetMapping
    public List<CameraCatalogResponse> search(@RequestParam(required = false) String query) {
        return cameraCatalogService.search(query);
    }
}
