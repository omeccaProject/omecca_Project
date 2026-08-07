package com.omecca.omeccabackend.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.omecca.omeccabackend.dto.RoiCreateRequest;
import com.omecca.omeccabackend.dto.RoiResponse;
import com.omecca.omeccabackend.entity.Roi;
import com.omecca.omeccabackend.entity.enums.RoiType;
import com.omecca.omeccabackend.repository.RoiRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ResponseStatusException;

@Service
@RequiredArgsConstructor
public class RoiService {

    private final RoiRepository roiRepository;
    private final ObjectMapper objectMapper;

    @Transactional
    public RoiResponse create(RoiCreateRequest request) {
        RoiType roiType = parseEnum(RoiType.class, request.getRoiType(), "roiType");

        Roi roi = Roi.builder()
                .camId(request.getCamId())
                .roiType(roiType)
                .name(request.getName())
                .geometryJson(toJson(request.getGeometryJson()))
                .build();

        return RoiResponse.from(roiRepository.save(roi), objectMapper);
    }

    @Transactional(readOnly = true)
    public Page<RoiResponse> findAll(String camId, Pageable pageable) {
        Page<Roi> page = StringUtils.hasText(camId)
                ? roiRepository.findByCamId(camId, pageable)
                : roiRepository.findAll(pageable);
        return page.map(roi -> RoiResponse.from(roi, objectMapper));
    }

    @Transactional(readOnly = true)
    public RoiResponse findById(Long id) {
        Roi roi = roiRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "roi not found"));
        return RoiResponse.from(roi, objectMapper);
    }

    private String toJson(JsonNode node) {
        if (node == null || node.isNull()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "geometryJson is required");
        }
        try {
            return objectMapper.writeValueAsString(node);
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid json field: geometryJson");
        }
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
