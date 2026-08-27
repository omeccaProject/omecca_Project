package com.omecca.omeccabackend.controller;

import com.omecca.omeccabackend.dto.WantedPersonResponse;
import com.omecca.omeccabackend.service.WantedPersonService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * 수배자 얼굴 등록 API. AdminUserController와 동일한 원칙 - "누가 등록했는지"를
 * 확실히 남겨야 하는 민감한 행위라, X-API-Key(기계 간 호출)만으로는 부족하고 실제
 * 로그인한 사람(JWT)이어야 한다.
 *
 * [성혁 확인 필요] SecurityConfig에서 /api/wanted-persons/** 를 "로그인 필요
 * (인증된 사용자면 누구나, ADMIN 롤 제한은 아님 - 관제요원 전원이 등록 가능해야
 * 하므로 /api/admin/**처럼 ROLE_ADMIN으로 좁히면 안 됨)"로 추가해줘야 이 컨트롤러의
 * currentUserId()가 항상 유효한 값을 반환한다. 지금 상태로는 로그인 안 해도 요청
 * 자체는 도달하고 principal이 null이라 NPE가 날 수 있음 - 반드시 반영 필요.
 */
@RestController
@RequestMapping("/api/wanted-persons")
@RequiredArgsConstructor
public class WantedPersonController {

    private final WantedPersonService wantedPersonService;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public WantedPersonResponse register(
            @RequestParam("wantedId") String wantedId,
            @RequestParam("name") String name,
            @RequestParam("file") MultipartFile file
    ) {
        return wantedPersonService.register(wantedId, name, file, currentUserId());
    }

    @GetMapping
    public List<WantedPersonResponse> list() {
        return wantedPersonService.findAll();
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        wantedPersonService.delete(id);
    }

    private Long currentUserId() {
        return (Long) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
    }
}
