-- 수배자 얼굴 등록 감사(audit) 테이블. 실제 얼굴 임베딩은
-- c_person_risk/face_embeddings.pkl에 있고, 이 테이블은 "누가 언제 어떤 사진으로
-- 등록/삭제 시도했는지"를 기록하는 계층이다.
CREATE TABLE wanted_person (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    wanted_id           VARCHAR(50)  NOT NULL UNIQUE,
    name                VARCHAR(100) NOT NULL,
    photo_url           VARCHAR(500),
    status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    failure_reason      VARCHAR(500),
    registered_by       BIGINT,
    registered_by_name  VARCHAR(50),
    created_at          DATETIME     NOT NULL
);
