package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.UserResponse;
import com.omecca.omeccabackend.service.AuthService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 회원가입 승인 관리. SecurityConfig에서 /api/admin/** 전체를 ROLE_ADMIN으로 막아뒀으므로,
 * 여기 도달했다는 것 자체가 이미 관리자 인증이 끝났다는 뜻이다.
 */
@RestController
@RequestMapping("/api/admin/users")
@RequiredArgsConstructor
public class AdminUserController {

    private final AuthService authService;

    /** 기본값 PENDING — 승인 대기 목록을 가장 자주 볼 것이므로 */
    @GetMapping
    public List<UserResponse> list(@RequestParam(required = false, defaultValue = "PENDING") String status) {
        return authService.findByStatus(status);
    }

    @PatchMapping("/{id}/approve")
    public UserResponse approve(@PathVariable Long id) {
        return authService.approve(id, currentAdminId());
    }

    @PatchMapping("/{id}/reject")
    public UserResponse reject(@PathVariable Long id) {
        return authService.reject(id, currentAdminId());
    }

    private Long currentAdminId() {
        return (Long) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
    }
}