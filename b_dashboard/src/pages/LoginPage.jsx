import { useState } from 'react'
import { login } from '../api'
import { saveSession } from '../auth'

// b_gateway POST /api/auth/login 호출. 성공하면 토큰을 저장하고 관제 대시보드("/dashboard")로 이동.
// AuthService가 던지는 에러 메시지(아이디/비번 불일치, 승인 대기, 거절됨)를 그대로 보여준다.
export default function LoginPage({ navigate }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!username.trim() || !password) {
      setError('아이디와 비밀번호를 입력해주세요.')
      return
    }
    setLoading(true)
    try {
      const res = await login({ username: username.trim(), password })
      saveSession(res)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message || '로그인에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

 return (
    <div className="auth-page">
      <button type="button" className="auth-back-btn" onClick={() => navigate('/landing')}>← 메인으로</button>
      <form className="auth-card" onSubmit={handleSubmit}>
        <div className="auth-brand"><span className="auth-dot"></span>Vigilog</div>
        <h2>로그인</h2>

        <label className="auth-field">
          <span>아이디</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
        </label>
        <label className="auth-field">
          <span>비밀번호</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button type="submit" className="auth-submit" disabled={loading}>
          {loading ? '로그인 중...' : '로그인'}
        </button>

        <div className="auth-switch">
          계정이 없으신가요? <button type="button" onClick={() => navigate('/signup')}>회원가입</button>
        </div>
      </form>
    </div>
  )
}
