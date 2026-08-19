package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.RoiCreateRequest;
import com.omecca.omeccabackend.dto.RoiResponse;
import com.omecca.omeccabackend.dto.RoiUpdateRequest;
import com.omecca.omeccabackend.service.RoiService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/**
 * ROI(감지 구역/가상 라인) 등록·조회 API.
 * 기획서 기능 ⑤ 낙하물 감지(ZONE), 기능 ⑦ 신호위반·유턴 감지(LINE)에서 사용하는 기준 영역을
 * 담당 모듈(김관용/박지원)이 미리 등록해두는 곳.
 */
@RestController
@RequestMapping("/api/rois")
@RequiredArgsConstructor
public class RoiController {

    private final RoiService roiService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public RoiResponse create(@Valid @RequestBody RoiCreateRequest request) {
        return roiService.create(request);
    }

    @GetMapping
    public Page<RoiResponse> list(
            @RequestParam(required = false) String camId,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable
    ) {
        return roiService.findAll(camId, pageable);
    }

    @GetMapping("/{id}")
    public RoiResponse get(@PathVariable Long id) {
        return roiService.findById(id);
    }

    @PutMapping("/{id}")
    public RoiResponse update(@PathVariable Long id, @RequestBody RoiUpdateRequest request) {
        return roiService.update(id, request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        roiService.delete(id);
    }
}
