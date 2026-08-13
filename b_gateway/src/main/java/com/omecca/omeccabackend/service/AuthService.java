package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.LoginRequest;
import com.omecca.omeccabackend.dto.LoginResponse;
import com.omecca.omeccabackend.dto.SignupRequest;
import com.omecca.omeccabackend.dto.UserResponse;
import com.omecca.omeccabackend.entity.User;
import com.omecca.omeccabackend.entity.enums.UserRole;
import com.omecca.omeccabackend.entity.enums.UserStatus;
import com.omecca.omeccabackend.repository.UserRepository;
import com.omecca.omeccabackend.security.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;

    @Transactional
    public UserResponse signup(SignupRequest request) {
        if (userRepository.existsByUsername(request.getUsername())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 사용 중인 아이디입니다");
        }
        User user = User.builder()
                .username(request.getUsername())
                .password(passwordEncoder.encode(request.getPassword()))
                .name(request.getName())
                .role(UserRole.USER)
                .status(UserStatus.PENDING)
                .build();
        userRepository.save(user);
        return UserResponse.from(user);
    }

    @Transactional(readOnly = true)
    public LoginResponse login(LoginRequest request) {
        User user = userRepository.findByUsername(request.getUsername())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다"));

        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다");
        }

        if (user.getStatus() == UserStatus.PENDING) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "관리자 승인 대기 중입니다");
        }
        if (user.getStatus() == UserStatus.REJECTED) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "가입이 거절된 계정입니다");
        }

        String token = jwtService.createToken(user.getId(), user.getUsername());
        return LoginResponse.builder()
                .token(token)
                .userId(user.getId())
                .username(user.getUsername())
                .name(user.getName())
                .role(user.getRole().name())
                .build();
    }

    @Transactional(readOnly = true)
    public List<UserResponse> findByStatus(String statusParam) {
        UserStatus status = parseStatus(statusParam);
        return userRepository.findByStatus(status).stream().map(UserResponse::from).toList();
    }

    @Transactional
    public UserResponse approve(Long targetUserId, Long adminUserId) {
        User user = getUser(targetUserId);
        user.setStatus(UserStatus.APPROVED);
        user.setApprovedBy(adminUserId);
        user.setApprovedAt(LocalDateTime.now());
        return UserResponse.from(user);
    }

    @Transactional
    public UserResponse reject(Long targetUserId, Long adminUserId) {
        User user = getUser(targetUserId);
        user.setStatus(UserStatus.REJECTED);
        user.setApprovedBy(adminUserId);
        user.setApprovedAt(LocalDateTime.now());
        return UserResponse.from(user);
    }

    private User getUser(Long id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "user not found"));
    }

    private UserStatus parseStatus(String value) {
        if (value == null || value.isBlank()) {
            return UserStatus.PENDING;
        }
        try {
            return UserStatus.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid status: " + value);
        }
    }
}