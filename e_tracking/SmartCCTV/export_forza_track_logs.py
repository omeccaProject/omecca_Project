"""
export_forza_track_logs.py
================================================================
Forza A/B/C/D 4개 영상을 각각 한 번씩 사전 분석해서, export_track_log.py와
완전히 동일한 구조의 JSON(track log)을 web/data/에 저장한다.

왜 필요한가
----------------------------------------------------------------
웹사이트에서 CCTV(보라매역/장승배기/상도/한강대교남단)를 클릭하면 해당
Forza mp4가 웹사이트의 <video> 태그에서 그대로 재생된다. 브라우저가
재생하는 영상과 Python이 실시간으로 분석하는 영상을 프레임 단위로
동기화하려면 별도의 스트리밍 서버 + 정밀한 시간 동기화가 필요해서 훨씬
복잡하고 지연/오차가 생기기 쉽다 (export_track_log.py 상단 주석 참고).

그래서 H4642 테스트 카메라에 이미 쓰던 것과 완전히 동일한 방식 -
"미리 한 번 분석해서 JSON으로 저장 → 브라우저는 video.currentTime에
맞는 박스만 canvas에 그린다" - 을 Forza 4개 영상에도 그대로 적용한다.
새로운 분석 로직은 전혀 만들지 않았다 - export_track_log.py를 그대로
4번 호출할 뿐이다.

왜 4번의 "별도 프로세스"로 실행하는가
----------------------------------------------------------------
anomaly_detection.py는 track_states/event_logs 등을 모듈 전역 변수로
갖고 있고, export_track_log.py 내부의 YOLO 모델도 persist=True로 추적
상태를 모델 인스턴스에 저장한다. 한 프로세스에서 4개 영상을 연달아
분석하면 이전 영상의 추적 상태가 다음 영상으로 새어 들어갈 수 있다.
realtime_anomaly.py가 실제 CCTV/Forza 영상마다 완전히 별도의 OS
프로세스를 쓰는 것과 정확히 같은 이유로, 여기서도 subprocess.run()으로
영상마다 새 파이썬 프로세스를 띄운다.

cam_id는 추측이 아니라 실제 존재하는 UTIC 카메라 레코드를 그대로
재사용한다. realtime_anomaly.py의 DEMO_SOURCES에 이미 정리되어 있는
ref_cam_id(보라매역=L010111, 장승배기=L010271, 상도=L010128,
한강대교남단=L010481)를 그대로 가져다 쓴다 - 여기서 새로 정의하지 않는다
(단일 출처 유지 - DEMO_SOURCES가 바뀌면 이 스크립트도 자동으로 반영됨).

실행 방법
----------------------------------------------------------------
    python export_forza_track_logs.py

완료되면 web/data/ 안에 다음 4개 파일이 생긴다 (영상 자체가 바뀌지
않는 한 한 번만 실행하면 된다 - export_track_log.py와 동일).
    forza-track-log-L010111.json (A, 보라매역)
    forza-track-log-L010271.json (B, 장승배기)
    forza-track-log-L010128.json (C, 상도)
    forza-track-log-L010481.json (D, 한강대교남단)

주의: 이 스크립트는 realtime_anomaly.py를 import해서 DEMO_SOURCES만
가져다 쓴다 (실행하지는 않는다 - realtime_anomaly.py는
`if __name__ == "__main__":` 가드로 보호되어 있어 import만으로는
아무 프로세스도 뜨지 않는다).
"""

import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from realtime_anomaly import DEMO_SOURCES  # 영상 경로/좌표/실제 cam_id의 단일 출처 - 여기서 새로 정의하지 않는다

OUTPUT_DIR = os.path.join(_THIS_DIR, "web", "data")
EXPORT_SCRIPT = os.path.join(_THIS_DIR, "export_track_log.py")


def main():
    ordered = sorted(DEMO_SOURCES.items(), key=lambda kv: kv[1]["order"])
    print(f"Forza 데모 {len(ordered)}개 영상을 순서대로(A→B→C→D) 사전 분석합니다.")
    print("(영상마다 완전히 독립된 프로세스로 실행 - anomaly_detection.py 전역 상태가 섞이지 않습니다)\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    succeeded = []
    failed = []

    for demo_id, config in ordered:
        cam_id = config["ref_cam_id"]
        video_path = os.path.join(_THIS_DIR, config["path"])
        output_json = os.path.join(OUTPUT_DIR, f"forza-track-log-{cam_id}.json")

        if not os.path.isfile(video_path):
            print(f"[{demo_id}] 건너뜀 - 영상 파일이 없습니다: {video_path}")
            failed.append(demo_id)
            continue

        print(f"[{demo_id}] {config['name']} ({cam_id}) 분석 시작 - {video_path}")
        result = subprocess.run(
            [
                sys.executable,
                EXPORT_SCRIPT,
                "--video", video_path,
                "--output", output_json,
                "--cam-id", cam_id,
            ],
            cwd=_THIS_DIR,
        )
        if result.returncode != 0:
            print(f"[{demo_id}] 실패 (exit code {result.returncode}) - 나머지 영상은 계속 진행합니다.\n")
            failed.append(demo_id)
            continue

        print(f"[{demo_id}] 완료: {output_json}\n")
        succeeded.append(demo_id)

    print("=" * 60)
    print(f"완료: {succeeded} / 실패: {failed or '없음'}")
    if succeeded:
        print("web/index.html에서 보라매역/장승배기/상도/한강대교남단을 클릭해 확인하세요.")


if __name__ == "__main__":
    main()