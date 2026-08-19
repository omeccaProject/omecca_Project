import { useCallback, useEffect, useState } from 'react'
import { EVENT_LABEL } from '../constants'
import { REAL_CAMERAS as FALLBACK_REAL_CAMERAS } from '../realCameras'
import { fetchCameras } from '../api'
import Badge from './Badge'
import FrameImage from './FrameImage'
import LiveHlsVideo from './LiveHlsVideo'
import CameraManagerModal from './CameraManagerModal'

// 아직 이벤트가 안 들어온 카메라도 그리드에 자리를 채워두기 위한 기본 목록.
// 실제 카메라 목록 API가 생기면 이 상수 대신 그걸 쓰면 됨. 3분할 모드(모니터
// 2/3에 9개씩, 총 18개)까지 커버해야 하므로 18개까지 준비해둠.
const FALLBACK_CAMS = [
  'CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05', 'CAM-06',
  'CAM-07', 'CAM-08', 'CAM-09', 'CAM-10', 'CAM-11', 'CAM-12',
  'CAM-13', 'CAM-14', 'CAM-15', 'CAM-16', 'CAM-17', 'CAM-18',
]

const CAM_COUNT_OPTIONS = [6, 9]
const CAM_COUNT_STORAGE_KEY = 'omecca_cctv_cam_count'
// 사용자가 특정 칸에 직접 지정한 카메라 배정 - { [전역 슬롯 인덱스]: camId }.
// localStorage에 저장해서 새로고침해도 유지되고, 'storage' 이벤트로 다른 창(메인 대시보드 ↔
// 분할화면 monitor2/3)끼리도 같은 배정이 즉시 동기화되게 한다.
const MANUAL_SLOT_STORAGE_KEY = 'omecca_cctv_manual_slots'

function loadManualSlots() {
  try {
    const raw = localStorage.getItem(MANUAL_SLOT_STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

// camOffset: 카메라 목록에서 몇 번째부터 보여줄지 (3분할 모드에서 모니터2=0, 모니터3=9로
//            넘겨서 두 창이 서로 겹치지 않는 9개씩을 나눠 보여준다).
// fixedCount: 지정되면 6/9 토글 UI를 숨기고 이 개수로 고정한다 (3분할 모드는 항상 9개 고정,
//             화면을 꽉 채워서 보여준다 - App.css의 .kiosk-cctv-fill 참고).
export default function CctvGrid({ events, focusedEvent, onSelectCam, camOffset = 0, fixedCount = null }) {
  // 화면에 몇 개 카메라를 보여줄지(6 또는 9). localStorage에 저장해서
  // 3분할 모니터의 CCTV 창을 새로고침해도 마지막에 고른 개수가 유지되게 함.
  const [camCount, setCamCount] = useState(() => {
    if (fixedCount) return fixedCount
    const saved = Number(localStorage.getItem(CAM_COUNT_STORAGE_KEY))
    return CAM_COUNT_OPTIONS.includes(saved) ? saved : 6
  })

  // 클릭해서 확대한 카메라 ID. null이면 확대 화면 없음.
  const [zoomedCamId, setZoomedCamId] = useState(null)

  // 카메라 마스터 데이터 관리 모달. 3분할 모드(fixedCount)에서는 안 띄운다(운영 화면이라).
  const [showCameraManager, setShowCameraManager] = useState(false)

  // 실시간 영상이 연결된 카메라 목록. 이제 하드코딩된 realCameras.js가 아니라
  // "카메라 관리"에서 등록한 DB(camera 테이블) 데이터를 직접 불러온다 — 등록 즉시
  // 그리드뷰어에 반영되게 하기 위함. /api/cameras가 아직 없거나(마이그레이션 전) 응답이
  // 비어있으면 realCameras.js를 폴백으로 써서 화면이 깨지지 않게 한다.
  const [liveCameras, setLiveCameras] = useState(FALLBACK_REAL_CAMERAS)

  // "카메라 관리" API가 실제로 응답해서 알려준 실제 등록 카메라들이 그리드에서 어느 칸에
  // 나올지를 정하는 슬롯 배정 목록(인덱스 = 칸 위치, 값 = 그 칸에 배정된 camId).
  // 규칙:
  //  1) 이미 슬롯을 가진 카메라가 계속 활성 상태면 그 자리 그대로 유지한다(다른 카메라가
  //     밀고 들어오지 않음 - 삭제/비활성화 시 "다른 cctv가 자리를 채운다"는 문제 방지).
  //  2) 어떤 슬롯의 카메라가 비활성화되면 그 슬롯은 "빈 자리"가 되고 idle로 표시된다.
  //  3) 새로 활성화된 카메라는 먼저 빈 자리가 있으면 그 자리부터 채우고, 빈 자리가 하나도
  //     없을 때만 새 슬롯을 맨 뒤에 추가한다 - 그래야 비활성화한 칸에 다른 카메라를 새로
  //     활성화했을 때 바로 그 자리에서 보인다(화면 밖 슬롯으로 밀려나 안 보이는 문제 방지).
  // 주의: 초기값/폴백값(FALLBACK_REAL_CAMERAS)은 절대 여기 섞지 않는다 - 섞으면 아직 API가
  // 응답하기 전의 임시 목록이 "진짜 등록된 카메라"보다 먼저 자리를 선점해버려서, 실제로
  // 등록·활성화된 카메라가 뒤로 밀려나 그리드 화면 밖으로 벗어나는 회귀가 생긴다.
  const [slots, setSlots] = useState([])

  // 사용자가 "이 칸엔 이 카메라" 식으로 직접 고정한 배정. 자동 슬롯 배정(slots)보다 항상
  // 우선한다 - 명시적으로 요청된 기능("cctv를 자기가 원하는 칸에 넣어서 볼 수 있게").
  const [manualSlots, setManualSlots] = useState(loadManualSlots)

  useEffect(() => {
    localStorage.setItem(MANUAL_SLOT_STORAGE_KEY, JSON.stringify(manualSlots))
  }, [manualSlots])

  useEffect(() => {
    function onStorage(e) {
      if (e.key !== MANUAL_SLOT_STORAGE_KEY) return
      setManualSlots(e.newValue ? JSON.parse(e.newValue) : {})
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // 슬롯 index(전역 그리드 위치)에 camId를 고정하거나(값 있음) 자동 배정으로 되돌린다(null).
  // 같은 카메라가 이미 다른 칸에 고정돼 있으면 그 칸의 고정은 풀어서 한 카메라가 두 칸에
  // 동시에 나오는 걸 막는다.
  function assignSlot(index, camId) {
    setManualSlots((prev) => {
      const next = { ...prev }
      if (camId) {
        Object.keys(next).forEach((key) => {
          if (Number(key) !== index && next[key] === camId) delete next[key]
        })
        next[index] = camId
      } else {
        delete next[index]
      }
      return next
    })
  }

  const loadLiveCameras = useCallback(() => {
    fetchCameras()
      .then((list) => {
        const withStream = (Array.isArray(list) ? list : [])
          .filter((c) => c.status === 'ACTIVE' && c.streamUrl)
          .map((c) => ({ camId: c.camId, name: c.name, videoUrl: c.streamUrl }))
        setLiveCameras(withStream.length > 0 ? withStream : FALLBACK_REAL_CAMERAS)

        // API가 실제로 응답했을 때만(설령 withStream이 아직 비어있더라도) 슬롯을 갱신한다 -
        // 폴백 목록은 절대 반영하지 않는다.
        const liveIds = withStream.map((c) => c.camId)
        setSlots((prev) => {
          const liveSet = new Set(liveIds)
          // 이미 슬롯이 있고 계속 활성 상태인 camId는 그대로 두고, 슬롯이 아직 없는
          // (새로 활성화된) camId만 배정 대상으로 남긴다.
          const alreadySlotted = new Set(prev.filter((id) => id && liveSet.has(id)))
          const newcomers = liveIds.filter((id) => !alreadySlotted.has(id))
          if (newcomers.length === 0) return prev

          // 지금 슬롯 중 "더 이상 활성 상태가 아닌 camId가 남아있는" 빈 자리를 재사용 대상으로 수집.
          const next = [...prev]
          const idleSlotIndexes = []
          next.forEach((id, idx) => {
            if (id && !liveSet.has(id)) idleSlotIndexes.push(idx)
          })

          let idlePtr = 0
          newcomers.forEach((id) => {
            if (idlePtr < idleSlotIndexes.length) {
              next[idleSlotIndexes[idlePtr]] = id
              idlePtr += 1
            } else {
              next.push(id)
            }
          })
          return next
        })
      })
      .catch(() => {
        // API 자체가 아직 없거나(구버전 서버) 실패하면 기존 하드코딩 목록을 그대로 유지.
        // 슬롯은 건드리지 않는다 - 아직 뭐가 진짜 등록된 카메라인지 알 수 없으므로.
        setLiveCameras(FALLBACK_REAL_CAMERAS)
      })
  }, [])

  useEffect(() => {
    loadLiveCameras()
  }, [loadLiveCameras])

  useEffect(() => {
    if (fixedCount) return // 3분할 모드는 항상 9개 고정이므로 저장/동기화할 필요가 없다
    localStorage.setItem(CAM_COUNT_STORAGE_KEY, String(camCount))
  }, [camCount, fixedCount])

  // 다른 모니터(다른 창)에서 카메라 개수를 바꾸면 이 창도 같이 맞춘다 (localStorage는 같은 origin 창끼리 공유됨).
  useEffect(() => {
    if (fixedCount) return
    function onStorage(e) {
      if (e.key !== CAM_COUNT_STORAGE_KEY) return
      const next = Number(e.newValue)
      if (CAM_COUNT_OPTIONS.includes(next)) setCamCount(next)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [fixedCount])

  // ESC로 확대 화면 닫기
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape') setZoomedCamId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const effectiveCount = fixedCount || camCount
  const seenCams = [...new Set(events.map((ev) => ev.camId).filter(Boolean))]
  // 실제로 실시간 영상이 연결된 카메라(liveCameras, DB "카메라 관리"에서 등록된 것)는
  // 항상 그리드 맨 앞에 고정 노출한다.
  const realCameraById = Object.fromEntries(liveCameras.map((c) => [c.camId, c]))
  // slots(진짜 등록된 적 있는 카메라의 칸 배정, 삭제/비활성화돼도 자리 유지 + 새로 활성화된
  // 카메라는 빈 자리부터 채움)를 맨 앞에 둬서 다른 카메라가 밀고 들어오지 않게 하고, 그
  // 다음 liveCameras의 현재 camId(API 응답 전/실패 시의 폴백 목록을 화면에 그대로 보여주기
  // 위함 - slots가 비어있는 그 순간에도 화면이 안 깨지게), seenCams, FALLBACK_CAMS 순서로 채운다.
  const autoCamIdPool = [...new Set([
    ...slots.filter(Boolean),
    ...liveCameras.map((c) => c.camId),
    ...seenCams,
    ...FALLBACK_CAMS,
  ])]

  // manualSlots에 고정된 카메라는 자동 배정 후보 목록에서 빼서, 사용자가 지정한 칸 말고
  // 다른 칸에 같은 카메라가 중복으로 나타나지 않게 한다.
  const pinnedCamIds = new Set(Object.values(manualSlots).filter(Boolean))
  const autoPool = autoCamIdPool.filter((id) => !pinnedCamIds.has(id))

  const usedThisRender = new Set()
  let autoPtr = 0
  const camIds = []
  for (let i = camOffset; i < camOffset + effectiveCount; i++) {
    const pinned = manualSlots[i]
    if (pinned) {
      camIds.push(pinned)
      usedThisRender.add(pinned)
      continue
    }
    while (autoPtr < autoPool.length && usedThisRender.has(autoPool[autoPtr])) autoPtr += 1
    const next = autoPool[autoPtr]
    autoPtr += 1
    if (next) usedThisRender.add(next)
    camIds.push(next ?? `CAM-EMPTY-${i}`)
  }

  const latestByCam = {}
  events.forEach((ev) => {
    const prev = latestByCam[ev.camId]
    if (!prev || new Date(ev.occurredAt) > new Date(prev.occurredAt)) {
      latestByCam[ev.camId] = ev
    }
  })

  function handleCellClick(camId) {
    const latest = latestByCam[camId]
    if (latest) onSelectCam(latest) // 기존 동작 유지: 이벤트가 있으면 다른 모니터 창에도 포커스 전파
    setZoomedCamId(camId) // 확대는 이벤트 유무와 상관없이 항상 가능
  }

  const zoomedLatest = zoomedCamId ? latestByCam[zoomedCamId] : null

  return (
    <section className="panel cctv-panel">
      <div className="cctv-panel-head">
        <h2>CCTV 그리드 뷰어{fixedCount ? ` (${camOffset + 1}~${camOffset + effectiveCount})` : ''}</h2>
        {!fixedCount && (
          <div className="cctv-panel-head-right">
            <button type="button" className="cam-manage-btn" onClick={() => setShowCameraManager(true)}>
              카메라 관리
            </button>
            <div className="cam-count-toggle">
              {CAM_COUNT_OPTIONS.map((n) => (
                <button
                  key={n}
                  className={camCount === n ? 'active' : ''}
                  onClick={() => setCamCount(n)}
                >
                  {n}개
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={`cctv-grid cctv-grid-${effectiveCount}`}>
        {camIds.map((camId, idx) => {
          const slotIndex = camOffset + idx
          const latest = latestByCam[camId]
          const isFocused = focusedEvent?.camId === camId
          const realCam = realCameraById[camId]

          return (
            <div
              key={slotIndex}
              className={`cctv-cell ${isFocused ? 'active' : ''} ${latest ? '' : 'idle'} ${realCam ? 'cctv-cell-live' : ''}`}
              onClick={() => handleCellClick(camId)}
            >
              <div className="cctv-cell-pin" onClick={(e) => e.stopPropagation()}>
                <select
                  className="cctv-cell-pin-select"
                  title="이 칸에 표시할 카메라를 직접 지정"
                  value={manualSlots[slotIndex] || ''}
                  onChange={(e) => assignSlot(slotIndex, e.target.value || null)}
                >
                  <option value="">자동 배정</option>
                  {liveCameras.map((c) => (
                    <option key={c.camId} value={c.camId}>{c.name}</option>
                  ))}
                </select>
              </div>
              {isFocused && focusedEvent ? (
                <div className="cctv-cell-detail">
                  <div className="frames-mini">
                    {focusedEvent.frameRefBefore && <img src={focusedEvent.frameRefBefore} alt="before" />}
                    {focusedEvent.frameRefAfter && <img src={focusedEvent.frameRefAfter} alt="after" />}
                  </div>
                  <div className="cctv-cell-foot">
                    <Badge eventType={focusedEvent.eventType} />
                    <span className="cctv-cell-cam">{camId}</span>
                  </div>
                </div>
              ) : realCam ? (
                <div className="cctv-cell-live-wrap">
                  <LiveHlsVideo videoUrl={realCam.videoUrl} className="cctv-cell-live-video" />
                  <div className="cctv-cell-foot cctv-cell-foot-live">
                    <span className="cctv-cell-live-dot" />
                    <span className="cctv-cell-cam">{realCam.name}</span>
                  </div>
                </div>
              ) : (
                <div className="cctv-cell-idle">
                  <span className="cctv-cell-cam">{camId}</span>
                  {latest ? (
                    <span className="cctv-cell-sub">
                      {EVENT_LABEL[latest.eventType] || latest.eventType} · {fmtTime(latest.occurredAt)}
                    </span>
                  ) : (
                    <span className="cctv-cell-sub">신호 대기 중</span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {zoomedCamId && (() => {
        const zoomedRealCam = realCameraById[zoomedCamId]
        return (
        <div className="cctv-zoom-overlay" onClick={() => setZoomedCamId(null)}>
          <div className="cctv-zoom-box" onClick={(e) => e.stopPropagation()}>
            <div className="cctv-zoom-head">
              <span className="cctv-zoom-cam">{zoomedRealCam ? zoomedRealCam.name : zoomedCamId}</span>
              {zoomedLatest && <Badge eventType={zoomedLatest.eventType} />}
              <button className="cctv-zoom-close" onClick={() => setZoomedCamId(null)}>닫기 ✕</button>
            </div>

            {zoomedLatest ? (
              <>
                <div className="frames-zoom">
                  <FrameImage label="이전" url={zoomedLatest.frameRefBefore} />
                  <FrameImage label="이후" url={zoomedLatest.frameRefAfter} />
                </div>
                <div className="cctv-zoom-meta">
                  {EVENT_LABEL[zoomedLatest.eventType] || zoomedLatest.eventType} · {fmtTime(zoomedLatest.occurredAt)}
                </div>
              </>
            ) : zoomedRealCam ? (
              <LiveHlsVideo videoUrl={zoomedRealCam.videoUrl} className="cctv-zoom-live-video" />
            ) : (
              <div className="cctv-zoom-empty">신호 대기 중 — 아직 감지된 이벤트가 없습니다</div>
            )}
          </div>
        </div>
        )
      })()}

      {showCameraManager && (
        <CameraManagerModal
          onClose={() => setShowCameraManager(false)}
          onChanged={loadLiveCameras}
        />
      )}
    </section>
  )
}