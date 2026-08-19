package com.omecca.omeccabackend.security;

import com.omecca.omeccabackend.entity.User;
import com.omecca.omeccabackend.entity.enums.UserStatus;
import com.omecca.omeccabackend.repository.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * Authorization: Bearer <JWT> 헤더를 파싱해 SecurityContext에 로그인 사용자를 등록한다.
 * status가 APPROVED가 아니면(대기/거절) 토큰이 유효해도 인증하지 않는다 — 매 요청마다
 * DB를 다시 조회하므로, 관리자가 방금 거절해도 즉시 반영된다.
 */
@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtService jwtService;
    private final UserRepository userRepository;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String authorization = request.getHeader("Authorization");
        if (authorization != null && authorization.startsWith("Bearer ")) {
            String token = authorization.substring(7).trim();
            jwtService.parseUserId(token).ifPresent(userId -> {
                User user = userRepository.findById(userId).orElse(null);
                if (user != null && user.getStatus() == UserStatus.APPROVED) {
                    var authorities = List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole().name()));
                    var authentication = new UsernamePasswordAuthenticationToken(userId, null, authorities);
                    SecurityContextHolder.getContext().setAuthentication(authentication);
                }
            });
        }
        filterChain.doFilter(request, response);
    }
}