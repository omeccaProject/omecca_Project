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
        return "GET".equalsIgnoreCase(request.getMethod()) && path.matches("^/api/reports/\\d+/download$");
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