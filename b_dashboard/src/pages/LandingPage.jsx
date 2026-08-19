import { useEffect, useState } from 'react'
import './LandingPage.css'

// 실시간 카메라 그리드 탭에 쓰는 목업 데이터. 실제 이벤트 API를 호출하지 않는
// 마케팅용 정적 랜딩페이지라, 영상 데모와 동일한 값을 그대로 하드코딩해서 보여준다.
const CAM_TILES = [
  { id: 'CAM-01', label: 'PERSON 0.94', alert: false, loc: '보라매역 3번', res: '1080p' },
  { id: 'CAM-02', label: 'VEHICLE 0.97', alert: false, loc: '강남대로 12', res: '4K' },
  { id: 'CAM-03', label: '이상행동 0.91', alert: true, loc: '홍대입구 8번', res: '1080p' },
  { id: 'CAM-04', label: 'PERSON 0.86', alert: false, loc: '잠실 롯데월드', res: '1080p' },
  { id: 'CAM-05', label: null, alert: false, loc: '여의도 IFC', res: '4K' },
  { id: 'CAM-06', label: 'CROWD 4.2/㎡', alert: false, loc: '광화문 광장', res: '1080p' },
  { id: 'CAM-07', label: 'VEHICLE 0.92', alert: false, loc: '강변북로 · 상수', res: '4K' },
  { id: 'CAM-08', label: null, alert: false, loc: '노원 상계동', res: '1080p' },
]

const GIS_PINS = [
  { n: 5, top: 30, left: 60 }, { n: 14, top: 20, left: 400 }, { n: 3, top: 15, left: 540 },
  { n: 26, top: 80, left: 280 }, { n: 9, top: 120, left: 40 }, { n: 4, top: 135, left: 280, hot: true },
  { n: 18, top: 105, left: 610 }, { n: 2, top: 150, left: 660 },
]

const STREAM_ROWS = [
  { t: '14:49:07', chip: 'critical', label: 'CRITICAL', desc: '이상운전 감지 — 흉기 소지 의심', loc: 'CAM-01 · 보라매' },
  { t: '14:47:22', chip: 'warn', label: 'WARN', desc: '5분 이상 배회 — 야간 시간', loc: 'CAM-14 · 강남' },
  { t: '14:44:58', chip: 'warn', label: 'WARN', desc: '도로 위 낙하물 감지', loc: 'CAM-08 · 홍대' },
  { t: '14:41:03', chip: 'info', label: 'INFO', desc: '지정 차량 매칭 — 신뢰도 96%', loc: 'CAM-22 · 잠실' },
  { t: '14:38:41', chip: 'info', label: 'INFO', desc: '번호판 인식 · 12가3456', loc: 'CAM-07 · 상수' },
]

const CATEGORY_BARS = [
  { label: '이상행동', pct: 38, color: 'var(--lp-red)' },
  { label: '차량 인식', pct: 27, color: 'var(--lp-cyan)' },
  { label: '낙하물 감지', pct: 19, color: 'var(--lp-green)' },
  { label: '기타', pct: 16, color: 'var(--lp-muted2)' },
]

const PDF_ROWS = [
  { tag: 'summary', label: 'SUMMARY', section: 'Section 1', desc: '일일 관제 요약 — 이벤트 1,284건 · 대응 완료 97.4%', ref: '전체' },
  { tag: 'trend', label: 'TREND', section: 'Section 2', desc: '낙하물 감지 - 도로 위 낙하물 24건', ref: 'CAM-08,14' },
  { tag: 'incident', label: 'INCIDENT', section: 'Section 3', desc: '중대 사건 6건 상세 · 대응 타임라인 포함', ref: 'CAM-01,03' },
]

const TABS = [
  { n: 1, label: '실시간 카메라' },
  { n: 2, label: '지도 관제' },
  { n: 3, label: 'AI 이벤트' },
  { n: 4, label: '분석 리포트' },
]

// "파일럿 신청서 작성" 모달의 관심 분야 드롭다운 / 예상 CCTV 규모 옵션.
const INQUIRY_INTERESTS = [
  '지자체 통합관제',
  '산업현장 · 스마트팩토리',
  '항만 · 공항 · 물류',
  '교통 · 도로 · 주차',
  '공공기관 · 국가시설',
  '기타 · 컨설팅 문의',
]
const INQUIRY_SCALES = ['~50', '50-500', '500-3,000', '3,000+']

const INQUIRY_INITIAL = {
  name: '', org: '', email: '', phone: '',
  interest: INQUIRY_INTERESTS[0], scale: INQUIRY_SCALES[1],
  message: '', agree: false,
}

// "파일럿 신청서 작성 →" 버튼을 누르면 뜨는 도입 문의 모달.
// 색상은 랜딩페이지 자체의 다크 톤이 아니라 로그인/회원가입(AuthPages.css) 팔레트를
// 그대로 반영해달라는 요청이라, lp-* 다크 변수 대신 auth 쪽 색상 값을 직접 써서
// (흰 카드 + #3b5bdb 블루 accent) 이 모달 안에서만 별도로 스타일링한다.
function PilotInquiryModal({ onClose }) {
  const [form, setForm] = useState(INQUIRY_INITIAL)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  const setField = (key) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [key]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.org.trim() || !form.email.trim()) {
      setError('이름/담당자, 소속 기관·회사, 이메일은 필수 입력 항목입니다.')
      return
    }
    if (!form.agree) {
      setError('개인정보 수집·이용에 동의해주세요.')
      return
    }
    setError('')
    // 아직 별도 백엔드 접수 API가 없는 마케팅 폼이라, 우선 접수 완료 화면만 보여준다.
    // (실제 접수 처리를 붙이려면 b_gateway에 /api/inquiries 같은 엔드포인트가 필요함
    //  — 설계는 B_9_파일럿신청서_접수API_설계.md에 정리해둠, 필요해지면 그대로 구현)
    setSubmitted(true)
  }

  return (
    <div className="pi-overlay" onClick={onClose}>
      <div className="pi-modal" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="pi-close" onClick={onClose} aria-label="닫기">✕</button>

        <div className="pi-left">
          <span className="pi-eyebrow">— 도입 문의</span>
          <h3 className="pi-heading">관제의 다음 세대를,<br /><span className="pi-accent">함께 설계</span>합니다.</h3>
          <p className="pi-desc">
            지자체·공공기관·산업현장 어디든, 규모와 목적을 알려주시면 도메인 전담
            컨설턴트가 1영업일 안에 회신드립니다. 파일럿 관제는 30일간 무료로 운영해 볼 수 있습니다.
          </p>
          <div className="pi-contact">
            <div className="pi-contact-row">
              <span className="pi-contact-icon">✉</span>
              <div><div className="pi-contact-label">EMAIL</div><div className="pi-contact-value">sales@omecca.co.kr</div></div>
            </div>
            <div className="pi-contact-row">
              <span className="pi-contact-icon">☎</span>
              <div><div className="pi-contact-label">PHONE</div><div className="pi-contact-value">02-6952-0413 (평일 09-18시)</div></div>
            </div>
            <div className="pi-contact-row">
              <span className="pi-contact-icon">📍</span>
              <div><div className="pi-contact-label">OFFICE</div><div className="pi-contact-value">서울특별시 강남구 테헤란로 421, 20층</div></div>
            </div>
          </div>
        </div>

        <div className="pi-right">
          {submitted ? (
            <div className="pi-done">
              <div className="pi-done-icon">✓</div>
              <h4>문의가 접수되었습니다.</h4>
              <p>담당 컨설턴트가 1영업일 안에 {form.email}로 회신드립니다.</p>
              <button type="button" className="pi-submit" onClick={onClose}>닫기</button>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="pi-grid2">
                <label className="pi-field">
                  <span>이름 / 담당자 <em>*</em></span>
                  <input value={form.name} onChange={setField('name')} autoFocus />
                </label>
                <label className="pi-field">
                  <span>소속 기관 · 회사 <em>*</em></span>
                  <input value={form.org} onChange={setField('org')} />
                </label>
              </div>
              <div className="pi-grid2">
                <label className="pi-field">
                  <span>이메일 <em>*</em></span>
                  <input type="email" value={form.email} onChange={setField('email')} />
                </label>
                <label className="pi-field">
                  <span>연락처</span>
                  <input value={form.phone} onChange={setField('phone')} placeholder="선택" />
                </label>
              </div>

              <label className="pi-field">
                <span>관심 분야</span>
                <select value={form.interest} onChange={setField('interest')}>
                  {INQUIRY_INTERESTS.map((it) => <option key={it} value={it}>{it}</option>)}
                </select>
              </label>

              <div className="pi-field">
                <span>예상 CCTV 규모</span>
                <div className="pi-scale-group">
                  {INQUIRY_SCALES.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className={`pi-scale-btn ${form.scale === s ? 'on' : ''}`}
                      onClick={() => setForm((f) => ({ ...f, scale: s }))}
                    >
                      <span className="pi-scale-dot" />{s}
                    </button>
                  ))}
                </div>
              </div>

              <label className="pi-field">
                <span>문의 내용 (선택, 500자 이내)</span>
                <textarea
                  rows={4}
                  maxLength={500}
                  value={form.message}
                  onChange={setField('message')}
                  placeholder="관제 대상, 도입 시기, 궁금하신 부분을 편하게 적어주세요."
                />
              </label>

              {error && <div className="pi-error">{error}</div>}

              <label className="pi-agree">
                <input type="checkbox" checked={form.agree} onChange={setField('agree')} />
                <span>개인정보 수집·이용에 동의합니다. 문의 응대 목적 외로 사용되지 않으며 1년 후 파기됩니다.</span>
              </label>

              <button type="submit" className="pi-submit">도입 상담 신청하기 →</button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

// 히어로 하단 도시 스카이라인 실루엣. 참고 디자인의 "산맥 실루엣"을 CCTV/야간 관제
// 톤에 맞춰 도시 야경으로 재해석한 것 - 건물 배열은 매 렌더마다 흔들리지 않도록
// 고정된 좌표 배열로 정의한다(Math.random 사용 안 함).
const SKYLINE_BUILDINGS = [
  { x: 0, w: 46, h: 70 }, { x: 48, w: 30, h: 108 }, { x: 80, w: 54, h: 56 },
  { x: 136, w: 26, h: 130 }, { x: 164, w: 40, h: 84 }, { x: 206, w: 60, h: 60 },
  { x: 268, w: 32, h: 150 }, { x: 302, w: 44, h: 96 }, { x: 348, w: 28, h: 118 },
  { x: 378, w: 58, h: 70 }, { x: 438, w: 34, h: 140 }, { x: 474, w: 46, h: 88 },
  { x: 522, w: 60, h: 64 }, { x: 584, w: 30, h: 160 }, { x: 616, w: 40, h: 100 },
  { x: 658, w: 26, h: 122 }, { x: 686, w: 56, h: 74 }, { x: 744, w: 32, h: 144 },
  { x: 778, w: 46, h: 92 }, { x: 826, w: 60, h: 58 }, { x: 888, w: 30, h: 128 },
  { x: 920, w: 42, h: 82 }, { x: 964, w: 28, h: 152 }, { x: 994, w: 56, h: 68 },
  { x: 1052, w: 34, h: 110 }, { x: 1088, w: 44, h: 80 }, { x: 1134, w: 66, h: 62 },
]
const SKYLINE_WINDOWS = [
  [12, 30], [20, 55], [58, 40], [58, 60], [92, 30], [148, 20], [148, 60], [148, 100],
  [180, 40], [220, 20], [220, 40], [286, 40], [286, 90], [320, 30], [320, 65],
  [392, 30], [392, 50], [452, 30], [452, 70], [452, 110], [494, 40], [538, 20],
  [598, 50], [598, 100], [634, 40], [634, 70], [700, 30], [762, 40], [762, 90],
  [796, 20], [796, 50], [844, 20], [904, 40], [904, 90], [938, 30], [982, 40],
  [982, 90], [982, 130], [1012, 20], [1068, 30], [1068, 70], [1106, 20], [1150, 20],
]

function CitySkyline() {
  return (
    <svg className="lp-skyline" viewBox="0 0 1200 160" preserveAspectRatio="none" aria-hidden="true">
      {SKYLINE_BUILDINGS.map((b, i) => (
        <rect key={i} className="lp-skyline-b" x={b.x} y={160 - b.h} width={b.w} height={b.h} />
      ))}
      {SKYLINE_WINDOWS.map(([x, dy], i) => (
        <rect key={i} className="lp-skyline-w" x={x} y={160 - dy} width={3} height={5} />
      ))}
    </svg>
  )
}

const STAR_DOTS = [
  [60, 30], [140, 60], [260, 20], [340, 80], [420, 40], [520, 15], [600, 55],
  [700, 25], [780, 70], [860, 35], [940, 10], [1020, 60], [1100, 30], [180, 100],
  [460, 100], [760, 100], [980, 90],
]

// 로그인 안 한 사용자가 처음 접속했을 때 보는 랜딩페이지.
// 2026-08-16 영상 레퍼런스(Vigilo 스타일 다크 UI) 디자인을 그대로 코드로 옮긴 버전.
// 상태(state)는 "Core Features" 탭 전환용 하나뿐이고, 실제 로그인/회원가입 화면으로
// 안내하는 게 유일한 목적이라 API 호출은 없다.
export default function LandingPage({ navigate }) {
  const [tab, setTab] = useState(1)
  const [inquiryOpen, setInquiryOpen] = useState(false)

  // 4초마다 다음 탭으로 자동 전환 (영상 데모와 동일). 사용자가 직접 탭을 클릭해도
  // 그 시점부터 다시 4초 타이머가 새로 시작되도록 tab을 의존성에 둔다.
  useEffect(() => {
    const timer = setInterval(() => {
      setTab((t) => (t >= 4 ? 1 : t + 1))
    }, 4000)
    return () => clearInterval(timer)
  }, [tab])

  return (
    <div className="lp-root">
      <nav className="lp-nav">
        <div className="lp-brand"><span className="lp-dot">V</span> Vigilog</div>
        <div className="lp-navlinks">
          <a href="#lp-features">기능</a>
          <a href="#lp-platform">플랫폼</a>
          <a href="#lp-pricing">요금제</a>
        </div>
        <div className="lp-navright">
          <button type="button" className="lp-btn-ghost" onClick={() => navigate('/login')}>로그인</button>
          <button type="button" className="lp-btn-white" onClick={() => navigate('/signup')}>데모 요청</button>
        </div>
      </nav>

      <section className="lp-hero">
        <div className="lp-hero-bg" aria-hidden="true">
          <svg className="lp-stars" viewBox="0 0 1200 160" preserveAspectRatio="none">
            {STAR_DOTS.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 1.6 : 1} />)}
          </svg>
          <CitySkyline />
        </div>

        <span className="lp-badge-pill"><span className="lp-dot-sm" />2026년 실시간 관제 인프라 · Beta</span>
        <h1 className="lp-hero-title">모든 카메라를<br /><span className="lp-dim">하나의 눈</span>으로.</h1>
        <p className="lp-hero-sub">
          Vigilog는 흩어진 CCTV·IoT 센서·차량 신호를 하나의 관제화면에 통합합니다.
          AI가 24시간 이상 징후를 감지하고, 요원에게 필요한 순간에만 알립니다.
        </p>
        <div className="lp-hero-ctas">
          <button type="button" className="lp-btn-white" onClick={() => navigate('/signup')}>무료로 관제센터 열기 →</button>
          <button type="button" className="lp-btn-dark">▶ 2분 데모 영상</button>
        </div>

        <div className="lp-console-tilt">
        <div className="lp-console">
          <div className="lp-console-bar">
            <div className="lp-dots"><span /><span /><span /></div>
            <span className="lp-console-meta"><b>● LIVE</b> / Vigilog · 2026-08-16 14:49:07 KST</span>
          </div>
          <div className="lp-console-body">
            <div>
              <div className="lp-side-label">OVERVIEW</div>
              <div className="lp-side-row active">대시보드 <b>1</b></div>
              <div className="lp-side-row">지도 <b>303</b></div>
              <div className="lp-side-row">카메라 <b>303</b></div>
              <div className="lp-side-row">이벤트 <b>30</b></div>
              <div className="lp-side-label" style={{ marginTop: 18 }}>ALERTS</div>
              <div className="lp-side-row lp-alert">고위험 <b>1</b></div>
              <div className="lp-side-row">추적 차량 <b>1</b></div>
              <div className="lp-side-row">관심 대상 <b>0</b></div>
            </div>
            <div style={{ padding: 18 }}>
              <div className="lp-map-area">
                <div className="lp-pin" style={{ top: 20, left: 150 }}>9</div>
                <div className="lp-pin" style={{ top: 60, left: 70 }}>5</div>
                <div className="lp-pin" style={{ top: 50, left: 230 }}>14</div>
                <div className="lp-pin" style={{ top: 120, left: 110 }}>26</div>
                <div className="lp-pin" style={{ top: 130, left: 190 }}>16</div>
                <div className="lp-pin" style={{ top: 105, left: 270 }}>18</div>
                <div className="lp-pin lp-hot" style={{ top: 175, left: 150 }}>4</div>
                <div className="lp-pin" style={{ top: 180, left: 60 }}>2</div>
                <div className="lp-pin" style={{ top: 210, left: 230 }}>3</div>
                <div className="lp-pin" style={{ top: 195, left: 190 }}>7</div>
              </div>
            </div>
            <div>
              <div className="lp-evt-title">AI 관제 이벤트</div>
              <div className="lp-evt lp-evt-first">
                <div className="lp-evt-title-row">이상운전 감지 <span className="lp-chip">흉기</span></div>
                <div className="lp-evt-top"><span>CAM-01</span><span>14:49:07</span></div>
                <div className="lp-evt-sub">차량: 12가3456 · 보라매역</div>
              </div>
              <div className="lp-evt">
                <div className="lp-evt-title-row">배회 5분 이상</div>
                <div className="lp-evt-top"><span>CAM-14</span><span>14:47:22</span></div>
                <div className="lp-evt-sub">위치: 강남대로 · 신뢰도 82%</div>
              </div>
              <div className="lp-evt">
                <div className="lp-evt-title-row">인원 밀집 임계값</div>
                <div className="lp-evt-top"><span>CAM-08</span><span>14:44:58</span></div>
                <div className="lp-evt-sub">밀도: 4.2/㎡ · 홍대입구</div>
              </div>
              <div className="lp-evt">
                <div className="lp-evt-title-row">지정 차량 매칭</div>
                <div className="lp-evt-top"><span>CAM-22</span><span>14:41:03</span></div>
                <div className="lp-evt-sub">신뢰도 96% · 잠실</div>
              </div>
            </div>
          </div>
        </div>
        </div>
      </section>

      <section className="lp-partners">
        <span>□ 서울교통공사</span><span>⊕ 경기도 관제센터</span><span>⌒ 부산 스마트시티</span>
        <span>◈ 대전광역시</span><span>≡ K-Rail 관제</span>
      </section>

      <section id="lp-features" className="lp-section">
        <div className="lp-wrap">
          <div className="lp-head-split">
            <div>
              <span className="lp-eyebrow">Core Features</span>
              <h2 className="lp-title">하나의 화면에서<br />모든 상황을 지휘합니다.</h2>
            </div>
            <p className="lp-lead">지도, 실시간 영상, AI 감지, 이벤트 로그. 흩어진 관제 도구를 한 곳에 모아 요원의 시선이 화면을 벗어나지 않도록 설계했습니다.</p>
          </div>

          <div className="lp-tabbar">
            {TABS.map((t) => (
              <button
                key={t.n}
                type="button"
                className={`lp-tab ${tab === t.n ? 'on' : ''}`}
                onClick={() => setTab(t.n)}
              >
                <span className="lp-tab-n">0{t.n}</span>{t.label}
              </button>
            ))}
          </div>

          {tab === 1 && (
            <div className="lp-tabpanel">
              <div className="lp-cam-grid">
                {CAM_TILES.map((cam) => (
                  <div key={cam.id} className="lp-cam">
                    <div className={`lp-cam-shot ${cam.alert ? 'alert' : ''}`}>
                      {cam.label && <span className={`lp-cam-lbl ${cam.alert ? 'alert' : ''}`}>{cam.label}</span>}
                      {cam.label && <div className={`lp-cam-box ${cam.alert ? 'alert' : ''}`} />}
                    </div>
                    <div className="lp-cam-foot">
                      <span className="lp-cam-id">{cam.id}</span>
                      <span className={`lp-cam-live ${cam.alert ? 'alert' : ''}`}>{cam.alert ? '● ALERT' : '● LIVE'}</span>
                    </div>
                    <div className="lp-cam-loc"><span>{cam.loc}</span><span>{cam.res}</span></div>
                  </div>
                ))}
              </div>
              <p className="lp-tab-caption">303대 카메라를 실시간으로 감시 — 우선순위 이벤트가 자동으로 최상단에 배치됩니다.</p>
            </div>
          )}

          {tab === 2 && (
            <div className="lp-tabpanel">
              <div className="lp-gis-panel">
                <div className="lp-gis-map">
                  {GIS_PINS.map((p) => (
                    <div key={p.n} className={`lp-pin lp-gis-pin ${p.hot ? 'lp-hot' : ''}`} style={{ top: p.top, left: p.left }}>{p.n}</div>
                  ))}
                </div>
              </div>
              <p className="lp-tab-caption">GIS 지도 위에 카메라와 이벤트가 실시간 클러스터링됩니다 — 이상 발생 시 관련 시야가 자동 확장됩니다.</p>
            </div>
          )}

          {tab === 3 && (
            <div className="lp-tabpanel">
              <div className="lp-metric-row">
                <div className="lp-metric-card">
                  <div className="lp-metric-l">오늘 감지 이벤트</div>
                  <div className="lp-metric-v">1,284</div>
                  <div className="lp-metric-d up">▲ 12.4% vs 어제</div>
                </div>
                <div className="lp-metric-card">
                  <div className="lp-metric-l">평균 대응 시간</div>
                  <div className="lp-metric-v">42s</div>
                  <div className="lp-metric-d down">▼ 8.2s 개선</div>
                </div>
              </div>
              <div className="lp-stream-panel">
                <div className="lp-stream-head"><span>실시간 이벤트 스트림</span><span className="lp-live">● 30개 대기</span></div>
                {STREAM_ROWS.map((r, i) => (
                  <div key={i} className="lp-stream-row">
                    <span className="lp-stream-t">{r.t}</span>
                    <span className={`lp-chip2 ${r.chip}`}>{r.label}</span>
                    <span className="lp-stream-desc">{r.desc}</span>
                    <span className="lp-stream-loc">{r.loc}</span>
                  </div>
                ))}
              </div>
              <p className="lp-tab-caption">AI가 흉기·이상행동·배회·군집을 실시간 분류 — 요원은 우선순위 이벤트만 확인하면 됩니다.</p>
            </div>
          )}

          {tab === 4 && (
            <div className="lp-tabpanel">
              <div className="lp-rep-row">
                <div className="lp-rep-panel">
                  <div className="lp-rep-h">주요 위험 지역 히트맵</div>
                  <div className="lp-heatmap">
                    <div className="lp-blob" style={{ width: 110, height: 110, top: 20, left: 10, background: 'var(--lp-red)' }} />
                    <div className="lp-blob" style={{ width: 90, height: 90, top: 5, left: 130, background: 'var(--lp-amber)' }} />
                    <div className="lp-blob" style={{ width: 70, height: 70, top: 60, left: 110, background: 'var(--lp-green)' }} />
                    <div className="lp-blob" style={{ width: 100, height: 100, top: 15, left: 230, background: 'var(--lp-cyan)' }} />
                  </div>
                </div>
                <div className="lp-rep-panel">
                  <div className="lp-rep-h">이벤트 카테고리 분포</div>
                  {CATEGORY_BARS.map((b) => (
                    <div key={b.label} className="lp-bar-row">
                      <div className="lp-bar-lab"><span>{b.label}</span><span>{b.pct}%</span></div>
                      <div className="lp-bar-track"><div className="lp-bar-fill" style={{ width: `${b.pct}%`, background: b.color }} /></div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="lp-pdf-table">
                <div className="lp-pdf-head"><span>PDF 리포트 · 2026-08-16 자동 생성</span><span>v3.2</span></div>
                {PDF_ROWS.map((r) => (
                  <div key={r.section} className="lp-pdf-row">
                    <span className={`lp-tag2 ${r.tag}`}>{r.label}</span>
                    <span>{r.section}</span>
                    <span className="lp-pdf-desc">{r.desc}</span>
                    <span className="lp-pdf-ref">{r.ref}</span>
                  </div>
                ))}
              </div>
              <p className="lp-tab-caption">일일·주간·월간 리포트가 자동 생성됩니다 — 감사와 브리핑 문서를 별도 작성할 필요가 없습니다.</p>
            </div>
          )}

          <div className="lp-statbar">
            <div><b>303대</b><span>동시 감시 카메라</span></div>
            <div><b>42ms</b><span>평균 감지 지연</span></div>
            <div><b>97.4%</b><span>대응 완료율</span></div>
            <div><b>24/7</b><span>무인 자동 감시</span></div>
          </div>
        </div>
      </section>

      <section id="lp-platform" className="lp-section lp-bordered">
        <div className="lp-wrap">
          <div className="lp-head-split">
            <div>
              <span className="lp-eyebrow">Platform</span>
              <h2 className="lp-title">한 번 세팅하면,<br />필요한 순간에만 알립니다.</h2>
            </div>
            <p className="lp-lead">이벤트 규칙, AI 임계값, 요원 배정을 한번 지정하면 시스템이 스스로 판단합니다. 관제 요원은 진짜 결정이 필요한 순간에만 개입하면 됩니다.</p>
          </div>
          <div className="lp-cards3">
            <div className="lp-pcard">
              <div className="lp-pcard-thumb">
                <span className="lp-pcard-lbl" style={{ top: 14, left: 16, background: 'var(--lp-green)', color: '#06210f' }}>PERSON 0.94</span>
                <div className="lp-pcard-box" style={{ top: 32, left: 16, width: 36, height: 66 }} />
                <span className="lp-pcard-lbl" style={{ top: 14, left: 130, background: 'var(--lp-red)', color: '#2a0505' }}>흉기 0.87</span>
                <div className="lp-pcard-box r" style={{ top: 32, left: 130, width: 50, height: 66 }} />
              </div>
              <div className="lp-pcard-body">
                <h4>AI 객체·행동 감지</h4>
                <p>사람·차량·소지품을 프레임 단위로 분류하고, 흉기·폭행·배회 같은 위험 행동을 즉시 태그합니다.</p>
                <div className="lp-tags"><span>YOLOv10</span><span>Pose Estimation</span><span>Action Rec.</span></div>
              </div>
            </div>
            <div className="lp-pcard">
              <div className="lp-pcard-thumb">
                <div className="lp-blob" style={{ width: 80, height: 80, top: 10, left: 20, background: 'var(--lp-red)' }} />
                <div className="lp-blob" style={{ width: 60, height: 60, top: 0, left: 100, background: 'var(--lp-amber)' }} />
                <div className="lp-blob" style={{ width: 60, height: 60, top: 30, left: 180, background: 'var(--lp-cyan)' }} />
              </div>
              <div className="lp-pcard-body">
                <h4>도로 위 낙하물 감지</h4>
                <p>도로 위에 떨어진 물체를 실시간으로 감지하고 알림을 제공합니다.</p>
                <div className="lp-tags"><span>Crowd Density</span><span>Trajectory</span><span>Time-series</span></div>
              </div>
            </div>
            <div className="lp-pcard">
              <div className="lp-pcard-thumb">
                <svg viewBox="0 0 300 110" preserveAspectRatio="none">
                  <polyline points="0,60 40,60 55,20 70,95 85,60 300,60" fill="none" style={{ stroke: 'var(--lp-cyan)' }} strokeWidth="2" />
                </svg>
              </div>
              <div className="lp-pcard-body">
                <h4>이상 차량·번호판 추적</h4>
                <p>지정한 차량이 관할 구역 어느 카메라에 잡히든 자동 알림 — 이동 경로가 지도 위에 실시간으로 이어집니다.</p>
                <div className="lp-tags"><span>ANPR</span><span>Re-ID</span><span>Multi-cam Track</span></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="lp-pricing" className="lp-section lp-bordered lp-pricing-hero">
        <div className="lp-wrap">
          <span className="lp-eyebrow center">Pricing</span>
          <h2 className="lp-title center">지자체·공공기관은<br /><span className="lp-dim">1년간 무료입니다.</span></h2>
          <p className="lp-lead center">파일럿 도입 신청서를 접수한 기관에 한해, 카메라 최대 500대·요원 계정 10석까지 무료로 제공합니다. 신용카드는 필요 없습니다.</p>
          <div className="lp-hero-ctas center">
            <button type="button" className="lp-btn-white" onClick={() => setInquiryOpen(true)}>파일럿 신청서 작성 →</button>
            <a className="lp-btn-dark" href="mailto:sales@omecca.co.kr">영업팀과 상담</a>
          </div>
        </div>
      </section>

      {inquiryOpen && <PilotInquiryModal onClose={() => setInquiryOpen(false)} />}

      <footer className="lp-footer">
        <div className="lp-wrap">
          <div className="lp-foot-grid">
            <div className="lp-foot-brand">
              <div className="lp-brand"><span className="lp-dot">V</span> Vigilog</div>
              <p>통합 관제의 새로운 기준. 서울시 강남구 테헤란로 421, 20층.</p>
            </div>
            <div className="lp-foot-col">
              <div className="lp-foot-col-title">PRODUCT</div>
              <a href="#lp-features">실시간 관제</a><a href="#lp-features">AI 감지 엔진</a><a href="#lp-features">지도 대시보드</a><a href="#">API · SDK</a>
            </div>
            <div className="lp-foot-col">
              <div className="lp-foot-col-title">SOLUTIONS</div>
              <a href="#">지자체 관제</a><a href="#">교통 · 물류</a><a href="#">스마트시티</a><a href="#">캠퍼스 보안</a>
            </div>
            <div className="lp-foot-col">
              <div className="lp-foot-col-title">COMPANY</div>
              <a href="#">소개</a><a href="#">보안 백서</a><a href="#">채용</a><a href="#">보도자료</a>
            </div>
            <div className="lp-foot-col">
              <div className="lp-foot-col-title">SUPPORT</div>
              <a href="#">문서</a><a href="#">상태</a><a href="mailto:sales@omecca.co.kr">sales@omecca.co.kr</a><a href="tel:0269520413">02-6952-0413</a>
            </div>
          </div>
          <div className="lp-foot-bottom">
            <span>© 2026 Vigilog · 대한민국 서울</span>
            <span>v0.9.4 - build 2026.08.16 · <span className="lp-status">● all systems operational</span></span>
          </div>
        </div>
      </footer>
    </div>
  )
}
