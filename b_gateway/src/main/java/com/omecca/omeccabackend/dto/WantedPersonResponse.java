package com.omecca.omeccabackend.dto;

import com.omecca.omeccabackend.entity.WantedPerson;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class WantedPersonResponse {

    private Long id;
    private String wantedId;
    private String name;
    private String photoUrl;
    private String status;
    private String failureReason;
    private Long registeredBy;
    private String registeredByName;
    private LocalDateTime createdAt;

    public static WantedPersonResponse from(WantedPerson w) {
        return WantedPersonResponse.builder()
                .id(w.getId())
                .wantedId(w.getWantedId())
                .name(w.getName())
                .photoUrl(w.getPhotoUrl())
                .status(w.getStatus().name())
                .failureReason(w.getFailureReason())
                .registeredBy(w.getRegisteredBy())
                .registeredByName(w.getRegisteredByName())
                .createdAt(w.getCreatedAt())
                .build();
    }
}
