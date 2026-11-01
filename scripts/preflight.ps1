param([Parameter(Mandatory = $true)][string]$RunId)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
uv run python scripts/preflight.py --run $RunId
exit $LASTEXITCODE
