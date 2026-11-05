param([switch]$InstallBuildTools, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ($projectRoot.TrimEnd('\') -ne 'D:\solveguide-ai') { throw 'Use D:\solveguide-ai.' }
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.tools\python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Set up the existing backend environment first.' }
$env:TEMP = Join-Path $projectRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
$env:PYTHONPYCACHEPREFIX = Join-Path $projectRoot '.cache\pycache'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot '.cache\pyinstaller'
[IO.Directory]::CreateDirectory($env:TEMP) | Out-Null
if ($InstallBuildTools) {
  & $python -m pip install --disable-pip-version-check -r backend/requirements-build.txt
  if ($LASTEXITCODE -ne 0) { throw 'Build-tool installation failed.' }
}
& $python -c "import PyInstaller; assert PyInstaller.__version__ == '6.22.3'"
if ($LASTEXITCODE -ne 0) { throw 'Install pinned requirements-build.txt first.' }
& $python -m PyInstaller --noconfirm --log-level WARN --distpath dist/backend --workpath .cache/backend-package/work backend/solveguide_backend.spec
if ($LASTEXITCODE -ne 0) { throw 'Backend packaging failed.' }
$bundle = Join-Path $projectRoot 'dist\backend\solveguide-backend'
'import importlib.metadata as m,json,platform,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"python":platform.python_version(),"packages":{d.metadata["Name"]:d.version for d in m.distributions() if d.metadata["Name"]}},indent=2),encoding="utf-8")' | & $python - (Join-Path $bundle 'build-info.json')
if ($LASTEXITCODE -ne 0) { throw 'Could not record build versions.' }
Write-Host "Built $bundle\solveguide-backend.exe (ship the entire folder)."
if ($SmokeTest) {
  & $python scripts/smoke-backend-package.py --bundle $bundle
  if ($LASTEXITCODE -ne 0) { throw 'Packaged backend smoke check failed.' }
}
