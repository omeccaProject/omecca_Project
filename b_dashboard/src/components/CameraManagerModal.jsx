import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCameras, createCamera, updateCamera, deleteCamera, fetchCameraCatalog, uploadCameraVideo } from '../api'

const EMPTY_FORM = { camId: '', name: '', streamUrl: '', streamFormat: 'HLS', debrisDetectionEnabled: false, uturnDetectionEnabled: false, signalDetectionEnabled: false, personRiskDetectionEnabled: false }

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

  // 등록된 카메라 목록 검색 - 이름/cam_id로 입력하는 즉시 필터링된다.
  const [listQuery, setListQuery] = useState('')

  // UTIC 카메라 사전 등록 카탈로그 자동완성(고도화). cam_id나 이름 입력창에 타이핑하면
  // /api/camera-catalog를 debounce로 검색해서 후보를 보여주고, 하나를 고르면 streamUrl까지
  // 자동으로 채워준다 - 매번 URL을 직접 복사/붙여넣기 하지 않아도 되게 하는 게 목적.
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchTimerRef = useRef(null)

  // 동영상 파일 업로드로 카메라 등록(실시간 URL 대신). 업로드가 끝나면 반환된 URL을
  // streamUrl에 그대로 채워서, 아래 등록 로직은 URL을 직접 입력했을 때와 동일하게 탄다.
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = '' // 같은 파일을 다시 선택해도 onChange가 또 발생하게
    if (!file) return

    setUploadError('')
    setUploading(true)
    try {
      const { url } = await uploadCameraVideo(file)
      setForm((prev) => ({ ...prev, streamUrl: url, streamFormat: 'MP4' }))
    } catch (err) {
      setUploadError(err.message || '영상 업로드에 실패했습니다.')
    } finally {
      setUploading(false)
    }
  }

  useEffect(() => () => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
  }, [])

  // [개선] ESC 키로도 모달을 닫을 수 있게 함 - 예전엔 마우스로 바깥 클릭하거나
  // "닫기" 버튼만 눌러야 했음. 키보드 단축키는 관제실처럼 마우스보다 키보드
  // 조작이 잦을 수 있는 환경에서 사용성을 개선한다.
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const searchCatalog = (query) => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    if (!query.trim()) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    searchTimerRef.current = setTimeout(() => {
      fetchCameraCatalog(query.trim())
        .then((list) => {
          setSuggestions(Array.isArray(list) ? list : [])
          setShowSuggestions(true)
        })
        .catch(() => {
          // 자동완성은 등록을 돕는 보조 기능이라, 검색이 실패해도 직접 입력은 그대로 가능해야
          // 한다 - 에러를 화면에 띄우지 않고 조용히 후보만 비운다.
          setSuggestions([])
        })
    }, 250)
  }

  const handlePickSuggestion = (item) => {
    setForm((prev) => ({
      ...prev,
      camId: item.camId,
      name: item.name,
      streamUrl: item.streamUrl || '',
      streamFormat: item.streamFormat || 'HLS',
    }))
    setShowSuggestions(false)
    setSuggestions([])
  }

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
    const value = e.target.value
    setForm((prev) => ({ ...prev, [field]: value }))
    if (field === 'camId' || field === 'name') {
      searchCatalog(value)
    }
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
        debrisDetectionEnabled: form.debrisDetectionEnabled,
        uturnDetectionEnabled: form.uturnDetectionEnabled,
        signalDetectionEnabled: form.signalDetectionEnabled,
        violationDetectionEnabled: form.uturnDetectionEnabled || form.signalDetectionEnabled,
        personRiskDetectionEnabled: form.personRiskDetectionEnabled,
      })
      setForm(EMPTY_FORM)
      setSuggestions([])
      setShowSuggestions(false)
      load()
      onChanged?.()
    } catch (err) {
      setFormError(err.message || '등록에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  // 이미 등록된 카메라의 낙하물 감지 사용 여부를 토글한다(등록 폼의 체크박스와 별개로,
  // 기존 카메라도 삭제/재등록 없이 켜고 끌 수 있어야 하므로).
  const handleToggleDebris = async (cam) => {
    setBusyId(cam.id)
    try {
      await updateCamera(cam.id, { debrisDetectionEnabled: !cam.debrisDetectionEnabled })
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '낙하물 감지 설정 변경에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleUturn = async (cam) => {
    setBusyId(cam.id)
    try {
      await updateCamera(cam.id, { uturnDetectionEnabled: !cam.uturnDetectionEnabled })
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '불법유턴 감지 설정 변경에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleSignal = async (cam) => {
    setBusyId(cam.id)
    try {
      await updateCamera(cam.id, { signalDetectionEnabled: !cam.signalDetectionEnabled })
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '신호위반 감지 설정 변경에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  // 이미 등록된 카메라의 수배자/흉기(C파트) 감지 사용 여부를 토글한다.
  const handleTogglePersonRisk = async (cam) => {
    setBusyId(cam.id)
    try {
      await updateCamera(cam.id, { personRiskDetectionEnabled: !cam.personRiskDetectionEnabled })
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '수배자/흉기 감지 설정 변경에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleStatus = async (cam) => {
    setBusyId(cam.id)
    try {
      const activating = cam.status !== 'ACTIVE'
      const payload = { status: activating ? 'ACTIVE' : 'INACTIVE' }

      // 비활성 → 활성화로 전환하는데 이 카메라에 아직 실시간 영상 URL이 등록돼 있지 않다면
      // (예: URL 없이 먼저 등록해뒀거나, 등록 이후에 UTIC 카탈로그가 채워진 경우), 같은
      // cam_id로 카탈로그를 찾아서 streamUrl/streamFormat까지 같이 채워 넣는다 - 그래야
      // "활성화" 버튼만 눌러도 바로 CCTV 영상이 뜬다(사용자가 매번 URL을 직접 찾아
      // 입력해야 하는 번거로움을 없애는 게 목적).
      if (activating && !cam.streamUrl) {
        try {
          const matches = await fetchCameraCatalog(cam.camId)
          const catalogMatch = (Array.isArray(matches) ? matches : []).find((m) => m.camId === cam.camId)
          if (catalogMatch?.streamUrl) {
            payload.streamUrl = catalogMatch.streamUrl
            payload.streamFormat = catalogMatch.streamFormat || 'HLS'
          }
        } catch {
          // 카탈로그 조회가 실패해도 활성화 자체는 계속 진행한다 - 영상 없이 활성화될 뿐,
          // 상태 변경까지 막을 이유는 없다.
        }
      }

      await updateCamera(cam.id, payload)
      load()
      onChanged?.()
    } catch (err) {
      alert(err.message || '상태 변경에 실패했습니다.')
    } finally {
      setBusyId(null)
    }
  }

  // 목록은 항상 이름 기준 가나다순(ㄱㄴㄷㄹ...)으로 정렬해서 보여주고, 검색어가 있으면
  // 이름 또는 cam_id에 포함되는 것만 즉시 걸러서 보여준다 - 카메라가 많아질수록 원하는
  // 카메라를 스크롤로 찾기 힘들어지는 문제를 해결하기 위함.
  const visibleCameras = [...cameras]
    .filter((cam) => {
      const q = listQuery.trim().toLowerCase()
      if (!q) return true
      return cam.name.toLowerCase().includes(q) || cam.camId.toLowerCase().includes(q)
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'ko'))

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
          {/* cam_id/이름 입력창 + UTIC 카탈로그 자동완성 드롭다운. 후보를 고르면
              streamUrl/streamFormat까지 자동으로 채워진다(handlePickSuggestion). */}
          <div className="cam-mgr-autocomplete-wrap">
            <label>
              <span>cam_id</span>
              <input
                type="text"
                placeholder="예: CAM-01, L010263"
                value={form.camId}
                onChange={handleFieldChange('camId')}
                onFocus={() => { if (suggestions.length) setShowSuggestions(true) }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              />
            </label>
            <label className="grow">
              <span>이름/위치</span>
              <input
                type="text"
                placeholder="예: 강남대로 교차로"
                value={form.name}
                onChange={handleFieldChange('name')}
                onFocus={() => { if (suggestions.length) setShowSuggestions(true) }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              />
            </label>
            {showSuggestions && suggestions.length > 0 && (
              <div className="cam-mgr-suggest-list">
                {suggestions.map((item) => (
                  <button
                    type="button"
                    key={item.camId}
                    className="cam-mgr-suggest-item"
                    // onClick 대신 onMouseDown - input의 onBlur(150ms 딜레이)보다 먼저 발생시켜서
                    // 클릭이 blur에 의해 드롭다운이 닫히기 전에 확실히 반영되게 한다.
                    onMouseDown={(e) => {
                      e.preventDefault()
                      handlePickSuggestion(item)
                    }}
                  >
                    <span className="cam-mgr-suggest-camid">{item.camId}</span>
                    <span className="cam-mgr-suggest-name">{item.name}</span>
                    <span className="cam-mgr-suggest-badge">URL 자동입력</span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
          <label>
            <span>또는 동영상 업로드</span>
            <input type="file" accept="video/mp4,video/webm,video/quicktime" onChange={handleFileUpload} disabled={uploading} />
          </label>

          {/* [수정] 체크박스 4개를 전용 wrapper로 묶어서 2x2 그리드로 항상 깔끔하게
              정렬되게 함 (App.css의 .cam-mgr-checkbox-group). 예전엔 다른 입력창들과
              같은 flex 줄에 섞여서, 개수가 늘어날 때마다 줄바꿈 위치가 어긋났었음. */}
          <div className="cam-mgr-checkbox-group">
            <label className="cam-mgr-checkbox">
              <input
                type="checkbox"
                checked={form.debrisDetectionEnabled}
                onChange={(e) => setForm((prev) => ({ ...prev, debrisDetectionEnabled: e.target.checked }))}
              />
              <span>낙하물 감지 사용</span>
            </label>
            <label className="cam-mgr-checkbox">
              <input
                type="checkbox"
                checked={form.uturnDetectionEnabled}
                onChange={(e) => setForm((prev) => ({ ...prev, uturnDetectionEnabled: e.target.checked }))}
              />
              <span>불법유턴 감지 사용</span>
            </label>
            <label className="cam-mgr-checkbox">
              <input
                type="checkbox"
                checked={form.signalDetectionEnabled}
                onChange={(e) => setForm((prev) => ({ ...prev, signalDetectionEnabled: e.target.checked }))}
              />
              <span>신호위반 감지 사용</span>
            </label>
            <label className="cam-mgr-checkbox">
              <input
                type="checkbox"
                checked={form.personRiskDetectionEnabled}
                onChange={(e) => setForm((prev) => ({ ...prev, personRiskDetectionEnabled: e.target.checked }))}
              />
              <span>수배자/흉기 감지 사용</span>
            </label>
          </div>

          <button type="submit" className="cam-mgr-submit-btn" disabled={submitting || uploading}>
            {submitting ? '등록 중...' : uploading ? '영상 업로드 중...' : '등록'}
          </button>
        </form>
        {uploadError && <div className="cam-mgr-form-error">{uploadError}</div>}
        {formError && <div className="cam-mgr-form-error">{formError}</div>}

        <div className="cam-mgr-list-search">
          <input
            type="text"
            placeholder="이름 또는 cam_id로 검색..."
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
          {!loading && !loadError && cameras.length === 0 && (
            <div className="cam-mgr-empty">등록된 카메라가 없습니다.</div>
          )}
          {!loading && !loadError && cameras.length > 0 && visibleCameras.length === 0 && (
            <div className="cam-mgr-empty">"{listQuery}"와 일치하는 카메라가 없습니다.</div>
          )}
          {!loading && !loadError && visibleCameras.map((cam) => (
            <div key={cam.id} className={`cam-mgr-row ${cam.status === 'INACTIVE' ? 'inactive' : ''}`}>
              <span className={`cam-mgr-live-badge ${cam.streamUrl ? 'on' : ''}`}>
                {cam.streamUrl ? 'LIVE' : '미연결'}
              </span>
              <div className="cam-mgr-row-main">
                <div className="cam-mgr-row-title">
                  {cam.name} <span className="cam-mgr-row-camid">{cam.camId}</span>
                  {cam.debrisDetectionEnabled && <span className="cam-tag-debris">(낙하물)</span>}
                  {cam.uturnDetectionEnabled && <span className="cam-tag-debris">(불법유턴)</span>}
                  {cam.signalDetectionEnabled && <span className="cam-tag-debris">(신호위반)</span>}
                  {cam.personRiskDetectionEnabled && <span className="cam-tag-person-risk">(수배자/흉기)</span>}
                </div>
                <div className="cam-mgr-row-sub">
                  {cam.status === 'ACTIVE' ? '운영 중' : '비활성'}
                  {cam.streamUrl ? ` · ${cam.streamFormat || '스트림'} 연결됨` : ' · 실시간 영상 없음'}
                </div>
              </div>

              {/* [수정] 버튼 5개를 전용 wrapper(cam-mgr-row-actions)로 묶어서 항상
                  다음 줄에 표시되게 함. 예전엔 이 버튼들이 cam-mgr-row-main과 같은
                  줄에서 고정폭을 다 차지하는 바람에, 제목 영역(min-width:0)이
                  극단적으로 압축되어 글자가 세로로 깨지는 문제가 있었음. */}
              <div className="cam-mgr-row-actions">
                <button
                  type="button"
                  className="cam-mgr-toggle-btn"
                  disabled={busyId === cam.id}
                  onClick={() => handleToggleDebris(cam)}
                >
                  {cam.debrisDetectionEnabled ? '낙하물 끄기' : '낙하물 켜기'}
                </button>
                <button
                  type="button"
                  className="cam-mgr-toggle-btn"
                  disabled={busyId === cam.id}
                  onClick={() => handleToggleUturn(cam)}
                >
                  {cam.uturnDetectionEnabled ? '불법유턴 끄기' : '불법유턴 켜기'}
                </button>
                <button
                  type="button"
                  className="cam-mgr-toggle-btn"
                  disabled={busyId === cam.id}
                  onClick={() => handleToggleSignal(cam)}
                >
                  {cam.signalDetectionEnabled ? '신호위반 끄기' : '신호위반 켜기'}
                </button>
                <button
                  type="button"
                  className="cam-mgr-toggle-btn"
                  disabled={busyId === cam.id}
                  onClick={() => handleTogglePersonRisk(cam)}
                >
                  {cam.personRiskDetectionEnabled ? '수배자/흉기 끄기' : '수배자/흉기 켜기'}
                </button>
                <button
                  type="button"
                  className="cam-mgr-toggle-btn"
                  disabled={busyId === cam.id}
                  onClick={() => handleToggleStatus(cam)}
                >
                  {cam.status === 'ACTIVE' ? '비활성화' : '활성화'}
                </button>
                {/* [개선] 삭제 버튼을 전용 구역(cam-mgr-danger-zone)으로 분리 -
                    바쁜 관제 상황에서 다른 토글 버튼과 헷갈려 실수로 삭제를
                    누르는 걸 방지하기 위해, 구분선을 두고 시각적으로 떨어뜨림 */}
                <div className="cam-mgr-danger-zone">
                  <button
                    type="button"
                    className="cam-mgr-delete-btn"
                    disabled={busyId === cam.id}
                    onClick={() => handleDelete(cam)}
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
