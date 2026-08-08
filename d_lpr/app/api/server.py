"""FastAPI 서버.

역할
  - 위반/경보 이벤트 REST 조회
  - WebSocket 실시간 푸시 (관제 화면 및 Spring Boot 게이트웨이 구독)
  - 위반 유형별 통계 API
  - 통계 대시보드 정적 파일 서빙

Spring Boot 게이트웨이(장성혁)와의 연동은 동일한 payload 규격을 쓰므로
게이트웨이가 이 서버의 /ws 를 구독하기만 하면 된다.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from ..core.bus import TOPIC_ALERT, TOPIC_VIOLATION, bus
from ..core.config import settings
from ..core.schemas import VehicleRecord, VehicleStatus
from ..lpr import plate_format as pf
from ..vehicle.repository import get_repository
from ..violation.engine import ViolationEngine
from . import stats as stats_mod

log = logging.getLogger("omeca.api")

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


# --------------------------------------------------------------------------
# WebSocket 허브
# --------------------------------------------------------------------------
class WSHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        log.info("WS 연결 (총 %d)", len(self.clients))

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def publish_threadsafe(self, topic: str, payload: dict[str, Any]) -> None:
        """이벤트 버스(동기 스레드)에서 asyncio 루프로 안전하게 넘긴다."""
        if self.loop is None or not self.clients:
            return
        msg = {"topic": topic, "data": payload}
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(msg), self.loop)
        except RuntimeError:
            pass


hub = WSHub()
engine: Optional[ViolationEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    hub.loop = asyncio.get_running_loop()
    bus.subscribe(hub.publish_threadsafe)
    engine = ViolationEngine()
    log.info("위반 감지 엔진 기동 (카메라 %d대)", len(engine.zones))
    yield
    bus.unsubscribe(hub.publish_threadsafe)


app = FastAPI(
    title="오메카3 LPR / 차량 위반 감지 API",
    description="번호판 인식, 고위험 차량 대조, 신호위반·불법유턴 감지 (담당: 박지원)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in str(settings.server.cors_origins).split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# 대시보드
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def dashboard():
    path = STATIC_DIR / "dashboard.html"
    if not path.exists():
        return JSONResponse({"detail": "dashboard.html 없음"}, status_code=404)
    return FileResponse(path)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mock_mode": settings.lpr.mock,
        "db_driver": get_repository().driver,
        "cameras": engine.zones.cam_ids() if engine else [],
    }


# --------------------------------------------------------------------------
# 위반 조회
# --------------------------------------------------------------------------
@app.get("/api/violations")
def list_violations(
    limit: int = Query(100, ge=1, le=1000),
    type: Optional[str] = Query(None, description="red_light | illegal_uturn | high_risk_vehicle"),
    cam_id: Optional[str] = None,
    risk_level: Optional[str] = Query(None, description="high | caution | normal"),
):
    rows = get_repository().recent_violations(
        limit=limit, violation_type=type, cam_id=cam_id, risk_level=risk_level
    )
    return {"count": len(rows), "items": rows}


@app.get("/api/violations/{event_id}")
def get_violation(event_id: str):
    rows = get_repository().recent_violations(limit=1000)
    for r in rows:
        if r["event_id"] == event_id:
            return r
    raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")


# --------------------------------------------------------------------------
# 통계
# --------------------------------------------------------------------------
@app.get("/api/stats")
def get_stats():
    return stats_mod.full()


@app.get("/api/stats/summary")
def get_summary():
    return stats_mod.summary()


@app.get("/api/stats/by-type")
def get_by_type():
    return stats_mod.by_type()


@app.get("/api/stats/by-hour")
def get_by_hour():
    return stats_mod.by_hour()


# --------------------------------------------------------------------------
# 차량 DB
# --------------------------------------------------------------------------
@app.get("/api/vehicles")
def list_vehicles(status: Optional[str] = None, limit: int = Query(200, ge=1, le=1000)):
    recs = get_repository().list_vehicles(status=status, limit=limit)
    return {
        "count": len(recs),
        "items": [
            {
                "plate_no": r.plate_no, "owner_name": r.owner_name, "model": r.model,
                "color": r.color, "status": r.status.value,
                "risk_level": r.risk_level.value, "memo": r.memo,
            }
            for r in recs
        ],
    }


@app.get("/api/vehicles/{plate_no}")
def lookup_vehicle(plate_no: str):
    """번호판 단건 조회. 관제요원이 화면에서 직접 조회할 때 사용."""
    repo = get_repository()
    key = pf.canonical(plate_no)
    rec = repo.find(key)
    if rec is None:
        similar = repo.find_similar(key)
        if similar is None:
            return {
                "plate_no": key, "matched": False,
                "status": VehicleStatus.UNREGISTERED.value, "risk_level": "high",
            }
        rec, diff = similar
        return _vehicle_payload(rec, matched=True, fuzzy=True, diff=diff)
    return _vehicle_payload(rec, matched=True)


def _vehicle_payload(rec: VehicleRecord, matched: bool, fuzzy: bool = False, diff: int = 0):
    return {
        "plate_no": rec.plate_no, "matched": matched, "fuzzy": fuzzy, "char_diff": diff,
        "owner_name": rec.owner_name, "model": rec.model, "color": rec.color,
        "status": rec.status.value, "risk_level": rec.risk_level.value, "memo": rec.memo,
    }


# --------------------------------------------------------------------------
# ROI 설정 조회 (관제 화면에서 라인 오버레이용)
# --------------------------------------------------------------------------
@app.get("/api/zones")
def get_zones():
    if engine is None:
        return {"cameras": []}
    out = []
    for cam_id in engine.zones.cam_ids():
        cz = engine.zones.get(cam_id)
        if cz is None:
            continue
        out.append({
            "cam_id": cz.cam_id,
            "location": list(cz.location) if cz.location else None,
            "lines": [
                {"line_id": l.line_id, "name": l.name, "p1": list(l.p1),
                 "p2": list(l.p2), "direction": l.direction}
                for l in cz.lines.values()
            ],
            "zones": [
                {"zone_id": z.zone_id, "name": z.name, "zone_type": z.zone_type,
                 "uturn_allowed": z.uturn_allowed, "polygon": [list(p) for p in z.polygon]}
                for z in cz.zones.values()
            ],
            "intersections": cz.intersections,
        })
    return {"cameras": out}


# --------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    # 접속 직후 최근 이벤트를 밀어줘 화면이 비어 보이지 않게 한다
    for payload in bus.recent(TOPIC_VIOLATION, limit=20):
        await ws.send_json({"topic": TOPIC_VIOLATION, "data": payload})
    try:
        while True:
            await ws.receive_text()   # 클라이언트 ping 유지용
    except WebSocketDisconnect:
        hub.disconnect(ws)
    except Exception:
        hub.disconnect(ws)


@app.get("/api/recent-alerts")
def recent_alerts(limit: int = Query(20, ge=1, le=100)):
    return {"items": bus.recent(TOPIC_ALERT, limit=limit)}


def main() -> None:  # pragma: no cover
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(app, host=settings.server.host, port=int(settings.server.port))


if __name__ == "__main__":  # pragma: no cover
    main()
