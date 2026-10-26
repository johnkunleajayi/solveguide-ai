$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetFullPath($projectRoot).TrimEnd('\') -ne 'D:\solveguide-ai') {
    throw 'SolveGuide AI must remain in D:\solveguide-ai.'
}
Set-Location -LiteralPath $projectRoot
$env:CARGO_HOME = Join-Path $projectRoot '.tools\cargo'
$env:RUSTUP_HOME = Join-Path $projectRoot '.tools\rustup'
$env:TEMP = Join-Path $projectRoot '.cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path '.tools', $env:TEMP | Out-Null
$installer = Join-Path $projectRoot '.tools\rustup-init.exe'
if (-not (Test-Path -LiteralPath $installer)) {
    Invoke-WebRequest 'https://win.rustup.rs/x86_64' -OutFile $installer
}
& $installer -y --no-modify-path --profile minimal --default-toolchain stable
exit $LASTEXITCODE