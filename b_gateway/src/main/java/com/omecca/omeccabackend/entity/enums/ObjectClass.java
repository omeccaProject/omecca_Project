package com.omecca.omeccabackend.entity.enums;

/**
 * YOLOv11이 1차로 탐지한 원시 객체 클래스.
 * 흉기/차종 등 세부 정보는 objectClass가 아니라 meta에 담는다.
 */
public enum ObjectClass {
    PERSON,
    VEHICLE,
    OBJECT
}
