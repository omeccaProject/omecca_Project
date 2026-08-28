import { useCallback, useEffect, useState } from 'react'
import { EVENT_LABEL } from '../constants'
import { REAL_CAMERAS as FALLBACK_REAL_CAMERAS } from '../realCameras'
import { fetchCameras } from '../api'
import Badge from './Badge'
import FrameImage from './FrameImage'
import LiveHlsVideoWithDetections from './LiveHlsVideoWithDetections'
import CameraManagerModal from './CameraManagerModal'

// 아직 이벤트가 안 들어온 카메라도 그리드에 자리를 채워두기 위한 기본 목록.
const FALLBACK_CAMS = [
  'CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05', 'CAM-06',
  'CAM-07', 'CAM-08', 'CAM-09', 'CAM-10', 'CAM-11', 'CAM-12',
  'CAM-13', 'CAM-14', 'CAM-15', 'CAM-16', 'CAM-17', 'CAM-18',
]

const CAM_COUNT_OPTIONS = [6, 9]
const CAM_COUNT_STORAGE_KEY = 'omecca_cctv_cam_count'

// 사용자가 특정 칸에 직접 지정한 카메라 배정
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

// camOffset: 카메라 목록에서 몇 번째부터 보여줄지
// fixedCount: 지정되면 6/9 토글 UI를 숨기고 이 개수로 고정
export default function CctvGrid({
  events,
  focusedEvent,
  onSelectCam,
  camOffset = 0,
  fixedCount = null,
}) {
  // 화면에 몇 개 카메라를 보여줄지
  const [camCount, setCamCount] = useState(() => {
    if (fixedCount) return fixedCount

    const saved = Number(
      localStorage.getItem(CAM_COUNT_STORAGE_KEY)
    )

    return CAM_COUNT_OPTIONS.includes(saved) ? saved : 6
  })

  // 클릭해서 확대한 카메라 ID
  const [zoomedCamId, setZoomedCamId] = useState(null)

  // 카메라 관리 모달
  const [showCameraManager, setShowCameraManager] = useState(false)

  // 실시간 영상이 연결된 카메라 목록
  const [liveCameras, setLiveCameras] = useState(
    FALLBACK_REAL_CAMERAS
  )

  // 자동 슬롯 배정
  const [slots, setSlots] = useState([])

  // 사용자가 직접 지정한 슬롯
  const [manualSlots, setManualSlots] = useState(
    loadManualSlots
  )

  // manualSlots 저장
  useEffect(() => {
    localStorage.setItem(
      MANUAL_SLOT_STORAGE_KEY,
      JSON.stringify(manualSlots)
    )
  }, [manualSlots])

  // 다른 창과 manualSlots 동기화
  useEffect(() => {
    function onStorage(e) {
      if (e.key !== MANUAL_SLOT_STORAGE_KEY) return

      try {
        setManualSlots(
          e.newValue ? JSON.parse(e.newValue) : {}
        )
      } catch {
        setManualSlots({})
      }
    }

    window.addEventListener('storage', onStorage)

    return () =>
      window.removeEventListener('storage', onStorage)
  }, [])

  // 슬롯에 카메라 직접 지정
  function assignSlot(index, camId) {
    setManualSlots((prev) => {
      const next = { ...prev }

      if (camId) {
        Object.keys(next).forEach((key) => {
          if (
            Number(key) !== index &&
            next[key] === camId
          ) {
            delete next[key]
          }
        })

        next[index] = camId
      } else {
        delete next[index]
      }

      return next
    })
  }

  // =========================================================
  // 실제 카메라 목록 조회
  // =========================================================
  const loadLiveCameras = useCallback(() => {
    fetchCameras()
      .then((list) => {
        const withStream = (
          Array.isArray(list) ? list : []
        )
          .filter(
            (c) =>
              c.status === 'ACTIVE' &&
              c.streamUrl
          )
          .map((c) => ({
            camId: c.camId,
            name: c.name,
            videoUrl: c.streamUrl,
            streamFormat: c.streamFormat,

            // 감지 기능 설정
            debrisDetectionEnabled:
              !!c.debrisDetectionEnabled,

            uturnDetectionEnabled:
              !!c.uturnDetectionEnabled,

            signalDetectionEnabled:
              !!c.signalDetectionEnabled,

            personRiskDetectionEnabled:
              !!c.personRiskDetectionEnabled,
          }))

        setLiveCameras(
          withStream.length > 0
            ? withStream
            : FALLBACK_REAL_CAMERAS
        )

        // API가 정상 응답했을 때만 슬롯 갱신
        const liveIds = withStream.map(
          (c) => c.camId
        )

        setSlots((prev) => {
          const liveSet = new Set(liveIds)

          const alreadySlotted = new Set(
            prev.filter(
              (id) =>
                id &&
                liveSet.has(id)
            )
          )

          const newcomers = liveIds.filter(
            (id) =>
              !alreadySlotted.has(id)
          )

          if (newcomers.length === 0) {
            return prev
          }

          const next = [...prev]

          const idleSlotIndexes = []

          next.forEach((id, idx) => {
            if (
              id &&
              !liveSet.has(id)
            ) {
              idleSlotIndexes.push(idx)
            }
          })

          let idlePtr = 0

          newcomers.forEach((id) => {
            if (
              idlePtr <
              idleSlotIndexes.length
            ) {
              next[
                idleSlotIndexes[idlePtr]
              ] = id

              idlePtr += 1
            } else {
              next.push(id)
            }
          })

          return next
        })
      })
      .catch(() => {
        // API 실패 시 기존 fallback 유지
        setLiveCameras(
          FALLBACK_REAL_CAMERAS
        )
      })
  }, [])

  useEffect(() => {
    loadLiveCameras()
  }, [loadLiveCameras])

  // 카메라 개수 저장
  useEffect(() => {
    if (fixedCount) return

    localStorage.setItem(
      CAM_COUNT_STORAGE_KEY,
      String(camCount)
    )
  }, [camCount, fixedCount])

  // 다른 창에서 카메라 개수 변경 시 동기화
  useEffect(() => {
    if (fixedCount) return

    function onStorage(e) {
      if (
        e.key !==
        CAM_COUNT_STORAGE_KEY
      ) {
        return
      }

      const next = Number(e.newValue)

      if (
        CAM_COUNT_OPTIONS.includes(next)
      ) {
        setCamCount(next)
      }
    }

    window.addEventListener(
      'storage',
      onStorage
    )

    return () =>
      window.removeEventListener(
        'storage',
        onStorage
      )
  }, [fixedCount])

  // ESC로 확대 화면 닫기
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape') {
        setZoomedCamId(null)
      }
    }

    window.addEventListener(
      'keydown',
      onKeyDown
    )

    return () =>
      window.removeEventListener(
        'keydown',
        onKeyDown
      )
  }, [])

  const effectiveCount =
    fixedCount || camCount

  const seenCams = [
    ...new Set(
      events
        .map((ev) => ev.camId)
        .filter(Boolean)
    ),
  ]

  // 실제 등록된 카메라를 ID 기준으로 빠르게 찾기
  const realCameraById =
    Object.fromEntries(
      liveCameras.map((c) => [
        c.camId,
        c,
      ])
    )

  // 자동 카메라 후보 목록
  const autoCamIdPool = [
    ...new Set([
      ...slots.filter(Boolean),
      ...liveCameras.map(
        (c) => c.camId
      ),
      ...seenCams,
      ...FALLBACK_CAMS,
    ]),
  ]

  // 수동 지정된 카메라는 자동 배정에서 제외
  const pinnedCamIds = new Set(
    Object.values(
      manualSlots
    ).filter(Boolean)
  )

  const autoPool =
    autoCamIdPool.filter(
      (id) =>
        !pinnedCamIds.has(id)
    )

  const usedThisRender = new Set()

  let autoPtr = 0

  const camIds = []

  for (
    let i = camOffset;
    i <
    camOffset + effectiveCount;
    i++
  ) {
    const pinned =
      manualSlots[i]

    if (pinned) {
      camIds.push(pinned)

      usedThisRender.add(
        pinned
      )

      continue
    }

    while (
      autoPtr <
        autoPool.length &&
      usedThisRender.has(
        autoPool[autoPtr]
      )
    ) {
      autoPtr += 1
    }

    const next =
      autoPool[autoPtr]

    autoPtr += 1

    if (next) {
      usedThisRender.add(next)
    }

    camIds.push(
      next ??
        `CAM-EMPTY-${i}`
    )
  }

  // 카메라별 최신 이벤트
  const latestByCam = {}

  events.forEach((ev) => {
    const prev =
      latestByCam[ev.camId]

    if (
      !prev ||
      new Date(
        ev.occurredAt
      ) >
        new Date(
          prev.occurredAt
        )
    ) {
      latestByCam[
        ev.camId
      ] = ev
    }
  })

  function handleCellClick(camId) {
    const latest =
      latestByCam[camId]

    if (latest) {
      onSelectCam(latest)
    }

    // 이벤트 유무와 관계없이 확대
    setZoomedCamId(camId)
  }

  const zoomedLatest =
    zoomedCamId
      ? latestByCam[
          zoomedCamId
        ]
      : null

  return (
    <section className="panel cctv-panel">
      <div className="cctv-panel-head">
        <h2>
          CCTV 그리드 뷰어
          {fixedCount
            ? ` (${camOffset + 1}~${
                camOffset +
                effectiveCount
              })`
            : ''}
        </h2>

        {!fixedCount && (
          <div className="cctv-panel-head-right">
            <button
              type="button"
              className="cam-manage-btn"
              onClick={() =>
                setShowCameraManager(
                  true
                )
              }
            >
              카메라 관리
            </button>

            <div className="cam-count-toggle">
              {CAM_COUNT_OPTIONS.map(
                (n) => (
                  <button
                    key={n}
                    className={
                      camCount === n
                        ? 'active'
                        : ''
                    }
                    onClick={() =>
                      setCamCount(n)
                    }
                  >
                    {n}개
                  </button>
                )
              )}
            </div>
          </div>
        )}
      </div>

      <div
        className={`cctv-grid cctv-grid-${effectiveCount}`}
      >
        {camIds.map(
          (camId, idx) => {
            const slotIndex =
              camOffset + idx

            const latest =
              latestByCam[camId]

            const isFocused =
              focusedEvent?.camId ===
              camId

            const realCam =
              realCameraById[
                camId
              ]

            return (
              <div
                key={slotIndex}
                className={`cctv-cell ${
                  isFocused
                    ? 'active'
                    : ''
                } ${
                  latest
                    ? ''
                    : 'idle'
                } ${
                  realCam
                    ? 'cctv-cell-live'
                    : ''
                }`}
                onClick={() =>
                  handleCellClick(
                    camId
                  )
                }
              >
                <div
                  className="cctv-cell-pin"
                  onClick={(e) =>
                    e.stopPropagation()
                  }
                >
                  <select
                    className="cctv-cell-pin-select"
                    title="이 칸에 표시할 카메라를 직접 지정"
                    value={
                      manualSlots[
                        slotIndex
                      ] || ''
                    }
                    onChange={(e) =>
                      assignSlot(
                        slotIndex,
                        e.target.value ||
                          null
                      )
                    }
                  >
                    <option value="">
                      자동 배정
                    </option>

                    {liveCameras.map(
                      (c) => (
                        <option
                          key={c.camId}
                          value={c.camId}
                        >
                          {c.name}
                        </option>
                      )
                    )}
                  </select>
                </div>

                {realCam ? (
                  <div className="cctv-cell-live-wrap">
                    <LiveHlsVideoWithDetections
                      camId={
                        realCam.camId
                      }
                      videoUrl={
                        realCam.videoUrl
                      }
                      format={
                        realCam.streamFormat
                      }
                      className="cctv-cell-live-video"
                    />

                    <div className="cctv-cell-foot cctv-cell-foot-live">

                      {/* 실제 발생한 이벤트 Badge */}
                      <span className="cctv-cell-live-dot" />

                      {/* 카메라 이름 */}
                      <span className="cctv-cell-cam">
                        {realCam.name}
                      </span>

                      {/* =================================================
                          카메라 설정에서 ON 되어 있는 감지 기능 표시
                          ================================================= */}

                      {realCam.debrisDetectionEnabled && (
                        <span className="cam-tag-debris">
                          낙하물
                        </span>
                      )}

                      {realCam.uturnDetectionEnabled && (
                        <span className="cam-tag-debris">
                          불법유턴
                        </span>
                      )}

                      {realCam.signalDetectionEnabled && (
                        <span className="cam-tag-debris">
                          신호위반
                        </span>
                      )}

                      {realCam.personRiskDetectionEnabled && (
                        <span className="cam-tag-debris">
                          수배자/흉기
                        </span>
                      )}
                    </div>
                  </div>
                ) : isFocused &&
                  focusedEvent ? (
                  <div className="cctv-cell-detail">
                    <div className="frames-mini">
                      {focusedEvent.frameRefBefore && (
                        <img
                          src={
                            focusedEvent.frameRefBefore
                          }
                          alt="before"
                        />
                      )}

                      {focusedEvent.frameRefAfter && (
                        <img
                          src={
                            focusedEvent.frameRefAfter
                          }
                          alt="after"
                        />
                      )}
                    </div>

                    <div className="cctv-cell-foot">
                      <Badge
                        eventType={
                          focusedEvent.eventType
                        }
                      />

                      <span className="cctv-cell-cam">
                        {camId}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="cctv-cell-idle">
                    <span className="cctv-cell-cam">
                      {camId}
                    </span>

                    {latest ? (
                      <span className="cctv-cell-sub">
                        {EVENT_LABEL[
                          latest.eventType
                        ] ||
                          latest.eventType}{' '}
                        ·{' '}
                        {fmtTime(
                          latest.occurredAt
                        )}
                      </span>
                    ) : (
                      <span className="cctv-cell-sub">
                        신호 대기 중
                      </span>
                    )}
                  </div>
                )}
              </div>
            )
          }
        )}
      </div>

      {/* =========================================================
          CCTV 확대 화면
          ========================================================= */}
      {zoomedCamId &&
        (() => {
          const zoomedRealCam =
            realCameraById[
              zoomedCamId
            ]

          return (
            <div
              className="cctv-zoom-overlay"
              onClick={() =>
                setZoomedCamId(
                  null
                )
              }
            >
              <div
                className="cctv-zoom-box"
                onClick={(e) =>
                  e.stopPropagation()
                }
              >
                <div className="cctv-zoom-head">
                  <span className="cctv-zoom-cam">
                    {zoomedRealCam
                      ? zoomedRealCam.name
                      : zoomedCamId}
                  </span>

                

                  <button
                    className="cctv-zoom-close"
                    onClick={() =>
                      setZoomedCamId(
                        null
                      )
                    }
                  >
                    닫기 ✕
                  </button>
                </div>

                {zoomedRealCam ? (
                  <LiveHlsVideoWithDetections
                    camId={
                      zoomedRealCam.camId
                    }
                    videoUrl={
                      zoomedRealCam.videoUrl
                    }
                    format={
                      zoomedRealCam.streamFormat
                    }
                    className="cctv-zoom-live-video"
                  />
                ) : zoomedLatest ? (
                  <>
                    <div className="frames-zoom">
                      <FrameImage
                        label="이전"
                        url={
                          zoomedLatest.frameRefBefore
                        }
                      />

                      <FrameImage
                        label="이후"
                        url={
                          zoomedLatest.frameRefAfter
                        }
                      />
                    </div>

                    <div className="cctv-zoom-meta">
                      {EVENT_LABEL[
                        zoomedLatest.eventType
                      ] ||
                        zoomedLatest.eventType}
                      {' · '}
                      {fmtTime(
                        zoomedLatest.occurredAt
                      )}
                    </div>
                  </>
                ) : (
                  <div className="cctv-zoom-empty">
                    신호 대기 중 — 아직 감지된 이벤트가 없습니다
                  </div>
                )}
              </div>
            </div>
          )
        })()}

      {/* =========================================================
          카메라 관리 모달
          ========================================================= */}
      {showCameraManager && (
        <CameraManagerModal
          onClose={() =>
            setShowCameraManager(
              false
            )
          }
          onChanged={
            loadLiveCameras
          }
        />
      )}
    </section>
  )
}