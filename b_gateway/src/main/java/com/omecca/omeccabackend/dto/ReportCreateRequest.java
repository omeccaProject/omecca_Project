package com.omecca.omeccabackend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class ReportCreateRequest {

    @NotNull
    private Long eventId;

    @NotBlank
    private String pdfPath;

    /** PENDING / GENERATED / FAILED — 미지정 시 서비스에서 GENERATED로 처리 (b_report가 PDF 생성 완료 후 호출하는 흐름 기준) */
    private String status;
}
