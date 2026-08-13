package com.omecca.omeccabackend.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Optional;

/**
 * JWT 발급/검증. 외부 라이브러리(jjwt 등) 없이 HMAC-SHA256으로 직접 서명한다.
 * 토큰 형식: Base64(userId:username:만료시각:서명)
 *
 * 모듈 -> 게이트웨이(X-API-Key)와는 완전히 다른 인증 체계다. 이건 사람이
 * 로그인할 때만 쓴다.
 */
@Service
public class JwtService {

    private static final String HMAC_ALGORITHM = "HmacSHA256";
    /** 토큰 유효 기간: 7일 */
    private static final long EXPIRY_MS = 7L * 24 * 60 * 60 * 1000;

    private final byte[] secretBytes;

    public JwtService(@Value("${app.auth.jwt-secret:omecca-jwt-secret-change-this}") String secret) {
        this.secretBytes = secret.getBytes(StandardCharsets.UTF_8);
    }

    /** 로그인 성공 시 호출. 프론트는 반환값을 localStorage에 저장하고 이후 요청 헤더에 붙인다. */
    public String createToken(Long userId, String username) {
        long expiresAt = System.currentTimeMillis() + EXPIRY_MS;
        String payload = userId + ":" + username + ":" + expiresAt;
        String signature = sign(payload);
        String token = payload + ":" + signature;
        return Base64.getUrlEncoder().withoutPadding().encodeToString(token.getBytes(StandardCharsets.UTF_8));
    }

    /** Authorization: Bearer 토큰을 검증하고 userId를 반환한다. 서명 불일치/만료/형식 오류 시 empty. */
    public Optional<Long> parseUserId(String token) {
        try {
            String decoded = new String(Base64.getUrlDecoder().decode(token), StandardCharsets.UTF_8);
            String[] parts = decoded.split(":");
            if (parts.length != 4) {
                return Optional.empty();
            }

            String payload = parts[0] + ":" + parts[1] + ":" + parts[2];
            if (!sign(payload).equals(parts[3])) {
                return Optional.empty();
            }

            long expiresAt = Long.parseLong(parts[2]);
            if (System.currentTimeMillis() > expiresAt) {
                return Optional.empty();
            }

            return Optional.of(Long.parseLong(parts[0]));
        } catch (Exception ignored) {
            return Optional.empty();
        }
    }

    private String sign(String payload) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(secretBytes, HMAC_ALGORITHM));
            byte[] digest = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(digest);
        } catch (Exception e) {
            throw new IllegalStateException("JWT 서명 생성 실패", e);
        }
    }
}