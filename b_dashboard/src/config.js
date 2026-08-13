// 게이트웨이 API 인증 키.
// b_gateway의 GATEWAY_API_KEY 환경변수와 반드시 같은 값이어야 함 (기본값 서로 일치: omecca-dev-key-2026).
// 로컬에서 다른 값을 쓰고 싶으면 b_dashboard/.env 파일에 VITE_API_KEY=... 로 오버라이드.
export const API_KEY = import.meta.env.VITE_API_KEY || 'omecca-dev-key-2026'