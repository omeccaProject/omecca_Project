package com.omecca.omeccabackend.dto;

import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

/**
 * 이벤트 스키마 규격서의 "location": { "lat": .., "lng": .. } 형태 매핑
 */
@Getter
@Setter
public class LocationDto {
    private BigDecimal lat;
    private BigDecimal lng;
}
