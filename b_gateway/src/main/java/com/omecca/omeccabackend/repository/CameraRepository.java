package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.Camera;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface CameraRepository extends JpaRepository<Camera, Long> {

    boolean existsByCamId(String camId);

    Optional<Camera> findByCamId(String camId);
}
