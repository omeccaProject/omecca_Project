import { useCallback, useEffect, useState } from 'react'
import { fetchCameras, createCamera, updateCamera, deleteCamera } from '../api'

const EMPTY_FORM = { camId: '', name: '', streamUrl: '', streamFormat: 'HLS' }

// 카메라 마스터 데이터 관리 모달. CctvGrid 헤더의 "카메라 관리" 버튼으로 연다.
// 실제 설치된 카메라 목록(cam_id/이름/실시간 영상 URL)을 여기서 등록·수정·삭제한다 —
// 이걸 하기 전엔 event.camId로 몇 대가 설치돼 있는지조차 정확히 알 방법이 없었다.
export default function CameraManagerModal({ onClose, onChanged }) {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setLoadError('')
    fetchCameras()
      .then((list) => setCameras(Array.isArray(list) ? list : []))
      .catch((err) => setLoadError(err.message || '목록을 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleFieldChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')

    if (!form.camId.trim() || !form.name.trim()) {
      setFormError('cam_id와 이름은 필수입니다.')
      return
    }

    setSubmitting(true)
    try {
      await createCamera({
        camId: form.camId.trim(),
        name: form.name.trim(),
        streamUrl: form.streamUrl.trim() || undefined,
        streamFormat: form.streamUrl.trim() ? form.streamFormat : undefined,
      })
      setForm(EMPTY_FORM)
      load()
      onChanged?.()
    } catch (err) {
      setFormError(err.message || '등록에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggleStatus = async (cam) => {
    setBusyId(cam.id)
    try {
      await updateCamera(cam.id, { status: cam.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE' })
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '상태 변경에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async (cam) => {
    if (!window.confirm(`"${cam.name}" (${cam.camId})을(를) 삭제할까요?`)) return
    setBusyId(cam.id)
    try {
      await deleteCamera(cam.id)
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '삭제에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="cam-mgr-overlay" onClick={onClose}>
      <div className="cam-mgr-box" onClick={(e) => e.stopPropagation()}>
        <div className="cam-mgr-head">
          <h2>카메라 관리</h2>
          <button type="button" className="cam-mgr-close" onClick={onClose}>닫기 ✕</button>
        </div>

        <form className="cam-mgr-form" onSubmit={handleSubmit}>
          <label>
            <span>cam_id</span>
            <input
              type="text"
              placeholder="예: CAM-01, L010263"
              value={form.camId}
              onChange={handleFieldChange('camId')}
            />
          </label>
          <label className="grow">
            <span>이름/위치</span>
            <input
              type="text"
              placeholder="예: 강남대로 교차로"
              value={form.name}
              onChange={handleFieldChange('name')}
            />
          </label>
          <label className="grow">
            <span>실시간 영상 URL(선택)</span>
            <input
              type="text"
              placeholder="없으면 비워두세요"
              value={form.streamUrl}
              onChange={handleFieldChange('streamUrl')}
            />
          </label>
          <label>
            <span>형식</span>
            <select value={form.streamFormat} onChange={handleFieldChange('streamFormat')} disabled={!form.streamUrl.trim()}>
              <option value="HLS">HLS</option>
              <option value="MP4">MP4</option>
            </select>
          </label>
          <button type="submit" className="cam-mgr-submit-btn" disabled={submitting}>
            {submitting ? '등록 중...' : '등록'}
          </button>
        </form>
        {formError && <div className="cam-mgr-form-error">{formError}</div>}

        <div className="cam-mgr-list">
          {loading && <div className="cam-mgr-empty">불러오는 중...</div>}
          {!loading && loadError && <div className="cam-mgr-empty cam-mgr-error">{loadError}</div>}
          {!loading && !loadError && cameras.length === 0 && (
            <div className="cam-mgr-empty">등록된 카메라가 없습니다.</div>
          )}
          {!loading && !loadError && cameras.map((cam) => (
            <div key={cam.id} className={`cam-mgr-row ${cam.status === 'INACTIVE' ? 'inactive' : ''}`}>
              <span className={`cam-mgr-live-badge ${cam.streamUrl ? 'on' : ''}`}>
                {cam.streamUrl ? 'LIVE' : '미연결'}
              </span>
              <div className="cam-mgr-row-main">
                <div className="cam-mgr-row-title">{cam.name} <span className="cam-mgr-row-camid">{cam.camId}</span></div>
                <div className="cam-mgr-row-sub">
                  {cam.status === 'ACTIVE' ? '운영 중' : '비활성'}
                  {cam.streamUrl ? ` · ${cam.streamFormat || '스트림'} 연결됨` : ' · 실시간 영상 없음'}
                </div>
              </div>
              <button
                type="button"
                className="cam-mgr-toggle-btn"
                disabled={busyId === cam.id}
                onClick={() => handleToggleStatus(cam)}
              >
                {cam.status === 'ACTIVE' ? '비활성화' : '활성화'}
              </button>
              <button
                type="button"
                className="cam-mgr-delete-btn"
                disabled={busyId === cam.id}
                onClick={() => handleDelete(cam)}
              >
                삭제
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
