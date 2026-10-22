# 生成 Windows 安装包（Inno Setup）
# 用法：
#   pwsh -File scripts\build-installer.ps1              # 先打包 exe，再编译安装包
#   pwsh -File scripts\build-installer.ps1 -SkipExe     # 复用 dist 里已有的 exe

param(
    [switch]$SkipExe
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PATH = "D:\CodePrograms\uv;D:\CodePrograms\volta;" + $env:PATH

$exe = Join-Path $root 'dist\traffic-forwarding.exe'

if (-not $SkipExe -or -not (Test-Path $exe)) {
    Write-Host "[1/2] 构建 exe ..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'build.ps1') -Exe
}
else {
    Write-Host "[1/2] 复用已有 exe：$exe" -ForegroundColor DarkGray
}

if (-not (Test-Path $exe)) {
    throw "找不到 $exe，请先执行 build.ps1 -Exe"
}

Write-Host "[2/2] 编译安装包 ..." -ForegroundColor Cyan

$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
)
$iscc = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) {
    $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    throw @"
未找到 ISCC.exe（Inno Setup 编译器）。
请先安装：
    winget install --id JRSoftware.InnoSetup -e
"@
}

# 版本号从后端常量读取，保证 exe 与安装包一致
$configPath = Join-Path $root 'backend\app\core\config.py'
$match = Select-String -Path $configPath -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $match) { throw "未能从 $configPath 读取 APP_VERSION" }
$version = $match.Matches[0].Groups[1].Value

Write-Host "    版本 = $version" -ForegroundColor DarkGray
Write-Host "    ISCC = $iscc" -ForegroundColor DarkGray

& $iscc "/DMyAppVersion=$version" (Join-Path $root 'installer\traffic_forwarding.iss')
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup 编译失败（exit=$LASTEXITCODE）"
}

$setup = Join-Path $root "dist\installer\TrafficForwarding-Setup-$version.exe"
if (-not (Test-Path $setup)) {
    throw "编译完成但未找到产物：$setup"
}

$size = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "完成：$setup ($size MB)" -ForegroundColor Green
Write-Host "静默安装：`"$setup`" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -ForegroundColor DarkGray
Write-Host "静默卸载：`"$env:ProgramFiles\TrafficForwarding\unins000.exe`" /VERYSILENT" -ForegroundColor DarkGray
