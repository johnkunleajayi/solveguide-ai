param([switch]$Test, [switch]$Lint)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetFullPath($projectRoot).TrimEnd('\') -ne 'D:\solveguide-ai') {
  throw 'SolveGuide AI must run from D:\solveguide-ai.'
}
Set-Location -LiteralPath $projectRoot
$env:TEMP = Join-Path $projectRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $projectRoot '.cache\pycache'
$env:RUFF_CACHE_DIR = Join-Path $projectRoot '.cache\ruff'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$python = Join-Path $projectRoot '.tools\python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .tools/python and install backend requirements first; see README.md.' }
Set-Location -LiteralPath (Join-Path $projectRoot 'backend')
if ($Test) {
  & $python -m pytest --basetemp (Join-Path $projectRoot '.cache\pytest-tmp')
} elseif ($Lint) {
  & $python -m ruff check .
  if ($LASTEXITCODE -eq 0) { & $python -m ruff format --check . }
} else {
  # Loopback only. No access log or request payload logging.
  & $python -m app.runtime
}
exit $LASTEXITCODE
