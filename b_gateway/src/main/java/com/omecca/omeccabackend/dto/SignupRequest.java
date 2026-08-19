package com.omecca.omeccabackend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class SignupRequest {

    @NotBlank
    private String username;

    @NotBlank
    private String password;

    @NotBlank
    private String name;

    // 회원가입 시 "관리자"/"일반 사용자" 중 선택한 값. 비워서 보내면(구버전 클라이언트 호환)
    // AuthService에서 USER로 기본 처리한다. 여기서 값 자체를 USER/ADMIN 두 가지로만
    // 제한해두는 게 1차 방어선 - AuthService에서 UserRole.valueOf()로 한 번 더 검증한다.
    // 주의: 이렇게 관리자를 선택해서 가입해도 UserStatus는 여전히 PENDING으로 생성되고,
    // 기존 관리자가 승인(approve)해야만 실제로 로그인 가능해진다(AuthService.login() 참고) -
    // 즉 "관리자 자율 셀프 승격"은 불가능하고 승인 절차가 그대로 안전장치 역할을 한다.
    @Pattern(regexp = "^(USER|ADMIN)?$", message = "권한은 USER 또는 ADMIN이어야 합니다")
    private String role;
}