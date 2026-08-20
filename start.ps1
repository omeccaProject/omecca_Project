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
    ($pw -and $pw -notmatch '여기에|본인|CHANGE|password') `
    "b_gateway\.env 의 DB_PASSWORD 를 본인 MySQL 비밀번호로 바꾸세요 (현재: '$pw')"

$mapEnv = Join-Path $ROOT "e_tracking\SmartCCTV\.env"
if (-not (Test-Path $mapEnv)) {
    Copy-Item (Join-Path $ROOT "e_tracking\SmartCCTV\.env.example") $mapEnv
    Write-Host "  [생성] e_tracking\SmartCCTV\.env" -ForegroundColor Cyan
}
Chk "지도 서버 .env" (Test-Path $mapEnv) "e_tracking\SmartCCTV\.env.example 을 .env 로 복사"

# ---------------------------------------------------------------- 빌드 산출물
$jar = Get-ChildItem (Join-Path $ROOT "b_gateway\target") -Filter "*.jar" -EA SilentlyContinue |
       Where-Object { $_.Name -notlike "*sources*" } | Select-Object -First 1
Chk "게이트웨이 jar" ($null -ne $jar) "cd b_gateway;  .\mvnw clean package -DskipTests"
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

Write-Host ""
Launch "omecca - gateway :8080" (Join-Path $ROOT "b_gateway") "java -jar '$($jar.FullName)'"
Start-Sleep -Seconds 12       # Flyway 마이그레이션 + 기동을 기다린다
Launch "omecca - map :4000"      (Join-Path $ROOT "e_tracking\SmartCCTV\server") "node server.js"
Launch "omecca - dashboard :5173" (Join-Path $ROOT "b_dashboard") "npm run dev"
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
