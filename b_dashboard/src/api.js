// b_gateway REST API 호출 모음. 전부 상대경로("/api/...")라서
// dev 모드에선 vite.config.js의 proxy를 타고, 빌드 후엔 같은 오리진(스프링부트)에서 바로 붙는다.

import { API_KEY } from './config'
import { authHeaders } from './auth'

const AUTH_HEADERS = { 'X-API-Key': API_KEY }
const JSON_HEADERS = { 'Content-Type': 'application/json' }

export async function fetchInitialEvents(size = 30) {
  const res = await fetch(`/api/events?size=${size}`, { headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(`이벤트 목록 조회 실패: ${res.status}`)
  const page = await res.json()
  return page.content ?? []
}

// "📄 PDF 리포트 생성" 버튼용. 서버(b_report)가 그 자리에서 실제 PDF를 만들어 바이너리로
// 돌려준다 - 이미지가 없거나(전/후 캡쳐 없음) b_report 실행 자체가 실패하면 게이트웨이가
// 사람이 읽을 수 있는 에러 메시지를 JSON으로 준다(parseErrorMessage로 꺼냄).
// 반환값은 Blob이고, 호출한 쪽에서 URL.createObjectURL로 다운로드를 트리거하면 된다.
export async function generateEventReport(eventId) {
  const res = await fetch(`/api/events/${eventId}/report`, {
    method: 'POST',
    headers: AUTH_HEADERS,
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '리포트 생성에 실패했습니다.'))
  return res.blob()
}

// 관심 대상(target) 등록 현황 조회. 사이드바의 "추적 차량"/"관심 대상" 카운트는
// 이벤트 로그(event)가 아니라 실제로 등록·추적 중인 대상(target, status=ACTIVE) 기준으로 집계한다.
// (target.target_type: PERSON | VEHICLE — DB_스키마_설계서.md 3.1 참고)
export async function fetchActiveTargets(size = 200) {
  const res = await fetch(`/api/targets?status=ACTIVE&size=${size}`, { headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(`관심 대상 목록 조회 실패: ${res.status}`)
  const data = await res.json()
  // 페이징 응답({content:[...]})과 배열 응답 둘 다 방어적으로 처리.
  return Array.isArray(data) ? data : (data.content ?? [])
}

// 관심 대상 관리 화면(TargetsPanel)용. status가 없으면 전체(ACTIVE+CLOSED) 조회.
export async function fetchTargets(status = '', size = 200) {
  const qs = status ? `?status=${status}&size=${size}` : `?size=${size}`
  const res = await fetch(`/api/targets${qs}`, { headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(`관심 대상 목록 조회 실패: ${res.status}`)
  const data = await res.json()
  return Array.isArray(data) ? data : (data.content ?? [])
}

// 관심 대상 신규 등록. payload: { targetType, plateNumber?, personRefId?, label?, registeredBy }
export async function createTarget(payload) {
  const res = await fetch('/api/targets', {
    method: 'POST',
    headers: { ...AUTH_HEADERS, ...JSON_HEADERS },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '관심 대상 등록에 실패했습니다.'))
  return res.json()
}

// 추적 종료(status: ACTIVE → CLOSED).
export async function closeTarget(id) {
  const res = await fetch(`/api/targets/${id}/close`, { method: 'PATCH', headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '추적 종료 처리에 실패했습니다.'))
  return res.json()
}

// 카메라 마스터 데이터 관리(CctvGrid "카메라 관리" 버튼). 실제 설치된 카메라 목록/이름/
// 실시간 영상 연결 여부를 여기서 CRUD한다. target/roi와 동일하게 X-API-Key로 보호됨.
export async function fetchCameras() {
  const res = await fetch('/api/cameras', { headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(`카메라 목록 조회 실패: ${res.status}`)
  return res.json()
}

// payload: { camId, name, streamUrl?, streamFormat? }
export async function createCamera(payload) {
  const res = await fetch('/api/cameras', {
    method: 'POST',
    headers: { ...AUTH_HEADERS, ...JSON_HEADERS },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '카메라 등록에 실패했습니다.'))
  return res.json()
}

// payload: 바뀐 필드만 { name?, status?, streamUrl?, streamFormat? }
export async function updateCamera(id, payload) {
  const res = await fetch(`/api/cameras/${id}`, {
    method: 'PATCH',
    headers: { ...AUTH_HEADERS, ...JSON_HEADERS },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '카메라 수정에 실패했습니다.'))
  return res.json()
}

export async function deleteCamera(id) {
  const res = await fetch(`/api/cameras/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '카메라 삭제에 실패했습니다.'))
}

// 응답 body가 JSON이면 message/error 필드를, 아니면 fallback 문구를 사용한다.
async function parseErrorMessage(res, fallback) {
  try {
    const body = await res.json()
    return body?.message || body?.error || fallback
  } catch {
    return fallback
  }
}

// 회원가입/로그인은 모듈 인증(X-API-Key)이 아니라 사람 계정(JWT) 인증이라 헤더가 다르다.
// ApiKeyFilter가 /api/auth/**, /api/admin/**은 X-API-Key 검사에서 아예 제외해둠.
// role: 'USER' | 'ADMIN' (선택). 비워서 보내면 게이트웨이가 USER로 기본 처리한다
// (SignupRequest.role, AuthService.signup 참고). 관리자를 선택해도 status는 PENDING으로
// 생성되어 기존 관리자 승인 전까지는 로그인이 안 되므로 셀프 승격 위험은 없다.
export async function signup({ username, password, name, role }) {
  const res = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, password, name, role }),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '회원가입에 실패했습니다.'))
  return res.json()
}

export async function login({ username, password }) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '로그인에 실패했습니다.'))
  return res.json()
}

// 아래 셋은 관리자(JWT + ROLE_ADMIN) 전용. authHeaders()가 Authorization: Bearer <token>을 붙여준다.
export async function fetchUsersByStatus(status = 'PENDING') {
  const res = await fetch(`/api/admin/users?status=${status}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '회원 목록 조회에 실패했습니다.'))
  return res.json()
}

export async function approveUser(id) {
  const res = await fetch(`/api/admin/users/${id}/approve`, { method: 'PATCH', headers: authHeaders() })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '승인 처리에 실패했습니다.'))
  return res.json()
}

export async function rejectUser(id) {
  const res = await fetch(`/api/admin/users/${id}/reject`, { method: 'PATCH', headers: authHeaders() })
  if (!res.ok) throw new Error(await parseErrorMessage(res, '거절 처리에 실패했습니다.'))
  return res.json()
}