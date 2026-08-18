import { useState } from 'react'
import { signup } from '../api'

// b_gateway POST /api/auth/signup 호출. 가입 즉시 로그인되는 게 아니라 status=PENDING으로
// 생성되고 관리자 승인을 기다려야 한다 (AuthService.signup 참고) - 그래서 성공하면 바로
// 대시보드로 보내지 않고 "승인 대기 안내" 화면을 보여준다.
export default function SignupPage({ navigate }) {
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!username.trim() || !password || !name.trim()) {
      setError('모든 항목을 입력해주세요.')
      return
    }
    if (password !== passwordConfirm) {
      setError('비밀번호가 일치하지 않습니다.')
      return
    }
    setLoading(true)
    try {
      await signup({ username: username.trim(), password, name: name.trim() })
      setDone(true)
    } catch (err) {
      setError(err.message || '회원가입에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  if (done) {
    return (
      <div className="auth-page">
        <button type="button" className="auth-back-btn" onClick={() => navigate('/landing')}>← 메인으로</button>
        <div className="auth-card">
          <div className="auth-brand"><span className="auth-dot">3</span>OMECCA-3</div>
          <h2>가입 신청 완료</h2>
          <p className="auth-done-text">
            가입 신청이 접수되었습니다.<br />관리자 승인 후 로그인할 수 있습니다.
          </p>
          <button type="button" className="auth-submit" onClick={() => navigate('/login')}>로그인 화면으로</button>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <button type="button" className="auth-back-btn" onClick={() => navigate('/landing')}>← 메인으로</button>
      <form className="auth-card" onSubmit={handleSubmit}>
        <div className="auth-brand"><span className="auth-dot">3</span>OMECCA-3</div>
        <h2>회원가입</h2>

        <label className="auth-field">
          <span>이름</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" autoFocus />
        </label>
        <label className="auth-field">
          <span>아이디</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="auth-field">
          <span>비밀번호</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </label>
        <label className="auth-field">
          <span>비밀번호 확인</span>
          <input type="password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)} autoComplete="new-password" />
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button type="submit" className="auth-submit" disabled={loading}>
          {loading ? '가입 신청 중...' : '가입 신청'}
        </button>

        <div className="auth-switch">
          이미 계정이 있으신가요? <button type="button" onClick={() => navigate('/login')}>로그인</button>
        </div>
      </form>
    </div>
  )
}
