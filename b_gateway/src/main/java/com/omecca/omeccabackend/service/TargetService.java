package com.omecca.omeccabackend.service;

import com.omecca.omeccabackend.dto.TargetCreateRequest;
import com.omecca.omeccabackend.dto.TargetResponse;
import com.omecca.omeccabackend.entity.Target;
import com.omecca.omeccabackend.entity.enums.TargetStatus;
import com.omecca.omeccabackend.entity.enums.TargetType;
import com.omecca.omeccabackend.repository.TargetRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
public class TargetService {

    private final TargetRepository targetRepository;

    @Transactional
    public TargetResponse create(TargetCreateRequest request) {
        TargetType targetType = parseEnum(TargetType.class, request.getTargetType(), "targetType");

        if (targetType == TargetType.VEHICLE && !StringUtils.hasText(request.getPlateNumber())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "targetType=VEHICLE이면 plateNumber가 필요합니다");
        }
        if (targetType == TargetType.PERSON && !StringUtils.hasText(request.getPersonRefId())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "targetType=PERSON이면 personRefId가 필요합니다");
        }

        Target target = Target.builder()
                .targetType(targetType)
                .plateNumber(request.getPlateNumber())
                .personRefId(request.getPersonRefId())
                .label(request.getLabel())
                .registeredBy(request.getRegisteredBy())
                .status(TargetStatus.ACTIVE)
                .build();

        return TargetResponse.from(targetRepository.save(target));
    }

    @Transactional(readOnly = true)
    public Page<TargetResponse> findAll(String statusParam, Pageable pageable) {
        if (!StringUtils.hasText(statusParam)) {
            return targetRepository.findAll(pageable).map(TargetResponse::from);
        }
        TargetStatus status = parseEnum(TargetStatus.class, statusParam, "status");
        return targetRepository.findByStatus(status, pageable).map(TargetResponse::from);
    }

    @Transactional(readOnly = true)
    public TargetResponse findById(Long id) {
        return TargetResponse.from(getTarget(id));
    }

    @Transactional
    public TargetResponse close(Long id) {
        Target target = getTarget(id);
        if (target.getStatus() == TargetStatus.CLOSED) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 종료된 대상입니다");
        }
        target.setStatus(TargetStatus.CLOSED);
        target.setClosedAt(LocalDateTime.now());
        return TargetResponse.from(target);
    }

    private Target getTarget(Long id) {
        return targetRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "target not found"));
    }

    private <E extends Enum<E>> E parseEnum(Class<E> type, String value, String fieldName) {
        if (!StringUtils.hasText(value)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, fieldName + " is required");
        }
        try {
            return Enum.valueOf(type, value.trim().toUpperCase());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid " + fieldName + ": " + value);
        }
    }
}