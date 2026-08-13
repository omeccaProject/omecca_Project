package com.omecca.omeccabackend.dto;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class LoginResponse {
    private String token;
    private Long userId;
    private String username;
    private String name;
    private String role;
}