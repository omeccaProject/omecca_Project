// b_gateway REST API 호출 모음. 전부 상대경로("/api/...")라서
// dev 모드에선 vite.config.js의 proxy를 타고, 빌드 후엔 같은 오리진(스프링부트)에서 바로 붙는다.

import { API_KEY } from './config'

const AUTH_HEADERS = { 'X-API-Key': API_KEY }

export async function fetchInitialEvents(size = 30) {
  const res = await fetch(`/api/events?size=${size}`, { headers: AUTH_HEADERS })
  if (!res.ok) throw new Error(`이벤트 목록 조회 실패: ${res.status}`)
  const page = await res.json()
  return page.content ?? []
}