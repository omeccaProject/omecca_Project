package com.omecca.omeccabackend.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class ApiKeyFilter extends OncePerRequestFilter {

    private static final String HEADER_NAME = "X-API-Key";

    @Value("${gateway.api-key}")
    private String apiKey;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        if (!path.startsWith("/api/")) {
            return true;
        }
        if (path.startsWith("/api/health")) {
            return true;
        }
        // 회원가입/로그인은 API 키가 아니라 JWT(사람 인증) 대상 -> 여기서 제외
        if (path.startsWith("/api/auth/")) {
            return true;
        }
        // /api/admin/** 은 SecurityConfig가 JWT + ROLE_ADMIN으로 이미 막고 있음 -> 이중 인증 방지
        if (path.startsWith("/api/admin/")) {
            return true;
        }
        // 리포트 조회(목록 "/api/reports", 상세 "/api/reports/{id}", 다운로드 "/api/reports/{id}/download")는
        // SecurityConfig가 JWT(로그인)로 이미 막고 있음 -> 이중 인증 방지.
        // 단, 리포트 "생성"(POST /api/reports)은 b_report 같은 탐지 모듈이 X-API-Key로 호출하는 경로라 그대로 검사 대상.
        if ("GET".equalsIgnoreCase(request.getMethod())
                && (path.equals("/api/reports") || path.startsWith("/api/reports/"))) {
            return true;
        }
        return false;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String provided = request.getHeader(HEADER_NAME);

        if (apiKey != null && !apiKey.isBlank() && apiKey.equals(provided)) {
            filterChain.doFilter(request, response);
            return;
        }

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"UNAUTHORIZED\",\"message\":\"X-API-Key 헤더가 없거나 올바르지 않습니다.\"}");
    }
}