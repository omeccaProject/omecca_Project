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
export async function signup({ username, password, name }) {
  const res = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, password, name }),
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