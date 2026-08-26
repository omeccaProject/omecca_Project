"""카메라 등록 ↔ 낙하물 감지 자동 연결 워처.

b_gateway에서 카메라를 등록/활성화하고 "낙하물 감지 사용"을 켜면, 사람이 따로
yolo_infer.py를 켜지 않아도 이 스크립트가 대신 켜고 꺼준다.

    GET /api/cameras 주기 폴링
        → status=ACTIVE, debrisDetectionEnabled=true, streamUrl 있음 인 카메라마다
          yolo_infer.py --video <streamUrl> --cam-id <camId> --no-display 프로세스 유지
        → 조건이 깨지면(비활성화/삭제/URL 제거) 그 프로세스는 종료
        → 업로드 동영상처럼 끝까지 재생돼 프로세스가 스스로 끝나면 다음 폴링에서
          자동으로 다시 켜짐(반복재생 효과) - 단, 그 카메라가 낙하물 이벤트를 이미
          한 번 냈으면 재시작하지 않는다(카메라당 한 번으로 충분, 같은 물체로 계속
          새 이벤트가 쌓이는 것을 방지)

yolo_infer.py 자체 탐지 로직은 전혀 건드리지 않는다 - 이 스크립트는 그걸 "누가,
언제 켜고 끌지"만 관리한다.

불법유턴/신호위반(run_uturn.py, 박지원(D) 모듈)도 낙하물과 완전히 동일한 방식으로
자동 연결한다 - 카메라별 violationDetectionEnabled + config_zones.json에 ROI(중앙선/
정지선 등)가 등록돼 있는지를 보고 별도의 프로세스 풀로 켜고 끈다.

또한 1시간마다 b_dashboard/public/captures/(사건 전/후 캡처 이미지)를 훑어서
--capture-retention-days(기본 30일)보다 오래된 파일을 자동으로 지운다 - 이벤트가
날 때마다 사진이 계속 쌓이기만 해서 디스크 용량이 끝없이 늘어나는 걸 막기 위함.

사용법:
    python a_core/camera_watcher.py                  # 기본 10초 간격, 최대 5개 동시 실행
    python a_core/camera_watcher.py --interval 5 --max-concurrent 3
    python a_core/camera_watcher.py --capture-retention-days 7   # 캡처 이미지 7일만 보관
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Windows 콘솔 기본 코드페이지(cp949)는 이모지(🟢/🔴 등)를 못 그려서 UnicodeEncodeError로
# 워처 전체가 죽는다. stdout/stderr를 UTF-8로 강제 전환해서 어떤 터미널/파이프에서
# 실행하든 안전하게 출력되게 한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent  # a_core/
PROJECT_ROOT = BASE_DIR.parent               # omecca_Project/
YOLO_INFER_PATH = BASE_DIR / "yolo_infer.py"

# 불법유턴/신호위반(⑦) — 박지원(D) 모듈
D_LPR_DIR = PROJECT_ROOT / "d_lpr"
RUN_UTURN_PATH = D_LPR_DIR / "run_uturn.py"
ZONES_PATH = D_LPR_DIR / "config_zones.json"
SIGNAL_TIMELINE_PATH = D_LPR_DIR / "signal_timeline.json"

def resolve_demo_moving_roi(cam_id):
    """카메라별 1인칭 게임 신호위반 데모용 이동 ROI 설정 파일을 찾는다.
    d_lpr/demo_moving_roi_<cam_id>.json 이 있으면 그 경로를, 없으면 None을 돌려준다.
    (일반 CCTV 카메라는 이 파일이 없으므로 그냥 무시되고 기존 동작 그대로 간다.)"""
    path = D_LPR_DIR / f"demo_moving_roi_{cam_id}.json"
    return path if path.exists() else None

# yolo_infer.py의 CAPTURES_DIR과 반드시 같은 경로여야 한다(사건 전/후 캡처 이미지 저장 위치).
CAPTURES_DIR = PROJECT_ROOT / "b_dashboard" / "public" / "captures"

GATEWAY_ORIGIN = os.environ.get("GATEWAY_URL", "http://localhost:8080").rstrip("/")
GATEWAY_URL = GATEWAY_ORIGIN + "/api/cameras"
EVENTS_URL = GATEWAY_ORIGIN + "/api/events"
API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")

CLEANUP_INTERVAL_SEC = 3600
RETRY_BACKOFF_SEC = 20  # 비정상 종료 시 재시도 대기 시간


def fetch_cameras():
    """카메라 목록 조회. 게이트웨이가 아직 안 떠 있거나 잠깐 끊겨도 워처는 죽지 않고
    다음 폴링에서 다시 시도한다(yolo_infer.py의 send_to_gateway와 동일한 방어 방식)."""
    try:
        resp = requests.get(GATEWAY_URL, headers={"X-API-Key": API_KEY}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"[WATCHER] 카메라 목록 조회 실패(게이트웨이 연결 안 됨): {e}")
        return None


def resolve_stream_url(stream_url):
    """CameraService.uploadVideo가 돌려주는 streamUrl(예: "/media/videos/xxx.mp4")은
    브라우저가 프록시를 거쳐 여는 상대경로라서, cv2.VideoCapture에 그대로 넘기면 파일도
    URL도 아닌 문자열이라 "영상을 열 수 없습니다"로 즉시 실패한다. GATEWAY_URL을 붙여서
    실제로 열 수 있는 완전한 주소로 바꾼다. 이미 http(s):// 로 시작하는 실시간 스트림
    URL이나 로컬 절대경로(C:\\...)는 그대로 둔다."""
    if stream_url.startswith("/"):
        return GATEWAY_ORIGIN + stream_url
    return stream_url


def has_fired_debris(cam_id):
    """이 카메라가 이미 낙하물(DEBRIS) 이벤트를 한 번이라도 낸 적 있는지 게이트웨이에 물어본다."""
    try:
        resp = requests.get(
            EVENTS_URL,
            params={"camId": cam_id, "eventType": "DEBRIS", "size": 1},
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("totalElements", 0) > 0
    except requests.exceptions.RequestException:
        return False


def has_fired_uturn(cam_id):
    """이 카메라가 이미 불법유턴(UTURN_VIOLATION) 이벤트를 한 번이라도 낸 적 있는지 게이트웨이에 물어본다."""
    try:
        resp = requests.get(
            EVENTS_URL,
            params={"camId": cam_id, "eventType": "UTURN_VIOLATION", "size": 1},
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("totalElements", 0) > 0
    except requests.exceptions.RequestException:
        return False


def has_fired_signal(cam_id):
    """이 카메라가 이미 신호위반(SIGNAL_VIOLATION) 이벤트를 한 번이라도 낸 적 있는지 게이트웨이에 물어본다."""
    try:
        resp = requests.get(
            EVENTS_URL,
            params={"camId": cam_id, "eventType": "SIGNAL_VIOLATION", "size": 1},
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("totalElements", 0) > 0
    except requests.exceptions.RequestException:
        return False


def zone_info():
    """config_zones.json을 읽어 유턴 ROI(중앙선) 및 신호위반 ROI(교차로/정지선) 지원 cam_id 분류."""
    uturn_cams = set()
    signal_cams = set()
    try:
        data = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
        for cam in data.get("cameras", []):
            cid = cam.get("cam_id")
            if not cid:
                continue
            lines = cam.get("lines", [])
            has_center = any(l.get("line_type") == "center" for l in lines)
            if has_center:
                uturn_cams.add(cid)
            has_intersection = len(cam.get("intersections", [])) > 0
            if has_intersection:
                signal_cams.add(cid)
    except (OSError, json.JSONDecodeError):
        pass
    return uturn_cams, signal_cams


def cleanup_old_captures(retention_days):
    """CAPTURES_DIR 안의 오래된 캡처 이미지를 삭제한다."""
    if retention_days <= 0 or not CAPTURES_DIR.exists():
        return

    cutoff = time.time() - (retention_days * 86400)
    deleted_count = 0
    freed_bytes = 0
    for path in CAPTURES_DIR.glob("*.jpg"):
        try:
            stat = path.stat()
            if stat.st_mtime < cutoff:
                freed_bytes += stat.st_size
                path.unlink()
                deleted_count += 1
        except OSError as e:
            print(f"[WATCHER] ⚠ 캡처 이미지 정리 중 오류({path.name}): {e}")

    if deleted_count > 0:
        freed_mb = freed_bytes / (1024 * 1024)
        print(f"[WATCHER] 🧹 오래된 캡처 이미지 정리: {deleted_count}개 삭제 ({freed_mb:.1f}MB 확보, "
              f"{retention_days}일 이상 지난 파일 기준)")


def qualifying_debris_cameras(cameras):
    """자동 낙하물 감지 대상: 운영 중 + 낙하물 감지 사용 + 실제 영상 URL이 있는 카메라."""
    result = {}
    for cam in cameras:
        if cam.get("status") != "ACTIVE":
            continue
        if not cam.get("debrisDetectionEnabled"):
            continue
        stream_url = cam.get("streamUrl")
        if not stream_url:
            continue
        result[cam["camId"]] = resolve_stream_url(stream_url)
    return result


def qualifying_uturn_cameras(cameras):
    """자동 불법유턴 감지 대상: 운영 중 + 불법유턴 감지 사용 + 실제 영상 URL + 중앙선 ROI가 있는 카메라."""
    uturn_cams, _ = zone_info()
    result = {}
    for cam in cameras:
        if cam.get("status") != "ACTIVE":
            continue
        enabled = cam.get("uturnDetectionEnabled")
        if enabled is None:
            enabled = cam.get("violationDetectionEnabled")
        if not enabled:
            continue
        stream_url = cam.get("streamUrl")
        if not stream_url:
            continue
        cam_id = cam["camId"]
        if cam_id not in uturn_cams:
            print(f"[WATCHER] ⚠ {cam_id}: config_zones.json에 중앙선 ROI 설정이 없어 불법유턴 감지를 건너뜁니다 "
                  f"(draw_roi.py로 먼저 중앙선을 그려주세요)")
            continue
        result[cam_id] = resolve_stream_url(stream_url)
    return result


def qualifying_signal_cameras(cameras):
    """자동 신호위반 감지 대상: 운영 중 + 신호위반 감지 사용 + 실제 영상 URL + 정지선 ROI가 있는 카메라."""
    _, signal_cams = zone_info()
    result = {}
    for cam in cameras:
        if cam.get("status") != "ACTIVE":
            continue
        enabled = cam.get("signalDetectionEnabled")
        if enabled is None:
            enabled = cam.get("violationDetectionEnabled")
        if not enabled:
            continue
        stream_url = cam.get("streamUrl")
        if not stream_url:
            continue
        cam_id = cam["camId"]
        if cam_id not in signal_cams:
            print(f"[WATCHER] ⚠ {cam_id}: config_zones.json에 정지선/교차로 ROI 설정이 없어 신호위반 감지를 건너뜁니다 "
                  f"(draw_roi.py로 먼저 정지선(3)/진출선(4)을 그려주세요)")
            continue
        result[cam_id] = resolve_stream_url(stream_url)
    return result


class CameraWatcher:
    def __init__(self, interval, max_concurrent, threshold=None, capture_retention_days=30, lpr=True):
        self.interval = interval
        self.max_concurrent = max_concurrent
        self.threshold = threshold  # None이면 yolo_infer.py 기본값 그대로 사용
        self.lpr = lpr
        self.capture_retention_days = capture_retention_days
        self.last_cleanup_at = 0

        # 낙하물 프로세스 풀
        self.debris_processes = {}
        self.fired_debris_cams = set()

        # 불법유턴 프로세스 풀
        self.uturn_processes = {}
        self.fired_uturn_cams = set()

        # 신호위반 프로세스 풀
        self.signal_processes = {}
        self.fired_signal_cams = set()

        # 영상 완주 및 재시도 쿨다운 트래킹 (무한 급속 재시작 방지)
        self.completed_cams = set()  # (mode, cam_id)
        self.backoff_cams = {}       # (mode, cam_id) -> next_retry_ts

    # ------------------------------------------------------------------
    # 낙하물 프로세스 관리
    def _start_debris(self, cam_id, stream_url):
        print(f"[WATCHER] 🟢 낙하물 감지 시작: {cam_id} ({stream_url})")
        cmd = [sys.executable, str(YOLO_INFER_PATH),
               "--video", stream_url, "--cam-id", cam_id, "--no-display"]
        if self.threshold is not None:
            cmd += ["--threshold", str(self.threshold)]
        proc = subprocess.Popen(cmd, cwd=str(BASE_DIR))
        self.debris_processes[cam_id] = proc

    def _stop_debris(self, cam_id, reason):
        proc = self.debris_processes.pop(cam_id, None)
        if proc is None:
            return
        print(f"[WATCHER] 🔴 낙하물 감지 중단: {cam_id} ({reason})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def sync_debris(self, targets):
        for cam_id in list(self.debris_processes.keys()):
            if cam_id not in targets:
                self._stop_debris(cam_id, "카메라 비활성화/삭제/URL 제거됨")

        for cam_id, proc in list(self.debris_processes.items()):
            if proc.poll() is not None:
                del self.debris_processes[cam_id]
                if cam_id not in self.fired_debris_cams and has_fired_debris(cam_id):
                    self.fired_debris_cams.add(cam_id)
                if cam_id in self.fired_debris_cams:
                    print(f"[WATCHER] ✅ {cam_id} 낙하물 이미 감지됨 - 더 이상 재시작하지 않음")
                else:
                    print(f"[WATCHER] ⏹ {cam_id} 낙하물 영상 프로세스 종료됨")

        now = time.time()
        for cam_id, stream_url in targets.items():
            if cam_id in self.debris_processes:
                continue
            fired_in_db = None
            if cam_id in self.fired_debris_cams:
                fired_in_db = has_fired_debris(cam_id)
                if fired_in_db:
                    continue
                self.fired_debris_cams.discard(cam_id)
                print(f"[WATCHER] 🔄 {cam_id} 낙하물 기록이 DB에서 사라짐 - 감지 재개")
            if fired_in_db is None and has_fired_debris(cam_id):
                self.fired_debris_cams.add(cam_id)
                print(f"[WATCHER] ✅ {cam_id} 낙하물 이미 감지된 카메라 - 켜지 않음")
                continue
            if len(self.debris_processes) >= self.max_concurrent:
                print(f"[WATCHER] ⚠ 낙하물 동시 실행 한도({self.max_concurrent}) 도달 - {cam_id} 대기")
                continue
            self._start_debris(cam_id, stream_url)

    # ------------------------------------------------------------------
    # 불법유턴 프로세스 관리
    def _start_uturn(self, cam_id, stream_url):
        print(f"[WATCHER] 🟢 불법유턴 감지 시작: {cam_id} ({stream_url})")
        cmd = [sys.executable, str(RUN_UTURN_PATH),
               "--video", stream_url, "--cam", cam_id,
               "--zones", str(ZONES_PATH),
               "--gateway", GATEWAY_ORIGIN,
               "--mode", "uturn"]
        if self.lpr:
            cmd.append("--lpr")
        proc = subprocess.Popen(cmd, cwd=str(D_LPR_DIR))
        self.uturn_processes[cam_id] = proc

    def _stop_uturn(self, cam_id, reason):
        proc = self.uturn_processes.pop(cam_id, None)
        if proc is None:
            return
        print(f"[WATCHER] 🔴 불법유턴 감지 중단: {cam_id} ({reason})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def sync_uturn(self, targets):
        for cam_id in list(self.uturn_processes.keys()):
            if cam_id not in targets:
                self._stop_uturn(cam_id, "카메라 비활성화/삭제/URL 제거됨")

        now = time.time()
        for cam_id, proc in list(self.uturn_processes.items()):
            poll = proc.poll()
            if poll is not None:
                del self.uturn_processes[cam_id]
                fired = has_fired_uturn(cam_id)
                if fired:
                    self.fired_uturn_cams.add(cam_id)
                    print(f"[WATCHER] ✅ {cam_id} 불법유턴 이벤트 이미 감지됨 - 더 이상 재시작하지 않음")
                else:
                    if poll == 0:
                        self.completed_cams.add(("uturn", cam_id))
                        print(f"[WATCHER] ⏹ {cam_id} 불법유턴 영상 분석 완료 (종료코드 {poll})")
                    else:
                        self.backoff_cams[("uturn", cam_id)] = now + RETRY_BACKOFF_SEC
                        print(f"[WATCHER] ⚠ {cam_id} 불법유턴 프로세스 비정상 종료 (코드 {poll}) - {RETRY_BACKOFF_SEC}초 후 재시도 가능")

        for cam_id, stream_url in targets.items():
            if cam_id in self.uturn_processes:
                continue
            fired_in_db = None
            if cam_id in self.fired_uturn_cams:
                fired_in_db = has_fired_uturn(cam_id)
                if fired_in_db:
                    continue
                self.fired_uturn_cams.discard(cam_id)
                self.completed_cams.discard(("uturn", cam_id))
                print(f"[WATCHER] 🔄 {cam_id} 불법유턴 기록이 DB에서 사라짐 - 감지 재개")
            if fired_in_db is None and has_fired_uturn(cam_id):
                self.fired_uturn_cams.add(cam_id)
                print(f"[WATCHER] ✅ {cam_id} 불법유턴 이미 감지된 카메라 - 켜지 않음")
                continue
            if ("uturn", cam_id) in self.completed_cams:
                continue
            if now < self.backoff_cams.get(("uturn", cam_id), 0):
                continue
            if len(self.uturn_processes) >= self.max_concurrent:
                print(f"[WATCHER] ⚠ 불법유턴 동시 실행 한도({self.max_concurrent}) 도달 - {cam_id} 대기")
                continue
            self._start_uturn(cam_id, stream_url)

    # ------------------------------------------------------------------
    # 신호위반 프로세스 관리
    def _start_signal(self, cam_id, stream_url):
        print(f"[WATCHER] 🟢 신호위반 감지 시작: {cam_id} ({stream_url})")
        cmd = [sys.executable, str(RUN_UTURN_PATH),
               "--video", stream_url, "--cam", cam_id,
               "--zones", str(ZONES_PATH),
               "--gateway", GATEWAY_ORIGIN,
               "--mode", "signal"]
        if self.lpr:
            cmd.append("--lpr")
        if SIGNAL_TIMELINE_PATH.exists():
            cmd += ["--signal", str(SIGNAL_TIMELINE_PATH)]
        else:
            print(f"[WATCHER] ⚠ 신호 타임라인 없음: {SIGNAL_TIMELINE_PATH}")
        moving_roi_path = resolve_demo_moving_roi(cam_id)
        if moving_roi_path is not None:
            cmd += ["--demo-moving-roi", str(moving_roi_path)]
            print(f"[WATCHER]   게임 데모 이동 ROI 적용: {moving_roi_path.name}")
        proc = subprocess.Popen(cmd, cwd=str(D_LPR_DIR))
        self.signal_processes[cam_id] = proc

    def _stop_signal(self, cam_id, reason):
        proc = self.signal_processes.pop(cam_id, None)
        if proc is None:
            return
        print(f"[WATCHER] 🔴 신호위반 감지 중단: {cam_id} ({reason})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def sync_signal(self, targets):
        for cam_id in list(self.signal_processes.keys()):
            if cam_id not in targets:
                self._stop_signal(cam_id, "카메라 비활성화/삭제/URL 제거됨")

        now = time.time()
        for cam_id, proc in list(self.signal_processes.items()):
            poll = proc.poll()
            if poll is not None:
                del self.signal_processes[cam_id]
                fired = has_fired_signal(cam_id)
                if fired:
                    self.fired_signal_cams.add(cam_id)
                    print(f"[WATCHER] ✅ {cam_id} 신호위반 이벤트 이미 감지됨 - 더 이상 재시작하지 않음")
                else:
                    if poll == 0:
                        self.completed_cams.add(("signal", cam_id))
                        print(f"[WATCHER] ⏹ {cam_id} 신호위반 영상 분석 완료 (종료코드 {poll})")
                    else:
                        self.backoff_cams[("signal", cam_id)] = now + RETRY_BACKOFF_SEC
                        print(f"[WATCHER] ⚠ {cam_id} 신호위반 프로세스 비정상 종료 (코드 {poll}) - {RETRY_BACKOFF_SEC}초 후 재시도 가능")

        for cam_id, stream_url in targets.items():
            if cam_id in self.signal_processes:
                continue
            fired_in_db = None
            if cam_id in self.fired_signal_cams:
                fired_in_db = has_fired_signal(cam_id)
                if fired_in_db:
                    continue
                self.fired_signal_cams.discard(cam_id)
                self.completed_cams.discard(("signal", cam_id))
                print(f"[WATCHER] 🔄 {cam_id} 신호위반 기록이 DB에서 사라짐 - 감지 재개")
            if fired_in_db is None and has_fired_signal(cam_id):
                self.fired_signal_cams.add(cam_id)
                print(f"[WATCHER] ✅ {cam_id} 신호위반 이미 감지된 카메라 - 켜지 않음")
                continue
            if ("signal", cam_id) in self.completed_cams:
                continue
            if now < self.backoff_cams.get(("signal", cam_id), 0):
                continue
            if len(self.signal_processes) >= self.max_concurrent:
                print(f"[WATCHER] ⚠ 신호위반 동시 실행 한도({self.max_concurrent}) 도달 - {cam_id} 대기")
                continue
            self._start_signal(cam_id, stream_url)

    # ------------------------------------------------------------------
    def run(self):
        print(f"[WATCHER] 시작. {self.interval}초 간격으로 {GATEWAY_URL} 폴링, "
              f"동시 실행 최대 {self.max_concurrent}개, "
              f"캡처 이미지 보관기간 {self.capture_retention_days}일"
              + ("(정리 안 함)" if self.capture_retention_days <= 0 else "")
              + f", 번호판 인식 {'ON' if self.lpr else 'OFF'}")
        try:
            while True:
                cameras = fetch_cameras()
                if cameras is not None:
                    debris_targets = qualifying_debris_cameras(cameras)
                    self.sync_debris(debris_targets)

                    uturn_targets = qualifying_uturn_cameras(cameras)
                    self.sync_uturn(uturn_targets)

                    signal_targets = qualifying_signal_cameras(cameras)
                    self.sync_signal(signal_targets)

                now = time.time()
                if now - self.last_cleanup_at >= CLEANUP_INTERVAL_SEC:
                    cleanup_old_captures(self.capture_retention_days)
                    self.last_cleanup_at = now

                time.sleep(self.interval)
        except KeyboardInterrupt:
            print("\n[WATCHER] 종료 신호 - 실행 중인 감지 프로세스를 모두 정리한다.")
            for cam_id in list(self.debris_processes.keys()):
                self._stop_debris(cam_id, "워처 종료")
            for cam_id in list(self.uturn_processes.keys()):
                self._stop_uturn(cam_id, "워처 종료")
            for cam_id in list(self.signal_processes.keys()):
                self._stop_signal(cam_id, "워처 종료")


def main():
    parser = argparse.ArgumentParser(description="카메라 등록 상태를 보고 낙하물/불법유턴/신호위반 감지를 자동으로 켜고 끄는 워처")
    parser.add_argument("--interval", type=int, default=10, help="폴링 간격(초)")
    parser.add_argument("--max-concurrent", type=int, default=5, help="동시 실행 가능한 감지 프로세스 수")
    parser.add_argument("--threshold", type=int, default=2, help="방치물 정지 판정 시간(초)")
    parser.add_argument("--no-lpr", action="store_true", help="위반감지 프로세스에서 번호판 인식을 끈다.")
    parser.add_argument("--capture-retention-days", type=int, default=30, help="캡처 이미지 보관일수")
    args = parser.parse_args()

    CameraWatcher(
        interval=args.interval,
        max_concurrent=args.max_concurrent,
        threshold=args.threshold,
        capture_retention_days=args.capture_retention_days,
        lpr=not args.no_lpr,
    ).run()


if __name__ == "__main__":
    main()