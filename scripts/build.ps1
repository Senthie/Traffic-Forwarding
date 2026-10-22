# 构建前端 -> 复制到后端静态目录 -> 可选打包 exe
# 用法：
#   pwsh -File scripts\build.ps1
#   pwsh -File scripts\build.ps1 -Exe

param(
    [switch]$Exe
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PATH = "D:\CodePrograms\uv;D:\CodePrograms\volta;" + $env:PATH

Write-Host "[1/3] 构建前端 ..." -ForegroundColor Cyan
Push-Location (Join-Path $root 'frontend')
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
}
finally {
    Pop-Location
}

Write-Host "[2/3] 复制静态资源 ..." -ForegroundColor Cyan
$static = Join-Path $root 'backend\app\static'
if (Test-Path $static) { Remove-Item $static -Recurse -Force }
New-Item -ItemType Directory -Path $static -Force | Out-Null
Copy-Item (Join-Path $root 'frontend\dist\*') $static -Recurse -Force
Write-Host "    -> $static" -ForegroundColor DarkGray

if (-not $Exe) {
    Write-Host "[3/3] 跳过 exe 打包（加 -Exe 启用）" -ForegroundColor DarkGray
    Write-Host "完成。启动：pwsh -File scripts\run_as_admin.ps1" -ForegroundColor Green
    exit 0
}

Write-Host "[3/3] 打包 exe（PyInstaller）..." -ForegroundColor Cyan
Push-Location (Join-Path $root 'backend')
try {
    uv sync --extra gui --extra build
    uv run pyinstaller --noconfirm --clean `
        --distpath (Join-Path $root 'dist') `
        --workpath (Join-Path $root 'build') `
        (Join-Path $root 'launcher\traffic_forwarding.spec')
}
finally {
    Pop-Location
}

Write-Host "完成：$root\dist\traffic-forwarding.exe" -ForegroundColor Green
