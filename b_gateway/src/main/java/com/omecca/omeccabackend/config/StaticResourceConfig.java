package com.omecca.omeccabackend.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.nio.file.Path;

/**
 * CameraService.uploadVideo가 저장한 동영상 파일을 /media/videos/**로 서빙한다.
 * /api/**가 아니므로 ApiKeyFilter를 안 타고, SecurityConfig의 anyRequest().permitAll()로
 * 인증 없이 열려 있다 - <video src>가 커스텀 헤더를 못 붙이는 것과 동일한 이유로,
 * UTIC HLS 외부 URL과 마찬가지로 인증 없이 바로 재생 가능해야 한다.
 *
 * [추가] WantedPersonService가 저장한 수배자 등록 사진도 같은 이유(<img src>가
 * 커스텀 헤더를 못 붙임)로 /media/wanted/**를 통해 인증 없이 서빙한다. 사진 자체는
 * 민감할 수 있으나, URL 자체가 UUID라 추측 불가능한 랜덤 파일명이라 videos와 동일한
 * 보안 수준으로 취급한다 - 등록/조회/삭제 같은 "행위"는 SecurityConfig에서
 * /api/wanted-persons/**로 이미 로그인을 강제하고 있고, 여기는 그 결과물(정적 이미지
 * 파일 하나)을 그냥 내려주는 것뿐이라 별도 인증을 추가하지 않는다.
 */
@Configuration
public class StaticResourceConfig implements WebMvcConfigurer {

    @Value("${app.upload-dir:uploads}")
    private String uploadDir;

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        // Windows에서 Path.toString()은 백슬래시를 쓰는데, Spring의 "file:" 리소스 위치는
        // 슬래시 기준이라 그대로 넘기면 안 깨지긴 해도 관례에 안 맞는다 - 명시적으로 치환.
        String videosDir = Path.of(uploadDir, "videos").toAbsolutePath().normalize()
                .toString().replace('\\', '/');
        registry.addResourceHandler("/media/videos/**")
                .addResourceLocations("file:" + videosDir + "/");

        // [추가] 수배자 등록 사진 서빙 (WantedPersonManagerModal 목록의 썸네일 img src용)
        String wantedDir = Path.of(uploadDir, "wanted").toAbsolutePath().normalize()
                .toString().replace('\\', '/');
        registry.addResourceHandler("/media/wanted/**")
                .addResourceLocations("file:" + wantedDir + "/");
    }
}