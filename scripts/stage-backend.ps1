param([switch]$Personal)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ($root.TrimEnd('\') -ne 'D:\solveguide-ai') { throw 'Use D:\solveguide-ai.' }
$source = Join-Path $root 'dist\backend\solveguide-backend'
$target = [IO.Path]::GetFullPath((Join-Path $root '.cache\desktop-backend'))
if ($Personal) { $target = [IO.Path]::GetFullPath((Join-Path $root '.cache\personal-desktop-backend')) }
if (-not (Test-Path -LiteralPath (Join-Path $source 'solveguide-backend.exe')) -or -not (Test-Path -LiteralPath (Join-Path $source '_internal'))) { throw 'Build the backend first: scripts/build-backend.ps1' }
if ($target -notin 'D:\solveguide-ai\.cache\desktop-backend','D:\solveguide-ai\.cache\personal-desktop-backend') { throw 'Invalid staging path.' }
# Delete only this verified, generated staging directory; preserve all project/source data.
if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
[IO.Directory]::CreateDirectory($target) | Out-Null
Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $target -Recurse -Force
Write-Host 'Staged complete backend bundle outside Vite output.'
