package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.LoginRequest;
import com.omecca.omeccabackend.dto.LoginResponse;
import com.omecca.omeccabackend.dto.SignupRequest;
import com.omecca.omeccabackend.dto.UserResponse;
import com.omecca.omeccabackend.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/**
 * 회원가입 신청 / 로그인. SecurityConfig에서 이 경로들은 인증 없이 접근 가능하도록 열어뒀다.
 */
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/signup")
    @ResponseStatus(HttpStatus.CREATED)
    public UserResponse signup(@Valid @RequestBody SignupRequest request) {
        return authService.signup(request);
    }

    @PostMapping("/login")
    public LoginResponse login(@Valid @RequestBody LoginRequest request) {
        return authService.login(request);
    }
}