<#
  검증 일괄 실행 — 김준호 e_tracking(YOLO11m) 으로 추적한 뒤 우리 모듈로 판정한다.

  "omecca_Project 코드로 돌리고 결과는 omeca-lpr\output 에" 를 그대로 자동화한 것.
  추적 스크립트는 팀 저장소 쪽 파일을 그대로 쓰고, 건드리지 않는다.
  출력 경로만 우리 쪽으로 돌린다.

  결과 (전부 omeca-lpr\output)
      y_<CAM>.json          추적 로그      ← 김준호 모듈이 만든 것
      y_<CAM>_events.json   위반 이벤트    ← 우리 판정 결과
      y_<CAM>_result.mp4    판정 과정 영상

  사전 준비 (한 번만)
      cd C:\Users\박지원\Desktop\d\omeca-lpr
      .\.venv64\Scripts\python.exe -m pip install ultralytics

  실행
      .\run_all.ps1                 # 전부
      .\run_all.ps1 -Only UTURN3    # 하나만
      .\run_all.ps1 -SkipTrack      # 추적은 건너뛰고 판정만 다시
#>

param(
    [string]$Only = "",
    [switch]$SkipTrack,
    [switch]$SkipJudge
)

$ErrorActionPreference = "Continue"
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8

$LPR   = $PSScriptRoot
$D     = Split-Path $LPR -Parent
$TRACK = Join-Path $D "omecca_Project\e_tracking\SmartCCTV"
$OUT   = Join-Path $LPR "output"

# 파이썬 — 가상환경이 있으면 그걸, 없으면 시스템 python
$PY = Join-Path $LPR ".venv64\Scripts\python.exe"
if (-not (Test-Path $PY)) { $PY = "python" }

# 영상 ↔ cam_id ↔ 신호 타임라인
#   cam_id 는 config_zones.json 에 등록된 이름이어야 한다 (draw_roi.py 로 그은 것).
#   신호 타임라인은 신호위반 판정에만 필요하다. 유턴은 없어도 된다.
$JOBS = @(
    @{ Video = "불법유턴3.mp4"; Cam = "UTURN3";  Signal = "" },
    @{ Video = "불법유턴5.mp4"; Cam = "UTURN5";  Signal = "" },
    @{ Video = "불법유턴6.mp4"; Cam = "UTURN6";  Signal = "" },
    @{ Video = "불법유턴7.mp4"; Cam = "UTURN7";  Signal = "" },
    @{ Video = "신호위반2.mp4"; Cam = "SIGNAL2"; Signal = "output\sig2_timeline.json" }
)

# ---------------------------------------------------------------- 사전 점검
if (-not (Test-Path (Join-Path $TRACK "export_track_log.py"))) {
    Write-Host "[오류] 김준호 추적 스크립트를 못 찾았습니다:" -ForegroundColor Red
    Write-Host "       $TRACK\export_track_log.py"
    Write-Host "       omecca_Project 폴더가 omeca-lpr 와 같은 위치에 있어야 합니다."
    exit 1
}
if (-not (Test-Path $OUT)) { New-Item -ItemType Directory -Path $OUT | Out-Null }

if ($Only) { $JOBS = $JOBS | Where-Object { $_.Cam -eq $Only } }
if (-not $JOBS) { Write-Host "[오류] -Only $Only 에 해당하는 작업이 없습니다." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "python : $PY"
Write-Host "추적   : $TRACK"
Write-Host "출력   : $OUT"
Write-Host "대상   : $(($JOBS | ForEach-Object { $_.Cam }) -join ', ')"

# ---------------------------------------------------- 1단계: 추적 (팀 코드)
if (-not $SkipTrack) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " 1단계 — omecca_Project\e_tracking 으로 차량 추적 (YOLO11m)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    Push-Location $TRACK
    foreach ($j in $JOBS) {
        $src = Join-Path $D $j.Video
        $dst = Join-Path $OUT ("y_" + $j.Cam + ".json")
        Write-Host ""
        Write-Host "[추적] $($j.Video)  →  output\y_$($j.Cam).json" -ForegroundColor Yellow
        if (-not (Test-Path $src)) { Write-Host "  건너뜀 — 영상 없음: $src" -ForegroundColor DarkYellow; continue }
        & $PY export_track_log.py --video $src --output $dst --cam-id $j.Cam
        if ($LASTEXITCODE -ne 0) { Write-Host "  추적 실패 (종료코드 $LASTEXITCODE)" -ForegroundColor Red }
    }
    Pop-Location
}

# ------------------------------------------------- 2단계: 판정 (우리 코드)
if (-not $SkipJudge) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " 2단계 — omeca-lpr 로 위반 판정" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    Push-Location $LPR
    foreach ($j in $JOBS) {
        $log = Join-Path $OUT ("y_" + $j.Cam + ".json")
        Write-Host ""
        Write-Host "[판정] $($j.Cam)" -ForegroundColor Yellow
        if (-not (Test-Path $log)) { Write-Host "  건너뜀 — 추적 로그 없음" -ForegroundColor DarkYellow; continue }

        # 추적 로그는 좌표만 준다. --video 를 같이 줘야 그 영상 위에 결과를 그린다.
        $cmd = @(
            "run_uturn.py",
            "--track-log", "output\y_$($j.Cam).json",
            "--cam",       $j.Cam,
            "--video",     "..\$($j.Video)",
            "--save",      "output\y_$($j.Cam)_result.mp4",
            "--events",    "output\y_$($j.Cam)_events.json"
        )
        if ($j.Signal -and (Test-Path (Join-Path $LPR $j.Signal))) {
            $cmd += @("--signal", $j.Signal)
        } elseif ($j.Signal) {
            Write-Host "  주의 — 신호 타임라인 없음($($j.Signal)). 신호위반은 판정 보류됩니다." -ForegroundColor DarkYellow
        }
        & $PY @cmd
    }
    Pop-Location
}

# ---------------------------------------------------------------- 결과 요약
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " 결과 요약" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

foreach ($j in $JOBS) {
    $ev = Join-Path $OUT ("y_" + $j.Cam + "_events.json")
    if (-not (Test-Path $ev)) { Write-Host ("{0,-9} 결과 없음" -f $j.Cam) -ForegroundColor DarkGray; continue }
    try {
        # 파일 구조: { video, cam_id, tracker, frames_processed, events: [...] }
        $data = Get-Content $ev -Raw -Encoding UTF8 | ConvertFrom-Json
        $evts = @($data.events)
        if ($evts.Count -eq 0) {
            Write-Host ("{0,-9} 위반 없음  (프레임 {1})" -f $j.Cam, $data.frames_processed)
        } else {
            Write-Host ("{0,-9} 위반 {1}건  (프레임 {2}, 추적기 {3})" -f `
                $j.Cam, $evts.Count, $data.frames_processed, $data.tracker) -ForegroundColor Green
            foreach ($e in $evts) {
                Write-Host ("            t={0,6:F2}s  #{1}  {2}  {3}" -f `
                    $e.timestamp, $e.track_id, $e.label, $e.subtype)
            }
        }
    } catch {
        Write-Host ("{0,-9} 이벤트 파일을 읽지 못했습니다" -f $j.Cam) -ForegroundColor Red
    }
}
Write-Host ""
Write-Host "파일 위치: $OUT"
