param([switch]$Check)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetFullPath($projectRoot).TrimEnd('\') -ne 'D:\solveguide-ai') {
  throw 'SolveGuide AI must run from D:\solveguide-ai.'
}
Set-Location -LiteralPath $projectRoot
$env:npm_config_cache = Join-Path $projectRoot '.cache\npm'
$env:TEMP = Join-Path $projectRoot '.cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$localCargo = Join-Path $projectRoot '.tools\cargo'
if (Test-Path -LiteralPath (Join-Path $localCargo 'bin\cargo.exe')) {
  $env:CARGO_HOME = $localCargo
  $env:RUSTUP_HOME = Join-Path $projectRoot '.tools\rustup'
  $env:PATH = (Join-Path $localCargo 'bin') + ';' + $env:PATH
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
  throw 'Rust is required. Run npm.cmd run setup:rust from D:\solveguide-ai.'
}
$env:RUSTUP_AUTO_INSTALL = '0'
$toolchainReady = $false
try {
  & rustc --version *> $null
  $toolchainReady = $LASTEXITCODE -eq 0
} catch { }
if (-not $toolchainReady) {
  throw 'Rust setup is incomplete. Run npm.cmd run setup:rust from D:\solveguide-ai, then retry.'
}
if ($Check) { cargo check --manifest-path src-tauri/Cargo.toml } else { npm.cmd run tauri -- dev }
exit $LASTEXITCODE
