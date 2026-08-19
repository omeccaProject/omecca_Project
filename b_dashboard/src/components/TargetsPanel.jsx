import { useCallback, useEffect, useState } from 'react'
import { fetchTargets, createTarget, closeTarget } from '../api'
import { getUser } from '../auth'
import { VEHICLE_MODEL_SUGGESTIONS, VEHICLE_COLOR_OPTIONS } from '../constants'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

const STATUS_TABS = [
  { value: '', label: '전체' },
  { value: 'ACTIVE', label: '추적 중' },
  { value: 'CLOSED', label: '종료됨' },
]

const EMPTY_FORM = { targetType: 'VEHICLE', plateNumber: '', personRefId: '', label: '', color: '', colorCustom: '', vehicleModel: '' }

// 관심 대상(target) 등록/조회/추적종료 화면. 사이드바 "관심 대상"에서 들어온다.
// 백엔드 API(/api/targets)는 이미 완성돼있어서(TargetController/TargetService), 여기는 그 위의
// 화면만 새로 붙인 것 — curl로만 가능하던 등록/종료를 관제요원이 화면에서 직접 할 수 있게 함.
export default function TargetsPanel({ onChanged }) {
  const [statusFilter, setStatusFilter] = useState('ACTIVE')
  const [targets, setTargets] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [closingId, setClosingId] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setLoadError('')
    fetchTargets(statusFilter)
      .then((list) => setTargets(Array.isArray(list) ? list : []))
      .catch((err) => setLoadError(err.message || '목록을 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }, [statusFilter])

  useEffect(() => {
    load()
  }, [load])

  const handleFieldChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')

    if (form.targetType === 'VEHICLE' && !form.plateNumber.trim()) {
      setFormError('차량 번호판을 입력해주세요.')
      return
    }
    if (form.targetType === 'PERSON' && !form.personRefId.trim()) {
      setFormError('인물 식별 ID를 입력해주세요.')
      return
    }

    const registeredBy = getUser()?.username || getUser()?.name || 'operator'

    setSubmitting(true)
    try {
      const resolvedColor = form.color === '기타' ? form.colorCustom.trim() : form.color
      await createTarget({
        targetType: form.targetType,
        plateNumber: form.targetType === 'VEHICLE' ? form.plateNumber.trim() : undefined,
        personRefId: form.targetType === 'PERSON' ? form.personRefId.trim() : undefined,
        label: form.label.trim() || undefined,
        color: form.targetType === 'VEHICLE' ? (resolvedColor || undefined) : undefined,
        vehicleModel: form.targetType === 'VEHICLE' ? (form.vehicleModel.trim() || undefined) : undefined,
        registeredBy,
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

  const handleClose = async (target) => {
    if (!window.confirm(`"${target.label || target.plateNumber || target.personRefId}" 추적을 종료할까요?`)) return
    setClosingId(target.id)
    try {
      await closeTarget(target.id)
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '추적 종료에 실패했습니다.')
    } finally {
      setClosingId(null)
    }
  }

  return (
    <section className="panel targets-panel">
      <h2>관심 대상 관리</h2>

      <form className="targets-form" onSubmit={handleSubmit}>
        <div className="targets-form-row">
          <label>
            <span>유형</span>
            <select value={form.targetType} onChange={handleFieldChange('targetType')}>
              <option value="VEHICLE">차량</option>
              <option value="PERSON">인물</option>
            </select>
          </label>

          {form.targetType === 'VEHICLE' ? (
            <label className="grow">
              <span>차량 번호판</span>
              <input
                type="text"
                placeholder="예: 12가3456"
                value={form.plateNumber}
                onChange={handleFieldChange('plateNumber')}
              />
            </label>
          ) : (
            <label className="grow">
              <span>인물 식별 ID</span>
              <input
                type="text"
                placeholder="예: person-0021 (수배자 DB 참조 ID)"
                value={form.personRefId}
                onChange={handleFieldChange('personRefId')}
              />
            </label>
          )}

          {form.targetType === 'VEHICLE' && (
            <>
              <label>
                <span>차량 색상</span>
                <select value={form.color} onChange={handleFieldChange('color')}>
                  <option value="">선택 안 함</option>
                  {VEHICLE_COLOR_OPTIONS.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
              {form.color === '기타' && (
                <label>
                  <span>색상 직접 입력</span>
                  <input
                    type="text"
                    placeholder="예: 청록색"
                    value={form.colorCustom}
                    onChange={handleFieldChange('colorCustom')}
                  />
                </label>
              )}
              <label className="grow">
                <span>차종</span>
                <input
                  type="text"
                  list="vehicle-model-suggestions"
                  placeholder="예: 아반떼CN7, 싼타페"
                  value={form.vehicleModel}
                  onChange={handleFieldChange('vehicleModel')}
                />
                <datalist id="vehicle-model-suggestions">
                  {VEHICLE_MODEL_SUGGESTIONS.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </label>
            </>
          )}

          <label className="grow">
            <span>메모(선택)</span>
            <input
              type="text"
              placeholder="예: 절도 용의 차량"
              value={form.label}
              onChange={handleFieldChange('label')}
            />
          </label>

          <button type="submit" className="targets-submit-btn" disabled={submitting}>
            {submitting ? '등록 중...' : '등록'}
          </button>
        </div>
        {formError && <div className="targets-form-error">{formError}</div>}
      </form>

      <div className="targets-tabs">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={statusFilter === tab.value ? 'active' : ''}
            onClick={() => setStatusFilter(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="targets-list">
        {loading && <div className="targets-empty">불러오는 중...</div>}
        {!loading && loadError && <div className="targets-empty targets-error">{loadError}</div>}
        {!loading && !loadError && targets.length === 0 && (
          <div className="targets-empty">등록된 관심 대상이 없습니다.</div>
        )}
        {!loading && !loadError && targets.map((t) => (
          <div key={t.id} className={`targets-row ${t.status === 'CLOSED' ? 'closed' : ''}`}>
            <span className={`targets-type-badge ${t.targetType === 'VEHICLE' ? 'vehicle' : 'person'}`}>
              {t.targetType === 'VEHICLE' ? '차량' : '인물'}
            </span>
            <div className="targets-row-main">
              <div className="targets-row-title">
                {t.targetType === 'VEHICLE' ? (t.plateNumber || '-') : (t.personRefId || '-')}
                {t.targetType === 'VEHICLE' && (t.color || t.vehicleModel)
                  ? ` · ${[t.color, t.vehicleModel].filter(Boolean).join(' ')}`
                  : ''}
                {t.label ? ` · ${t.label}` : ''}
              </div>
              <div className="targets-row-sub">
                {t.registeredBy} 등록 · {fmtTime(t.createdAt)}
                {t.status === 'CLOSED' && t.closedAt ? ` · 종료: ${fmtTime(t.closedAt)}` : ''}
              </div>
            </div>
            {t.status === 'ACTIVE' ? (
              <button
                type="button"
                className="targets-close-btn"
                disabled={closingId === t.id}
                onClick={() => handleClose(t)}
              >
                {closingId === t.id ? '처리 중...' : '추적 종료'}
              </button>
            ) : (
              <span className="targets-closed-chip">종료됨</span>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
