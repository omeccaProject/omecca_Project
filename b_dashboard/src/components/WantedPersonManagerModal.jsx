import { useCallback, useEffect, useState } from 'react'
import { fetchWantedPersons, createWantedPerson, deleteWantedPerson } from '../api'

const EMPTY_FORM = { wantedId: '', name: '' }

const STATUS_LABEL = {
  PENDING: '등록 처리 중...',
  REGISTERED: '정상 등록됨',
  FAILED: '등록 실패',
}

// 수배자 얼굴 데이터베이스 관리 모달. CameraManagerModal과 완전히 동일한 시각적
// 패턴(cam-mgr-* 클래스 재사용)을 따른다 - 관제요원이 두 관리 화면을 오가도
// 이질감이 없게 하기 위함.
//
// 카메라 등록과 결정적으로 다른 점: 이건 "실시간 영상 스트림 설정"이 아니라
// "누구를 찾을지"를 정하는, 훨씬 민감한 등록 행위다. 그래서:
//  - 서버(WantedPersonController)가 반드시 로그인한 사용자만 허용하고, 누가
//    등록했는지(registeredByName) 기록해서 이 화면에도 그대로 보여준다.
//  - 등록 직후 상태는 즉시 확정되지 않는다(PENDING) - 파이썬 임베딩 생성이
//    끝나야 REGISTERED/FAILED로 바뀌므로, 등록 버튼 누른 뒤 목록을 한 번 더
//    새로고침해서 최종 상태를 확인해야 한다(주기적 자동 새로고침으로 처리).
export default function WantedPersonManagerModal({ onClose, onChanged }) {
  const [people, setPeople] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [file, setFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [listQuery, setListQuery] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setLoadError('')
    fetchWantedPersons()
      .then((list) => setPeople(Array.isArray(list) ? list : []))
      .catch((err) => setLoadError(err.message || '목록을 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // PENDING 상태(임베딩 생성 진행 중)인 항목이 하나라도 있으면 3초마다 자동
  // 새로고침 - 관제요원이 수동으로 새로고침 버튼을 계속 누르지 않아도 됨.
  useEffect(() => {
    const hasPending = people.some((p) => p.status === 'PENDING')
    if (!hasPending) return
    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [people, load])

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleFileChange = (e) => {
    setFile(e.target.files?.[0] || null)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')

    if (!form.wantedId.trim() || !form.name.trim()) {
      setFormError('수배자 ID와 이름은 필수입니다.')
      return
    }
    if (form.name.includes('_')) {
      setFormError('이름에 밑줄(_) 문자는 사용할 수 없습니다.')
      return
    }
    if (!file) {
      setFormError('등록할 사진을 선택해주세요.')
      return
    }

    setSubmitting(true)
    try {
      await createWantedPerson({ wantedId: form.wantedId.trim(), name: form.name.trim(), file })
      setForm(EMPTY_FORM)
      setFile(null)
      load()
      onChanged?.()
    } catch (err) {
      setFormError(err.message || '등록에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (person) => {
    if (!window.confirm(`"${person.name}" (${person.wantedId})을(를) 수배자 명단에서 삭제할까요?\n` +
      '삭제하면 즉시 얼굴 인식 대상에서 제외됩니다.')) return
    setBusyId(person.id)
    try {
      await deleteWantedPerson(person.id)
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '삭제에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const visiblePeople = [...people]
    .filter((p) => {
      const q = listQuery.trim().toLowerCase()
      if (!q) return true
      return p.name.toLowerCase().includes(q) || p.wantedId.toLowerCase().includes(q)
    })

  return (
    <div className="cam-mgr-overlay" onClick={onClose}>
      <div className="cam-mgr-box" onClick={(e) => e.stopPropagation()}>
        <div className="cam-mgr-head">
          <h2>수배자 관리</h2>
          <button type="button" className="cam-mgr-close" onClick={onClose}>닫기 ✕</button>
        </div>

        <form className="cam-mgr-form" onSubmit={handleSubmit}>
          <label>
            <span>수배자 ID</span>
            <input
              type="text"
              placeholder="예: W005"
              value={form.wantedId}
              onChange={(e) => setForm((prev) => ({ ...prev, wantedId: e.target.value }))}
            />
          </label>
          <label className="grow">
            <span>이름</span>
            <input
              type="text"
              placeholder="예: 홍길동 (밑줄(_) 문자 불가)"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            />
          </label>
          <label className="grow">
            <span>등록 사진 (정면 권장)</span>
            <input type="file" accept="image/jpeg,image/png" onChange={handleFileChange} disabled={submitting} />
          </label>
          <button type="submit" className="cam-mgr-submit-btn" disabled={submitting}>
            {submitting ? '등록 중...' : '등록'}
          </button>
        </form>
        {formError && <div className="cam-mgr-form-error">{formError}</div>}

        <div className="cam-mgr-list-search">
          <input
            type="text"
            placeholder="이름 또는 수배자 ID로 검색..."
            value={listQuery}
            onChange={(e) => setListQuery(e.target.value)}
          />
          {listQuery && (
            <button type="button" className="cam-mgr-list-search-clear" onClick={() => setListQuery('')}>
              지우기
            </button>
          )}
        </div>

        <div className="cam-mgr-list">
          {loading && <div className="cam-mgr-empty">불러오는 중...</div>}
          {!loading && loadError && <div className="cam-mgr-empty cam-mgr-error">{loadError}</div>}
          {!loading && !loadError && people.length === 0 && (
            <div className="cam-mgr-empty">등록된 수배자가 없습니다.</div>
          )}
          {!loading && !loadError && people.length > 0 && visiblePeople.length === 0 && (
            <div className="cam-mgr-empty">"{listQuery}"와 일치하는 수배자가 없습니다.</div>
          )}
          {!loading && !loadError && visiblePeople.map((p) => (
            <div key={p.id} className="cam-mgr-row">
              {p.photoUrl
                ? <img className="wp-mgr-thumb" src={p.photoUrl} alt={p.name} />
                : <div className="wp-mgr-thumb wp-mgr-thumb-empty">사진</div>}
              <div className="cam-mgr-row-main">
                <div className="cam-mgr-row-title">
                  {p.name} <span className="cam-mgr-row-camid">{p.wantedId}</span>
                  <span className={`wp-mgr-status wp-mgr-status-${p.status?.toLowerCase()}`}>
                    {STATUS_LABEL[p.status] || p.status}
                  </span>
                </div>
                <div className="cam-mgr-row-sub">
                  등록자: {p.registeredByName || '알 수 없음'} ·{' '}
                  {p.createdAt ? new Date(p.createdAt).toLocaleString('ko-KR') : '-'}
                </div>
                {p.status === 'FAILED' && p.failureReason && (
                  <div className="wp-mgr-failure-reason">{p.failureReason}</div>
                )}
              </div>
              <div className="cam-mgr-row-actions">
                <div className="cam-mgr-danger-zone">
                  <button
                    type="button"
                    className="cam-mgr-delete-btn"
                    disabled={busyId === p.id}
                    onClick={() => handleDelete(p)}
                  >
                    삭제
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
