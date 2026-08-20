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
    }
}
