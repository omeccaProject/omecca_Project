package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Roi;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface RoiRepository extends JpaRepository<Roi, Long> {
    List<Roi> findByCamId(String camId);

    Page<Roi> findByCamId(String camId, Pageable pageable);
}