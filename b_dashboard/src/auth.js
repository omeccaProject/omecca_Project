// 로그인 세션(로컬스토리지) 관리 + 권한 체크 헬퍼.
// b_gateway(AuthController)가 로그인 성공 시 내려주는 JWT 문자열을 그대로 저장해두고,
// 이후 관리자 API(/api/admin/**) 요청마다 Authorization: Bearer 헤더로 붙여서 보낸다.
// (모듈 -> 게이트웨이 이벤트 전송에 쓰는 X-API-Key와는 완전히 다른, 사람 로그인 전용 토큰)

const TOKEN_KEY = 'omecca_auth_token'
const USER_KEY = 'omecca_auth_user'

// 로그인 성공 응답(LoginResponse: token/userId/username/name/role)을 그대로 저장
export function saveSession(loginResponse) {
  localStorage.setItem(TOKEN_KEY, loginResponse.token)
  localStorage.setItem(USER_KEY, JSON.stringify({
    userId: loginResponse.userId,
    username: loginResponse.username,
    name: loginResponse.name,
    role: loginResponse.role,
  }))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function isLoggedIn() {
  return !!getToken()
}

export function isAdmin() {
  return getUser()?.role === 'ADMIN'
}

// 관리자 전용 API 호출에 붙일 헤더. 토큰 없으면 빈 객체(요청은 401로 자연스럽게 실패)
export function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}