# 同时启动后端（uvicorn --reload）与前端（vite dev）
# 用法：pwsh -File scripts\dev.ps1

param(
    [int]$BackendPort = 8000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# 本机工具链（目录存在才加；CI 上直接用 PATH 里的 uv / node）
foreach ($toolDir in @('D:\CodePrograms\uv', 'D:\CodePrograms\volta')) {
    if (Test-Path $toolDir) { $env:PATH = "$toolDir;" + $env:PATH }
}

Write-Host "启动后端 :$BackendPort ..." -ForegroundColor Cyan
$backend = Start-Process -FilePath "uv.exe" `
    -ArgumentList @("run", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "$BackendPort") `
    -WorkingDirectory (Join-Path $root 'backend') -PassThru -NoNewWindow

Write-Host "启动前端 :5173 ..." -ForegroundColor Cyan
$frontend = Start-Process -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev") `
    -WorkingDirectory (Join-Path $root 'frontend') -PassThru -NoNewWindow

Write-Host ""
Write-Host "后端 PID = $($backend.Id)   前端 PID = $($frontend.Id)" -ForegroundColor Green
Write-Host "打开 http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "停止：Stop-Process -Id $($backend.Id),$($frontend.Id)" -ForegroundColor DarkGray
