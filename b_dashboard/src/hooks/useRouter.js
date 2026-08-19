import { useCallback, useEffect, useState } from 'react'

// 별도 라이브러리(react-router 등) 없이 쓰는 아주 단순한 경로 기반 라우터.
// 기존 App.jsx의 "?view=" 키오스크 파라미터 방식은 그대로 두고, 이건 로그인/회원가입/
// 관리자 승인 화면처럼 실제로 주소가 바뀌어야 하는 화면에만 새로 쓴다.
export function useRouter() {
  const [pathname, setPathname] = useState(window.location.pathname)

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((to) => {
    if (to === window.location.pathname) return
    window.history.pushState({}, '', to)
    setPathname(to)
  }, [])

  return { pathname, navigate }
}