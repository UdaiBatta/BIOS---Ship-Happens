# One-command local setup, tests and launch of EgoHand Twin on Windows (backend + worker + viewer).
# Usage, from the repository root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1          # set up, then start
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Test    # set up, run all tests, then start
# Everything stays on this machine: the server binds to 127.0.0.1 only.
param([switch]$Test, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Clip = Join-Path $Root 'data\private\mytronlabs-000060-016.mp4'
$Release = 'ps4-baseline-handoff-20261031'
$Repo = 'UdaiBatta/BIOS---Ship-Happens'

function Need($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "Missing: $name. $hint" }
}
function Run([string]$what, [scriptblock]$block) {
    Write-Host "==> $what" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { throw "Failed ($LASTEXITCODE): $what" }
}

Need uv 'Install: winget install --id=astral-sh.uv -e   (then open a new PowerShell window)'
Need ffmpeg 'Install: winget install --id=Gyan.FFmpeg -e   (then open a new PowerShell window)'
Need ffprobe 'Install FFmpeg (it provides ffprobe)'

Run 'Installing dependencies' { uv sync --extra dev --extra viewer --extra backend }
Run 'Fetching the hand model' { uv run egohand fetch-model | Out-Null }
uv run rerun analytics disable | Out-Null
Run 'Checking the MediaPipe runtime' { uv run egohand doctor | Select-String 'mediapipe_runtime' }

$HasMedia = (Test-Path (Join-Path $Root 'media')) -and (Get-ChildItem (Join-Path $Root 'media') -Recurse -File -Include *.mp4,*.mov,*.mkv,*.avi,*.m4v,*.webm | Select-Object -First 1)
if (-not (Test-Path $Clip) -and -not $HasMedia) {
    Write-Host "==> $Clip not found; downloading it from the private release (needs: gh auth login)" -ForegroundColor Cyan
    Need gh "Install GitHub CLI (winget install --id=GitHub.cli -e) and run: gh auth login. Or download ps4-source-video.zip from https://github.com/$Repo/releases/tag/$Release and unzip it here."
    $Tmp = Join-Path ([IO.Path]::GetTempPath()) ("egohand-" + [guid]::NewGuid())
    New-Item -ItemType Directory $Tmp | Out-Null
    Run 'Downloading ps4-source-video.zip' { gh release download $Release --repo $Repo --dir $Tmp -p ps4-source-video.zip -p SHA256SUMS }
    $Zip = Join-Path $Tmp 'ps4-source-video.zip'
    $Expected = ((Select-String -Path (Join-Path $Tmp 'SHA256SUMS') -Pattern 'ps4-source-video\.zip').Line -split '\s+')[0].ToLower()
    $Actual = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLower()
    if ($Expected -ne $Actual) { throw "SHA-256 mismatch for ps4-source-video.zip: expected $Expected, got $Actual" }
    Write-Host "    SHA-256 OK ($Actual)"
    Run 'Unzipping the clip' { uv run python -m zipfile -e $Zip . }
    Remove-Item -Recurse -Force $Tmp
    if (-not (Test-Path $Clip)) { throw "The zip did not contain $Clip" }
}

if ($Test) {
    Run 'Core tests (pytest)' { uv run pytest -q }
    Push-Location backend
    try { Run 'Backend tests (Django)' { uv run python manage.py test api -v 1 } } finally { Pop-Location }
}

# A server or worker left over from an earlier launch keeps running OLD code (it does not reload),
# so it would reject new presets and miss new viewer files. Stop them before starting fresh ones.
$Old = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'manage\.py"?\s+(runserver\s+127\.0\.0\.1:8000|egohand_worker)' })
if ($Old.Count) {
    Write-Host "==> Stopping $($Old.Count) EgoHand server/worker process(es) from an earlier launch" -ForegroundColor Cyan
    $Old | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is still in use by another program. Close it (or the old server window) and run this script again.'
}

Set-Location (Join-Path $Root 'backend')
Run 'Preparing the backend database' { uv run python manage.py migrate -v0 }
$Media = Join-Path $Root 'media'
$ToRegister = @()
if (Test-Path $Clip) { $ToRegister += $Clip }
if (Test-Path $Media) { $ToRegister += $Media }
Run 'Registering the clip and every video in media\' { uv run python manage.py egohand_register @ToRegister }

Write-Host '==> Starting the worker in a second window (close that window to stop it)' -ForegroundColor Cyan
$Backend = (Get-Location).Path
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$Backend'; uv run python manage.py egohand_worker --recover"
if (-not $NoBrowser) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-Command', 'Start-Sleep 5; Start-Process http://127.0.0.1:8000/'
}
Write-Host '    Open http://127.0.0.1:8000/  ->  Backend row: pick a video, preset recall, start 0, length 30, Process'
Write-Host '    Ctrl+C here stops the server.'
uv run python manage.py runserver 127.0.0.1:8000 --noreload
