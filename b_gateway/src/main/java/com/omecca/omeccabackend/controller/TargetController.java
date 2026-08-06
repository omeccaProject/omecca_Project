package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.TargetCreateRequest;
import com.omecca.omeccabackend.dto.TargetResponse;
import com.omecca.omeccabackend.service.TargetService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/**
 * 관심 대상(target) 등록·조회·종료 API.
 * 기획서 기능 ③ '관심 대상 자동 추적'에서 관제요원이 인물/차량을 등록하는 화면이 붙는 곳.
 */
@RestController
@RequestMapping("/api/targets")
@RequiredArgsConstructor
public class TargetController {

    private final TargetService targetService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public TargetResponse create(@Valid @RequestBody TargetCreateRequest request) {
        return targetService.create(request);
    }

    @GetMapping
    public Page<TargetResponse> list(
            @RequestParam(required = false) String status,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable
    ) {
        return targetService.findAll(status, pageable);
    }

    @GetMapping("/{id}")
    public TargetResponse get(@PathVariable Long id) {
        return targetService.findById(id);
    }

    @PatchMapping("/{id}/close")
    public TargetResponse close(@PathVariable Long id) {
        return targetService.close(id);
    }
}