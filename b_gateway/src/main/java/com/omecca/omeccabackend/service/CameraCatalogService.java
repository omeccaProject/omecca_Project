package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.CameraCatalogResponse;
import com.omecca.omeccabackend.repository.CameraCatalogRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;

@Service
@RequiredArgsConstructor
public class CameraCatalogService {

    private final CameraCatalogRepository cameraCatalogRepository;

    // query가 비어있으면 검색 의미가 없으므로 빈 목록을 준다(전체 303대를 매번 다 내려줄
    // 필요는 없음 - "카메라 관리"에서 타이핑을 시작해야 자동완성이 뜨는 구조).
    @Transactional(readOnly = true)
    public List<CameraCatalogResponse> search(String query) {
        if (!StringUtils.hasText(query)) {
            return List.of();
        }
        String q = query.trim();
        return cameraCatalogRepository
                .findTop20ByCamIdContainingIgnoreCaseOrNameContainingIgnoreCase(q, q)
                .stream()
                .map(CameraCatalogResponse::from)
                .toList();
    }
}
