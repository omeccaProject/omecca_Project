package com.omecca.omeccabackend.dto;

import com.omecca.omeccabackend.entity.CameraCatalog;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class CameraCatalogResponse {

    private String camId;
    private String name;
    private String streamUrl;
    private String streamFormat;
    private String sourceType;

    public static CameraCatalogResponse from(CameraCatalog c) {
        return CameraCatalogResponse.builder()
                .camId(c.getCamId())
                .name(c.getName())
                .streamUrl(c.getStreamUrl())
                .streamFormat(c.getStreamFormat())
                .sourceType(c.getSourceType())
                .build();
    }
}
