<#
  omeca-lpr  →  omecca_Project\d_lpr  반영

  내 작업 폴더(omeca-lpr)는 git 저장소가 아니다. 팀 저장소에 올리려면
  d_lpr 로 복사해야 한다. 이 스크립트가 그 복사를 안전하게 한다.

  **커밋도 푸시도 하지 않는다.** 파일만 옮기고 git status 를 보여준다.
  올릴지 말지는 직접 판단한다.

  제외 대상 (실수로 올라가면 안 되는 것)
      .env  its_key.txt      인증키
      output\ *.mp4 *.pt     결과물·영상·가중치 (용량)
      data\ *.db             로컬 DB
      captures\ frames\      분석 중 뽑은 이미지
      .venv64\ __pycache__\  환경·캐시

  사용
      .\sync_to_team.ps1            # 뭐가 바뀌는지만 보여준다 (복사 안 함)
      .\sync_to_team.ps1 -Apply     # 실제로 복사
#>

param([switch]$Apply)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8

$SRC  = $PSScriptRoot
$REPO = Join-Path (Split-Path $SRC -Parent) "omecca_Project"
$DST  = Join-Path $REPO "d_lpr"

if (-not (Test-Path $DST)) { Write-Host "[오류] d_lpr 없음: $DST" -ForegroundColor Red; exit 1 }

# 폴더 이름으로 통째 제외
#
#   plates* 는 **직접 찍은 실제 차량 번호판 사진**이다 (개인정보). 150장.
#   d_lpr\.gitignore 가 이미 막고 있지만, 그건 '커밋'을 막을 뿐 복사는 막지
#   않는다. 팀 폴더에 원본이 놓여 있으면 .gitignore 한 줄이 지워지는 순간
#   그대로 올라간다. 애초에 옮기지 않는 것이 맞다 — 막는 곳은 두 군데여야 한다.
$SKIP_DIR = @(".venv64", "output", "__pycache__", ".pytest_cache", "data",
              "captures", "frames", ".git", "samples", "weights", ".idea", ".vscode",
              "plates", "plates_test", "plates_final", "plates_angle")
# 파일 이름 / 확장자로 제외
$SKIP_FILE = @(".env", ".env.local", "its_key.txt", ".ds_store")
#   .pth/.zip 도 뺀다. 학습한 번호판 모델(plate.pth)과 학습 데이터 zip(652MB)이
#   실수로 딸려 가면 저장소가 못 쓰게 된다.
$SKIP_EXT  = @(".mp4", ".avi", ".mkv", ".pt", ".pth", ".onnx", ".zip",
               ".db", ".sqlite3", ".log", ".pyc", ".pyo", ".coverage")

Write-Host ""
Write-Host "원본: $SRC"
Write-Host "대상: $DST"
if (-not $Apply) { Write-Host "모드: 미리보기 (복사 안 함). 실제 복사는 -Apply" -ForegroundColor Yellow }
Write-Host ""

# ------------------------------------------------------------ 복사 대상 추리기
$srcLen = $SRC.Length + 1
$files = Get-ChildItem -Path $SRC -Recurse -File -Force | Where-Object {
    $rel = $_.FullName.Substring([int]$srcLen)
    $parts = $rel.Split([IO.Path]::DirectorySeparatorChar)
    # 경로 어딘가에 제외 폴더가 있으면 버린다 (마지막 조각은 파일명이므로 뺀다)
    $inSkipDir = $false
    for ($i = 0; $i -lt $parts.Length - 1; $i++) {
        if ($SKIP_DIR -contains $parts[$i]) { $inSkipDir = $true; break }
    }
    # models\ 안의 완성 모델은 확장자 규칙(.pt/.pth)을 면제한다.
    # 팀원이 clone 만으로 같은 성능을 내려면 이 파일이 함께 가야 한다.
    $inModels = ($parts[0] -eq "models")

    (-not $inSkipDir) -and
    ($SKIP_FILE -notcontains $_.Name.ToLower()) -and
    ($inModels -or ($SKIP_EXT -notcontains $_.Extension.ToLower()))
}

$new = @(); $chg = @(); $same = 0
foreach ($f in $files) {
    $rel = $f.FullName.Substring($srcLen)
    $to  = Join-Path $DST $rel
    if (-not (Test-Path $to)) { $new += $rel }
    elseif ((Get-FileHash $f.FullName -Algorithm MD5).Hash -ne
            (Get-FileHash $to        -Algorithm MD5).Hash) { $chg += $rel }
    else { $same++ }
}

if ($new) {
    Write-Host "새 파일 $($new.Count)개" -ForegroundColor Green
    $new | Sort-Object | ForEach-Object { Write-Host "  + $_" -ForegroundColor Green }
}
if ($chg) {
    Write-Host ""
    Write-Host "바뀐 파일 $($chg.Count)개" -ForegroundColor Yellow
    $chg | Sort-Object | ForEach-Object { Write-Host "  M $_" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "그대로인 파일 $same 개 (건너뜀)"

if (-not $Apply) {
    Write-Host ""
    Write-Host "실제로 복사하려면:  .\sync_to_team.ps1 -Apply" -ForegroundColor Yellow
    exit 0
}

if (-not $new -and -not $chg) {
    Write-Host ""
    Write-Host "복사할 게 없습니다." -ForegroundColor Cyan
    exit 0
}

# ------------------------------------------------------------------- 실제 복사
Write-Host ""
Write-Host "복사 중..." -ForegroundColor Cyan
foreach ($rel in ($new + $chg)) {
    $from = Join-Path $SRC $rel
    $to   = Join-Path $DST $rel
    $dir  = Split-Path $to -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $from $to -Force
}
Write-Host "  $($new.Count + $chg.Count)개 복사 완료" -ForegroundColor Green

# ---------------------------------------------------------------- 안전 점검
Write-Host ""
Write-Host "=== 비밀값 점검 ===" -ForegroundColor Cyan
$bad = @(".env", ".env.local", "its_key.txt") |
       Where-Object { Test-Path (Join-Path $DST $_) }
if ($bad) {
    Write-Host "[위험] d_lpr 에 인증키 파일이 있습니다: $($bad -join ', ')" -ForegroundColor Red
    Write-Host "       지우고 다시 실행하세요."
    exit 1
}
Write-Host "  인증키 파일 없음 - 정상" -ForegroundColor Green

Push-Location $REPO
try {
    # .gitignore 까지 반영된, git 이 실제로 올리려는 최종 목록
    $st = @(git status --porcelain d_lpr)
    # 경로 '끝'만 본다. `.env.example` 은 값이 빈 템플릿이라 올라가도 된다 —
    # `\.env` 로 느슨하게 잡으면 그것까지 걸려서 멀쩡한 커밋이 막힌다.
    $leak = $st | Where-Object {
        # models\ 안은 일부러 올리는 것이라 검사에서 뺀다
        ($_ -notmatch '[/\\]models[/\\]') -and (
        $_ -match '[/\\](\.env|\.env\.local|its_key\.txt)$' -or
        $_ -match '\.(mp4|avi|mkv|pt|pth|onnx|zip|db|sqlite3)$' ) -or
        # 번호판 사진이 어떤 경로로든 스테이징되면 멈춘다. 위 SKIP_DIR 로 이미
        # 걸러지지만, 폴더 이름을 바꾸거나 다른 곳에 사진을 두면 새는 길이 생긴다.
        $_ -match '[/\\]plates[^/\\]*[/\\].*\.(png|jpg|jpeg)$'
    }
    if ($leak) {
        Write-Host ""
        Write-Host "[위험] 올라가면 안 되는 파일이 잡혔습니다:" -ForegroundColor Red
        $leak | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        exit 1
    }
    Write-Host ""
    Write-Host "=== git 이 본 변경 ($($st.Count)개) ===" -ForegroundColor Cyan
    if ($st) { $st | ForEach-Object { Write-Host "  $_" } } else { Write-Host "  변경 없음" }

    Write-Host ""
    Write-Host "=== 다음 할 일 (직접 실행) ===" -ForegroundColor Cyan
    Write-Host "  cd $REPO"
    Write-Host "  git add d_lpr"
    Write-Host "  git status"
    Write-Host '  git commit -m "메시지"'
    Write-Host "  git push origin main"
} finally { Pop-Location }
