param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetFullPath($projectRoot).TrimEnd('\') -ne 'D:\solveguide-ai') { throw 'SolveGuide AI must run from D:\solveguide-ai.' }
Set-Location -LiteralPath $projectRoot
$env:TEMP = Join-Path $projectRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $projectRoot '.cache\pycache'
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
$python = Join-Path $projectRoot '.tools\python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  & python -m venv .tools/python
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $python -m pip install --cache-dir $env:PIP_CACHE_DIR -r backend/requirements.lock.txt
exit $LASTEXITCODE
