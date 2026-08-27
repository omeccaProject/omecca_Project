package com.omecca.omeccabackend.entity;

import com.omecca.omeccabackend.entity.enums.WantedPersonStatus;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 수배자 얼굴 등록 마스터 데이터. C파트(얼굴인식) 모듈이 실시간으로 참조하는
 * c_person_risk/face_embeddings.pkl과 1:1로 대응되는 감사(audit) 레코드다.
 *
 * 왜 필요한가: pkl 파일 자체는 "누가 언제 이 사람을 수배자로 등록했는지"를 전혀
 * 기록하지 않는다. 얼굴 데이터베이스에 사람을 추가하는 건 민감한 행위라 경찰/지자체
 * 관제센터 운영 기준상 반드시 등록자 추적이 가능해야 하므로, 이 테이블이 그 책임
 * 소재를 남긴다. 실제 임베딩 생성/매칭 로직은 그대로 파이썬(c_person_risk) 담당,
 * 이 테이블은 "누가, 언제, 어떤 사진으로" 등록했는지의 기록 계층이다.
 */
@Entity
@Table(name = "wanted_person")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class WantedPerson {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** c_person_risk 쪽 known_faces 파일명/pkl entry의 id와 반드시 일치해야 함 (예: W005) */
    @Column(name = "wanted_id", nullable = false, unique = true, length = 50)
    private String wantedId;

    @Column(nullable = false, length = 100)
    private String name;

    /** 원본 등록 사진이 저장된 정적 서빙 경로 (예: /media/wanted/W005.jpg) */
    @Column(name = "photo_url", length = 500)
    private String photoUrl;

    @Enumerated(EnumType.STRING)
    @Builder.Default
    @Column(nullable = false, length = 20)
    private WantedPersonStatus status = WantedPersonStatus.PENDING;

    /** 임베딩 생성 실패 시 사유(파이썬 스크립트 stderr 메시지) - 관제요원이 재등록 판단할 근거 */
    @Column(name = "failure_reason", length = 500)
    private String failureReason;

    /** 등록한 사용자의 id. User 엔티티가 나중에 삭제돼도 이 값 자체는 감사기록으로 남아야
     * 하므로 FK를 걸지 않는다(Camera.camId 설계와 동일한 원칙). */
    @Column(name = "registered_by")
    private Long registeredBy;

    /** 등록 당시 사용자 이름 스냅샷. User가 개명하거나 탈퇴해도 "그 시점에 누가 했는지"는
     * 그대로 보여야 하므로 조인 대신 등록 시점 값을 그대로 저장(비정규화). */
    @Column(name = "registered_by_name", length = 50)
    private String registeredByName;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }
}
