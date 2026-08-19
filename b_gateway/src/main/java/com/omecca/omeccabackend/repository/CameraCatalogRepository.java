package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.CameraCatalog;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CameraCatalogRepository extends JpaRepository<CameraCatalog, Long> {

    Optional<CameraCatalog> findByCamId(String camId);

    // "카메라 관리" 자동완성용 - cam_id 또는 이름에 검색어가 들어있으면 매칭(대소문자 무시).
    // Top20으로 제한해서 검색어가 너무 짧아도(예: 한 글자) 응답이 과도하게 커지지 않게 한다.
    List<CameraCatalog> findTop20ByCamIdContainingIgnoreCaseOrNameContainingIgnoreCase(String camId, String name);
}
