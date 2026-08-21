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

# 불법유턴/신호위반(⑦) — 박지원(D) 모듈. 낙하물과 동일한 방식(카메라 등록 상태를 보고
# 자동으로 켜고 끔)으로 연결한다.
D_LPR_DIR = PROJECT_ROOT / "d_lpr"
RUN_UTURN_PATH = D_LPR_DIR / "run_uturn.py"
ZONES_PATH = D_LPR_DIR / "config_zones.json"
VIOLATION_EVENT_TYPES = ("SIGNAL_VIOLATION", "UTURN_VIOLATION")

# yolo_infer.py의 CAPTURES_DIR과 반드시 같은 경로여야 한다(사건 전/후 캡처 이미지 저장 위치).
CAPTURES_DIR = PROJECT_ROOT / "b_dashboard" / "public" / "captures"

GATEWAY_ORIGIN = os.environ.get("GATEWAY_URL", "http://localhost:8080").rstrip("/")
GATEWAY_URL = GATEWAY_ORIGIN + "/api/cameras"
EVENTS_URL = GATEWAY_ORIGIN + "/api/events"
API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")

# 낙하물 이벤트마다 사진 2장(전/후)이 새로 쌓이기만 하고 지워지는 로직이 없어서, 관제
# 요원 입장에서 디스크 용량이 끝없이 늘어난다는 피드백이 있었다 - 워처가 어차피 계속
# 떠있는 프로세스라서, 별도로 cron 등을 설정하지 않아도 이 안에서 주기적으로(기본 1시간
# 마다) 오래된 캡처 이미지를 자동으로 정리하게 한다.
CLEANUP_INTERVAL_SEC = 3600


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
    """이 카메라가 이미 낙하물(DEBRIS) 이벤트를 한 번이라도 낸 적 있는지 게이트웨이에 물어본다.
    영상이 짧아서 계속 반복재생되면 그때마다 같은 물체를 다시 "새로 놓인 낙하물"처럼 잡아
    이벤트가 끝없이 쌓이는 걸 막기 위함 - 한 카메라당 한 번 뜨면 그걸로 충분하다는 요구사항.
    조회 자체가 실패하면(게이트웨이 잠깐 끊김 등) "아직 안 뜬 것"으로 보수적으로 처리해서
    감지가 아예 멈추는 일은 없게 한다."""
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


def has_fired_violation(cam_id):
    """이 카메라가 신호위반/불법유턴 이벤트를 한 번이라도 낸 적 있는지 게이트웨이에 물어본다.
    has_fired_debris와 이유가 같다 - 짧은 테스트 영상이 반복재생되면 같은 차량의 같은 위반이
    루프마다 다시 판정되어 DB에 중복으로 쌓이는 것을 막기 위함(ByteTrack 결과가 영상 기준으로
    결정적이라, 같은 영상을 처음부터 다시 돌리면 완전히 동일한 위반 이벤트가 또 나온다).
    두 이벤트 타입(SIGNAL_VIOLATION/UTURN_VIOLATION) 중 하나라도 이미 있으면 True."""
    for event_type in VIOLATION_EVENT_TYPES:
        try:
            resp = requests.get(
                EVENTS_URL,
                params={"camId": cam_id, "eventType": event_type, "size": 1},
                headers={"X-API-Key": API_KEY},
                timeout=5,
            )
            resp.raise_for_status()
            if resp.json().get("totalElements", 0) > 0:
                return True
        except requests.exceptions.RequestException:
            continue
    return False


def zone_configured_cam_ids():
    """config_zones.json에 ROI(중앙선/정지선 등)가 등록된 cam_id 집합.
    등록 안 된 cam_id로 run_uturn.py를 띄우면 곧바로 sys.exit()로 종료돼버리는데, 그 상태로
    두면 폴링 주기(기본 10초)마다 계속 재시작을 시도하며 크래시를 반복하게 된다. 미리 걸러낸다."""
    try:
        data = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
        return {cam["cam_id"] for cam in data.get("cameras", [])}
    except (OSError, json.JSONDecodeError):
        return set()


def cleanup_old_captures(retention_days):
    """CAPTURES_DIR 안의 사건 전/후 캡처 이미지 중, 마지막 수정시각(=거의 곧 캡처된
    시각) 기준으로 retention_days보다 오래된 파일을 지운다.

    이벤트 테이블에 아직 남아있는 이벤트의 이미지를 지워도 되는지(파일이 없어지면
    상세화면/PDF에서 깨진 이미지로 보임) 여기서 DB까지 조회해서 정교하게 판단하지는
    않는다 - CCTV 원본 영상 자체도 보통 30일 등 일정 기간만 보관하다 지우는 게 일반적인
    운영 방식이라, "그보다 오래된 사건은 이미지도 같이 정리한다"는 정책으로 충분하다고
    보고 단순하게 파일 나이만 본다. 더 촘촘한 보관정책이 필요해지면(예: 리포트로 이미 뽑힌
    사건은 별도 보관) 그때 DB 조회를 추가하면 된다.
    retention_days<=0이면 정리를 아예 하지 않는다(운영자가 끄고 싶을 때 대비).
    """
    if retention_days <= 0:
        return
    if not CAPTURES_DIR.exists():
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


def qualifying_cameras(cameras):
    """자동 감지 대상: 운영 중 + 낙하물 감지 사용 + 실제 영상 URL이 있는 카메라."""
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


def qualifying_violation_cameras(cameras):
    """자동 위반감지 대상: 운영 중 + 위반감지 사용 + 실제 영상 URL + ROI 설정이 있는 카메라."""
    zoned = zone_configured_cam_ids()
    result = {}
    for cam in cameras:
        if cam.get("status") != "ACTIVE":
            continue
        if not cam.get("violationDetectionEnabled"):
            continue
        stream_url = cam.get("streamUrl")
        if not stream_url:
            continue
        cam_id = cam["camId"]
        if cam_id not in zoned:
            print(f"[WATCHER] ⚠ {cam_id}: config_zones.json에 ROI 설정이 없어 위반감지를 건너뜁니다 "
                  f"(draw_roi.py로 먼저 중앙선/정지선을 그려주세요)")
            continue
        result[cam_id] = resolve_stream_url(stream_url)
    return result


class CameraWatcher:
    def __init__(self, interval, max_concurrent, threshold=None, capture_retention_days=30):
        self.interval = interval
        self.max_concurrent = max_concurrent
        self.threshold = threshold  # None이면 yolo_infer.py 기본값(10초) 그대로 사용
        self.processes = {}  # camId -> subprocess.Popen
        self.fired_cams = set()  # 이미 낙하물 이벤트를 한 번 낸 camId - 더 이상 재시작하지 않는다
        self.capture_retention_days = capture_retention_days
        self.last_cleanup_at = 0  # time.time() 기준 - 아직 한 번도 안 돌았으면 0이라 시작하자마자 1회 실행됨

        # 불법유턴/신호위반(run_uturn.py)용 - 낙하물과 완전히 독립된 프로세스 풀로 관리한다.
        # (카메라 한 대가 낙하물 감지와 위반감지를 동시에 켤 수도 있어야 하므로 별도 dict/set)
        self.violation_processes = {}
        self.fired_violation_cams = set()

    def _start(self, cam_id, stream_url):
        print(f"[WATCHER] 🟢 감지 시작: {cam_id} ({stream_url})")
        cmd = [sys.executable, str(YOLO_INFER_PATH),
               "--video", stream_url, "--cam-id", cam_id, "--no-display"]
        if self.threshold is not None:
            cmd += ["--threshold", str(self.threshold)]
        proc = subprocess.Popen(cmd, cwd=str(BASE_DIR))
        self.processes[cam_id] = proc

    def _stop(self, cam_id, reason):
        proc = self.processes.pop(cam_id, None)
        if proc is None:
            return
        print(f"[WATCHER] 🔴 감지 중단: {cam_id} ({reason})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _start_violation(self, cam_id, stream_url):
        print(f"[WATCHER] 🟢 위반감지 시작: {cam_id} ({stream_url})")
        cmd = [sys.executable, str(RUN_UTURN_PATH),
               "--video", stream_url, "--cam", cam_id,
               "--zones", str(ZONES_PATH),
               "--gateway", GATEWAY_ORIGIN]
        proc = subprocess.Popen(cmd, cwd=str(D_LPR_DIR))
        self.violation_processes[cam_id] = proc

    def _stop_violation(self, cam_id, reason):
        proc = self.violation_processes.pop(cam_id, None)
        if proc is None:
            return
        print(f"[WATCHER] 🔴 위반감지 중단: {cam_id} ({reason})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def sync(self, targets):
        # 더 이상 조건을 만족하지 않는 카메라는 정리.
        for cam_id in list(self.processes.keys()):
            if cam_id not in targets:
                self._stop(cam_id, "카메라 비활성화/삭제/URL 제거됨")

        # 끝까지 재생돼 스스로 종료된 프로세스: 그 사이에 낙하물 이벤트를 이미 냈으면
        # 다시 켜지 않는다(짧은 영상이 반복재생되며 같은 물체로 계속 새 이벤트를 만드는 것을
        # 막기 위함 - 카메라당 한 번이면 충분하다). 아직 안 냈으면 다음 블록에서 재시작한다.
        for cam_id, proc in list(self.processes.items()):
            if proc.poll() is not None:
                del self.processes[cam_id]
                if cam_id not in self.fired_cams and has_fired_debris(cam_id):
                    self.fired_cams.add(cam_id)
                if cam_id in self.fired_cams:
                    print(f"[WATCHER] ✅ {cam_id} 낙하물 이미 감지됨 - 더 이상 재시작하지 않음")
                else:
                    print(f"[WATCHER] ⏹ {cam_id} 영상이 끝나 프로세스 종료됨 - 재시작 예정")

        # 아직 안 켜져 있는 대상만 새로 켠다. 동시 실행 개수는 캡을 둔다 - 카메라마다
        # YOLO 모델을 2개씩 새로 로드하므로, 무제한으로 켜면 CPU/GPU가 감당 못 한다.
        for cam_id, stream_url in targets.items():
            if cam_id in self.processes:
                continue
            fired_in_db = None
            if cam_id in self.fired_cams:
                # 캐시에 있어도 DB 쪽 이벤트가 지워졌을 수 있다(재테스트하려고 HeidiSQL 등에서
                # 수동으로 지운 경우) - 그럴 때 워처를 껐다 켜야만 재개되는 게 불편하다는
                # 피드백이 있어서, 캐시를 무조건 믿지 않고 DB를 다시 확인해 필요하면 재개한다.
                fired_in_db = has_fired_debris(cam_id)
                if fired_in_db:
                    continue
                self.fired_cams.discard(cam_id)
                print(f"[WATCHER] 🔄 {cam_id} 낙하물 기록이 DB에서 사라짐 - 감지 재개")
            # 세션 캐시에 없어도(워처를 방금 재시작한 경우 등) 서버에 이미 기록이 있으면 존중한다.
            if fired_in_db is None and has_fired_debris(cam_id):
                self.fired_cams.add(cam_id)
                print(f"[WATCHER] ✅ {cam_id} 낙하물 이미 감지된 카메라 - 켜지 않음")
                continue
            if len(self.processes) >= self.max_concurrent:
                print(f"[WATCHER] ⚠ 동시 실행 한도({self.max_concurrent}) 도달 - {cam_id} 대기")
                continue
            self._start(cam_id, stream_url)

    def sync_violations(self, targets):
        """sync()와 완전히 동일한 로직을 위반감지(run_uturn.py) 프로세스 풀에 적용한다."""
        for cam_id in list(self.violation_processes.keys()):
            if cam_id not in targets:
                self._stop_violation(cam_id, "카메라 비활성화/삭제/URL 제거됨")

        for cam_id, proc in list(self.violation_processes.items()):
            if proc.poll() is not None:
                del self.violation_processes[cam_id]
                if cam_id not in self.fired_violation_cams and has_fired_violation(cam_id):
                    self.fired_violation_cams.add(cam_id)
                if cam_id in self.fired_violation_cams:
                    print(f"[WATCHER] ✅ {cam_id} 위반 이벤트 이미 감지됨 - 더 이상 재시작하지 않음")
                else:
                    print(f"[WATCHER] ⏹ {cam_id} 영상이 끝나 위반감지 프로세스 종료됨 - 재시작 예정")

        for cam_id, stream_url in targets.items():
            if cam_id in self.violation_processes:
                continue
            fired_in_db = None
            if cam_id in self.fired_violation_cams:
                fired_in_db = has_fired_violation(cam_id)
                if fired_in_db:
                    continue
                self.fired_violation_cams.discard(cam_id)
                print(f"[WATCHER] 🔄 {cam_id} 위반 기록이 DB에서 사라짐 - 감지 재개")
            if fired_in_db is None and has_fired_violation(cam_id):
                self.fired_violation_cams.add(cam_id)
                print(f"[WATCHER] ✅ {cam_id} 위반 이미 감지된 카메라 - 켜지 않음")
                continue
            if len(self.violation_processes) >= self.max_concurrent:
                print(f"[WATCHER] ⚠ 위반감지 동시 실행 한도({self.max_concurrent}) 도달 - {cam_id} 대기")
                continue
            self._start_violation(cam_id, stream_url)

    def run(self):
        print(f"[WATCHER] 시작. {self.interval}초 간격으로 {GATEWAY_URL} 폴링, "
              f"동시 실행 최대 {self.max_concurrent}개, "
              f"캡처 이미지 보관기간 {self.capture_retention_days}일"
              + ("(정리 안 함)" if self.capture_retention_days <= 0 else ""))
        try:
            while True:
                cameras = fetch_cameras()
                if cameras is not None:
                    targets = qualifying_cameras(cameras)
                    self.sync(targets)
                    violation_targets = qualifying_violation_cameras(cameras)
                    self.sync_violations(violation_targets)

                # 캡처 이미지 정리는 매 폴링(--interval, 보통 2~10초)마다 돌 필요는 없으니
                # CLEANUP_INTERVAL_SEC(1시간)마다 한 번씩만 - 워처가 켜져 있는 한 계속 도니
                # 별도 cron 설정 없이도 디스크 용량이 무한정 쌓이는 걸 막아준다.
                now = time.time()
                if now - self.last_cleanup_at >= CLEANUP_INTERVAL_SEC:
                    cleanup_old_captures(self.capture_retention_days)
                    self.last_cleanup_at = now

                time.sleep(self.interval)
        except KeyboardInterrupt:
            print("\n[WATCHER] 종료 신호 - 실행 중인 감지 프로세스를 모두 정리한다.")
            for cam_id in list(self.processes.keys()):
                self._stop(cam_id, "워처 종료")
            for cam_id in list(self.violation_processes.keys()):
                self._stop_violation(cam_id, "워처 종료")


def main():
    parser = argparse.ArgumentParser(description="카메라 등록 상태를 보고 낙하물/위반 감지를 자동으로 켜고 끄는 워처")
    parser.add_argument("--interval", type=int, default=10, help="폴링 간격(초)")
    parser.add_argument("--max-concurrent", type=int, default=5, help="동시 실행 가능한 감지 프로세스 수")
    parser.add_argument("--threshold", type=int, default=2,
                        help="방치물 정지 판정 시간(초). 기본 2초 - 테스트 영상 대부분이 10초보다 "
                             "짧고, IoU 추적이 프레임 사이에 잠깐씩 끊겼다 다시 잡히는 경우가 있어 "
                             "3초는 애매하게 못 넘는 경우가 있었다(2초는 여유 있게 넘어감). "
                             "원래 10초로 되돌리려면 --threshold 10 으로 지정한다.")
    parser.add_argument("--capture-retention-days", type=int, default=30,
                        help="사건 전/후 캡처 이미지(b_dashboard/public/captures/)를 며칠까지 "
                             "보관할지. 이보다 오래된 파일은 1시간마다 자동으로 삭제된다. "
                             "0 이하로 주면 자동 정리를 끈다.")
    args = parser.parse_args()

    CameraWatcher(
        interval=args.interval,
        max_concurrent=args.max_concurrent,
        threshold=args.threshold,
        capture_retention_days=args.capture_retention_days,
    ).run()


if __name__ == "__main__":
    main()