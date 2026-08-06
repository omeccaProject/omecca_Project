package com.omecca.omeccabackend.entity.enums;

/** 위험 이벤트 종류 (기능 ①~⑦ 매핑) */
public enum EventType {
    WANTED_PERSON,        // ① 수배자 얼굴 인식
    WEAPON,                // ① 흉기 인식
    UNREGISTERED_VEHICLE,  // ④ DB 미등록 차량
    DEBRIS,                 // ⑤ 도로 낙하물·방치물
    DUI_PATTERN,             // ⑥ 음주운전 의심 주행 패턴
    SIGNAL_VIOLATION,        // ⑦ 신호 위반
    UTURN_VIOLATION           // ⑦ 불법 유턴
}
