package com.omecca.omeccabackend.entity.enums;

/**
 * 얼굴 임베딩 생성 파이프라인 상태.
 * - PENDING: 사진 업로드+DB row 생성 완료, 파이썬 임베딩 생성 스크립트 실행 대기/진행 중
 * - REGISTERED: 임베딩 생성 성공, face_embeddings.pkl에 실제 반영 완료 - 즉시 감지 대상
 * - FAILED: 얼굴 인식 실패 등으로 임베딩 생성 불가 (failureReason 참고) - 감지에 반영 안 됨
 */
public enum WantedPersonStatus {
    PENDING,
    REGISTERED,
    FAILED
}
