package com.omecca.omeccabackend.repository;

import com.omecca.omeccabackend.entity.WantedPerson;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface WantedPersonRepository extends JpaRepository<WantedPerson, Long> {
    boolean existsByWantedId(String wantedId);
    Optional<WantedPerson> findByWantedId(String wantedId);
    List<WantedPerson> findAllByOrderByCreatedAtDesc();
}
