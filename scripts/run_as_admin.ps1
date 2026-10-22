# 以管理员身份启动后端（写操作必需）
# 用法：pwsh -File scripts\run_as_admin.ps1 [-Port 8000]

param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'

$uv = 'D:\CodePrograms\uv\uv.exe'
if (-not (Test-Path $uv)) {
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
}
if (-not $uv) {
    throw "未找到 uv，请先安装或修改本脚本中的路径。"
}

$arguments = @(
    'run', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1',
    '--port', "$Port"
)

Write-Host "以管理员身份启动后端 :$Port（将弹出 UAC 确认）" -ForegroundColor Cyan
Start-Process -FilePath $uv -ArgumentList $arguments -WorkingDirectory $backend -Verb RunAs
