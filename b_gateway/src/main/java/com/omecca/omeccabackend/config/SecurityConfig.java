package com.omecca.omeccabackend.config;

import com.omecca.omeccabackend.security.JwtAuthenticationFilter;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * 사람이 로그인하는 부분(JWT)만 담당한다. 모듈 -> 게이트웨이 이벤트 전송(X-API-Key)은
 * ApiKeyFilter가 별도로 계속 처리하며, 이 설정과 무관하게 그대로 동작한다.
 *
 * 지금 단계에서는 /api/admin/**(로그인+ADMIN)과 /api/reports/**(GET만, 로그인)만 강제하고,
 * 나머지 API는 그대로 열어둔다. 대시보드가 아직 로그인 화면을 전면 적용하기 전이라 여기서
 * 전부 막아버리면 기존 대시보드/모듈 연동이 다 깨진다 — 프론트에 로그인 화면이 붙고 나면
 * 범위를 넓히면 된다. 리포트는 증거 PDF라 예외적으로 먼저 로그인을 요구하도록 함.
 */
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> {})
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        // 리포트 조회(목록/상세/다운로드)는 로그인한 사람이면 누구나(관제요원 포함) 볼 수 있어야 하므로
                        // ADMIN까지는 아니고 "로그인만" 요구. 증거 PDF라 비로그인 상태로는 절대 못 열어야 함.
                        // "/api/reports"(목록)와 "/api/reports/{id}", "/api/reports/{id}/download" 둘 다 명시적으로 커버.
                        .requestMatchers(HttpMethod.GET, "/api/reports", "/api/reports/**").authenticated()
                        .anyRequest().permitAll()
                )
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, exception) -> {
                            response.setStatus(401);
                            response.setContentType("application/json;charset=UTF-8");
                            response.getWriter().write("{\"error\":\"로그인이 필요합니다.\"}");
                        })
                        .accessDeniedHandler((request, response, exception) -> {
                            response.setStatus(403);
                            response.setContentType("application/json;charset=UTF-8");
                            response.getWriter().write("{\"error\":\"관리자 권한이 필요합니다.\"}");
                        })
                )
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}