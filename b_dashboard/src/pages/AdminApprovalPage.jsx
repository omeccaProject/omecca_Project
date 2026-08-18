import { useCallback, useEffect, useState } from 'react'
import { approveUser, fetchUsersByStatus, rejectUser } from '../api'
import { clearSession, getUser, isAdmin, isLoggedIn } from '../auth'

const STATUS_TABS = [
  { value: 'PENDING', label: '승인 대기' },
  { value: 'APPROVED', label: '승인됨' },
  { value: 'REJECTED', label: '거절됨' },
]

function fmtDate(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

// b_gateway /api/admin/users(GET) + /{id}/approve, /{id}/reject(PATCH) 사용.
// SecurityConfig가 /api/admin/** 전체를 ROLE_ADMIN + JWT로 막아뒀기 때문에, 로그인 여부/역할
// 체크는 여기서도 한 번 더(프론트에서) 해서 관리자가 아닌 사람에게는 화면 자체를 안 보여준다.
export default function AdminApprovalPage({ navigate }) {
  const [status, setStatus] = useState('PENDING')
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [actingId, setActingId] = useState(null)
  const me = getUser()

  const load = useCallback(async (s) => {
    setLoading(true)
    setError('')
    try {
      const list = await fetchUsersByStatus(s)
      setUsers(list)
    } catch (err) {
      setError(err.message || '회원 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isLoggedIn() || !isAdmin()) return
    load(status)
  }, [status, load])

  if (!isLoggedIn()) {
    return (
      <div className="admin-page">
        <div className="admin-guard">
          로그인이 필요합니다.
          <button type="button" onClick={() => navigate('/login')}>로그인하러 가기</button>
        </div>
      </div>
    )
  }
  if (!isAdmin()) {
    return (
      <div className="admin-page">
        <div className="admin-guard">
          관리자 권한이 필요한 화면입니다.
          <button type="button" onClick={() => navigate('/')}>관제 화면으로</button>
        </div>
      </div>
    )
  }

  const handleApprove = async (id) => {
    setActingId(id)
    try {
      await approveUser(id)
      await load(status)
    } catch (err) {
      alert(err.message || '승인 처리 중 오류가 발생했습니다.')
    } finally {
      setActingId(null)
    }
  }

  const handleReject = async (id) => {
    setActingId(id)
    try {
      await rejectUser(id)
      await load(status)
    } catch (err) {
      alert(err.message || '거절 처리 중 오류가 발생했습니다.')
    } finally {
      setActingId(null)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-topbar">
        <div className="auth-brand" onClick={() => navigate('/')}>SMART CCTV 관제시스템</div>
        <div className="admin-topbar-right">
          <span>{me?.name} 관리자님</span>
          <button type="button" onClick={() => navigate('/')}>관제 화면으로</button>
          <button type="button" onClick={() => { clearSession(); navigate('/login') }}>로그아웃</button>
        </div>
      </div>

      <div className="admin-body">
        <h2>회원 승인 관리</h2>

        <div className="admin-tabs">
          {STATUS_TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              className={status === t.value ? 'active' : ''}
              onClick={() => setStatus(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <div className="auth-error">{error}</div>}

        <table className="admin-table">
          <thead>
            <tr>
              <th>이름</th><th>아이디</th><th>권한</th><th>가입일시</th><th>처리일시</th><th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="admin-empty">불러오는 중...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={6} className="admin-empty">해당 상태의 회원이 없습니다.</td></tr>
            ) : users.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{fmtDate(u.createdAt)}</td>
                <td>{fmtDate(u.approvedAt)}</td>
                <td className="admin-actions">
                  {status === 'PENDING' ? (
                    <>
                      <button type="button" className="admin-approve" disabled={actingId === u.id} onClick={() => handleApprove(u.id)}>승인</button>
                      <button type="button" className="admin-reject" disabled={actingId === u.id} onClick={() => handleReject(u.id)}>거절</button>
                    </>
                  ) : (
                    <span className={`admin-status-tag ${u.status?.toLowerCase()}`}>
                      {u.status === 'APPROVED' ? '승인됨' : '거절됨'}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}