<#
  오메카3 통합 실행 — 서버 3개를 한 번에 띄운다.

      .\start.ps1            준비 상태만 점검 (실행 안 함)
      .\start.ps1 -Run       점검 후 창 3개를 띄우고 브라우저를 연다
      .\start.ps1 -Run -Mock 위에 더해 가짜 이벤트 10건까지 보낸다

  띄우는 것
      b_gateway    :8080   API + DB (Flyway 가 스키마 자동 적용)
      b_dashboard  :5173   관제 화면
      지도 서버     :4000   e_tracking/SmartCCTV/server

  DB 는 손댈 필요 없다. 게이트웨이가 뜨면서 Flyway 가 데이터베이스·테이블·시드를
  전부 만든다. schema.sql 을 직접 실행하던 방식은 이제 쓰지 않는다.

  [2026-08-27 수정 - 이시헌]
  1. 게이트웨이를 예전엔 미리 빌드된 jar로 바로 실행했는데, 다들 코드 계속 
     고치는 지금 시기엔 "빌드를 깜빡해서 옛날 코드가 실행되는" 사고가 나기 
     쉽다(예: 오늘 WantedPerson 관련 새 파일 추가 후 jar 재빌드 안 하면 
     반영 안 됨). 그래서 실행 직전에 항상 자동으로 재빌드하도록 바꿈 - 
     시간이 조금 더 걸리는 대신(수십 초) "왜 안 바뀌지" 삽질을 원천 차단.
  2. camera_watcher.py를 그냥 "python"으로 실행하면, 그 파이썬이 venv가 
     아니라 시스템 기본 파이썬이면 face_recognition 등을 못 찾아 
     ModuleNotFoundError로 죽는다(오늘 실제로 겪음). venv\Scripts\python.exe가 
     있으면 그걸 우선 쓰고, 없으면 기존처럼 python으로 폴백하게 함.
#>

param([switch]$Run, [switch]$Mock)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ROOT = $PSScriptRoot

$ok = $true
function Chk($name, $cond, $hint) {
    if ($cond) { Write-Host "  [OK]   $name" -ForegroundColor Green }
    else { Write-Host "  [필요] $name  → $hint" -ForegroundColor Yellow; $script:ok = $false }
}
function Has($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

Write-Host ""
Write-Host "오메카3 통합 실행 점검" -ForegroundColor Cyan
Write-Host ("-" * 62)

# ---------------------------------------------------------------- 도구
Chk "Java"   (Has java)   "Java 21 설치 (java -version)"
Chk "Node"   (Has node)   "Node.js 18 이상 설치 (node -v)"
Chk "Python" ((Has python) -or (Has python3)) "Python 3 설치"

# ---------------------------------------------------------------- 설정 파일
#   .env 가 없으면 .env.example 을 복사해 준다. 다만 비밀번호는 사람이 채워야 하므로
#   자리표시자가 그대로면 실행을 막는다 — 그 상태로 띄우면 Access denied 로 죽는데,
#   스택 트레이스가 길어서 원인을 찾는 데 시간이 걸린다.
$gwEnv = Join-Path $ROOT "b_gateway\.env"
if (-not (Test-Path $gwEnv)) {
    Copy-Item (Join-Path $ROOT "b_gateway\.env.example") $gwEnv
    Write-Host "  [생성] b_gateway\.env  (.env.example 에서 복사)" -ForegroundColor Cyan
}
$pw = (Select-String -Path $gwEnv -Pattern '^DB_PASSWORD=(.*)$').Matches.Groups[1].Value
Chk "b_gateway\.env 비밀번호" `
    ($pw -and $pw.Trim() -ne '' -and $pw -notmatch '(?i)CHANGE|password|_MySQL_|YOUR') `
    "b_gateway\.env 의 DB_PASSWORD 를 본인 MySQL 비밀번호로 바꾸세요 (현재: '$pw')"

$mapEnv = Join-Path $ROOT "e_tracking\SmartCCTV\.env"
if (-not (Test-Path $mapEnv)) {
    Copy-Item (Join-Path $ROOT "e_tracking\SmartCCTV\.env.example") $mapEnv
    Write-Host "  [생성] e_tracking\SmartCCTV\.env" -ForegroundColor Cyan
}
Chk "지도 서버 .env" (Test-Path $mapEnv) "e_tracking\SmartCCTV\.env.example 을 .env 로 복사"

# ---------------------------------------------------------------- 빌드 산출물
# [수정] jar 존재 여부만 확인하던 것에서, "빌드는 실행 직전에 항상 새로 한다"로
# 바뀌었으므로 여기서는 mvnw 존재 여부만 확인한다 - 실제 재빌드는 아래 실행
# 단계에서 수행.
Chk "게이트웨이 mvnw" (Test-Path (Join-Path $ROOT "b_gateway\mvnw.cmd")) `
    "b_gateway 폴더에 mvnw.cmd 가 있는지 확인하세요"
Chk "대시보드 패키지" (Test-Path (Join-Path $ROOT "b_dashboard\node_modules")) `
    "cd b_dashboard;  npm install"
Chk "지도 서버 패키지" (Test-Path (Join-Path $ROOT "e_tracking\SmartCCTV\server\node_modules")) `
    "cd e_tracking\SmartCCTV\server;  npm install"

Write-Host ("-" * 62)
if (-not $ok) {
    Write-Host "위 항목을 먼저 해결하세요." -ForegroundColor Yellow
    exit 1
}
Write-Host "모두 준비됨." -ForegroundColor Green

if (-not $Run) {
    Write-Host ""
    Write-Host "실제로 띄우려면:  .\start.ps1 -Run" -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------- 실행
#   각 서버는 자기 폴더에서 떠야 한다 — 게이트웨이는 .env 를, 지도 서버는 videos/ 를
#   현재 폴더 기준으로 찾는다. 그래서 창마다 cd 를 먼저 넣는다.
function Launch($title, $dir, $cmd) {
    Write-Host "  띄우는 중: $title" -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle='$title'; Set-Location '$dir'; $cmd"
    )
}

# [수정] 게이트웨이는 창 안에서 "재빌드 후 실행"을 한 번에 하도록 명령을 합쳐서 넣는다.
# mvnw.cmd 는 Windows 배치파일이라 PowerShell에서 직접 호출 시 & 로 감싸야 안전하다.
# clean package 가 몇십 초 걸릴 수 있으니, 아래 Start-Sleep 대기시간도 12초 → 40초로
# 늘렸다(테스트는 스킵하지만 컴파일+패키징 자체는 시간이 걸림).
$gatewayCmd = "& .\mvnw.cmd clean package -DskipTests; " +
              "`$jar = Get-ChildItem target -Filter '*.jar' | Where-Object { `$_.Name -notlike '*sources*' } | Select-Object -First 1; " +
              "java -jar `$jar.FullName"

Write-Host ""
Launch "omecca - gateway :8080" (Join-Path $ROOT "b_gateway") $gatewayCmd
Start-Sleep -Seconds 40       # 재빌드 + Flyway 마이그레이션 + 기동을 기다린다 (기존 12초 → 40초)
Launch "omecca - map :4000"      (Join-Path $ROOT "e_tracking\SmartCCTV\server") "node server.js"
Launch "omecca - dashboard :5173" (Join-Path $ROOT "b_dashboard") "npm run dev"

# 카메라 관리에서 "낙하물 감지 사용"을 켠 카메라를 등록하면 곧바로 감지가 붙도록,
# 워처도 매번 손으로 켜지 않고 여기서 같이 띄운다. 간격을 2초로 짧게 줘서, 카메라
# 등록 후 체감상 거의 즉시 감지가 시작되는 것처럼 보이게 한다 (여전히 폴링 방식이지만
# 2초면 데모/실사용에서는 "바로 반영된다"로 느껴진다 - 진짜 이벤트 기반 트리거는 아님).
#
# [수정] venv\Scripts\python.exe가 있으면 그걸 우선 사용 - face_recognition 등
# 의존성이 venv에만 설치돼 있는 경우, 시스템 기본 python으로 실행하면
# ModuleNotFoundError로 곧바로 죽는다(camera_watcher.py가 켜지자마자 실패하는데
# 워처 자체는 죽지 않고 계속 재시도만 반복해서, 언뜻 보면 떠 있는 것처럼 보여
# 원인 파악이 늦어지기 쉽다).
$watcher = Join-Path $ROOT "a_core\camera_watcher.py"
$venvPython = Join-Path $ROOT "venv\Scripts\python.exe"
$pythonForWatcher = if (Test-Path $venvPython) { $venvPython } else { "python" }
if (Test-Path $watcher) {
    Launch "omecca - camera_watcher" (Join-Path $ROOT "a_core") "& '$pythonForWatcher' camera_watcher.py --interval 2"
} else {
    Write-Host "  [건너뜀] a_core\camera_watcher.py 없음 - 낙하물 자동 감지는 수동 실행 필요" -ForegroundColor DarkGray
}

Start-Sleep -Seconds 6

Write-Host ""
Write-Host "브라우저: http://localhost:5173   (로그인 admin / admin1234)" -ForegroundColor Green
Start-Process "http://localhost:5173"

if ($Mock) {
    Write-Host ""
    Write-Host "가짜 이벤트 10건 전송..." -ForegroundColor Cyan
    Push-Location (Join-Path $ROOT "b_gateway")
    try { python scripts\mock_events.py --count 10 --interval 1 } finally { Pop-Location }
}

Write-Host ""
Write-Host "끄려면 각 창에서 Ctrl+C 또는 창을 닫으세요." -ForegroundColor DarkGray