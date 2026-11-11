<#
.SYNOPSIS
    等 BlueArchive.exe 加载 GameAssembly.dll 后立刻挂起进程，给 CE 留出 attach + 下断点的时间。

.DESCRIPTION
    游戏的 ExcelDB.db 在启动预加载阶段很快就打开，手动 attach 常常来不及。
    本脚本轮询进程与模块，一旦 GameAssembly.dll 映射进内存就 NtSuspendProcess 冻结整个进程；
    你在 CE 里 attach、扫 AOB、下硬件断点完成后，回到本窗口按回车放行即可。

    加 -AutoContinue 切换为半自动模式：CE 里的 scripts/find_db_key.lua 下好断点后会写标记文件，
    本脚本检测到标记就自动放行；断点命中后自动读取密钥并校验，不需要回窗口按回车。
    标记与密钥文件放在 %LOCALAPPDATA%\batr\，两个脚本靠它握手。

.EXAMPLE
    pwsh -File scripts/suspend_until_gameassembly.ps1 -AutoContinue
    然后从 Steam 启动游戏，再在 CE 的 Lua 窗口执行 scripts/find_db_key.lua。
#>
param(
    [string]$ProcessName = "BlueArchive",
    [string]$ModuleName  = "GameAssembly.dll",
    [int]$TimeoutSec     = 300,
    # 半自动模式：等 Lua 写好断点标记 / 等命中后写出密钥的最长等待秒数
    [switch]$AutoContinue,
    [int]$ReadyTimeoutSec = 180,
    [int]$KeyTimeoutSec   = 180,
    # 校验用的库路径，默认用 work/db 下的干净副本
    [string]$DbPath = ""
)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "必须以管理员身份运行：游戏进程是高完整性级别（Steam 以管理员启动），普通权限枚举不到它的模块、也挂不起它。" -ForegroundColor Red
    exit 1
}

Add-Type -Namespace Native -Name ProcApi -MemberDefinition @'
[DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr h);
[DllImport("ntdll.dll")] public static extern int NtResumeProcess(IntPtr h);
'@

# 与 scripts/find_db_key.lua 约定的握手文件（两边都用 %LOCALAPPDATA%\batr）
$repoRoot = Split-Path -Parent $PSScriptRoot
$workDir = Join-Path $env:LOCALAPPDATA "batr"
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
$readyFile = Join-Path $workDir ".key_hook_ready"
$keyFile = Join-Path $workDir "db_key.txt"
Remove-Item $readyFile, $keyFile -ErrorAction SilentlyContinue

$deadline = (Get-Date).AddSeconds($TimeoutSec)

Write-Host "等待 $ProcessName.exe 启动（$TimeoutSec 秒内）..."
$proc = $null
while (-not $proc -and (Get-Date) -lt $deadline) {
    $proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $proc) { Start-Sleep -Milliseconds 100 }
}
if (-not $proc) {
    Write-Host "超时：没等到 $ProcessName.exe。" -ForegroundColor Red
    exit 1
}
$procId = $proc.Id
Write-Host "发现进程 PID=$procId，等待 $ModuleName 加载..."
$proc = Get-Process -Id $procId

$loaded = $false
$base = ""
while (-not $loaded -and (Get-Date) -lt $deadline) {
    try {
        $mod = $proc.Modules | Where-Object { $_.ModuleName -eq $ModuleName } | Select-Object -First 1
        if ($mod) {
            $loaded = $true
            $base = "0x{0:X}" -f [int64]$mod.BaseAddress
        }
    }
    catch {
        Write-Host "枚举模块失败（$($_.Exception.Message)），确认本窗口是管理员权限。" -ForegroundColor Red
        exit 1
    }
    if (-not $loaded) {
        Start-Sleep -Milliseconds 100
        $proc.Refresh()
    }
}
if (-not $loaded) {
    Write-Host "超时：$ModuleName 未加载。" -ForegroundColor Red
    exit 1
}
Write-Host "$ModuleName 基址 = $base"

$h = $proc.Handle
[Native.ProcApi]::NtSuspendProcess($h) | Out-Null
Write-Host ""
Write-Host "已挂起 PID=$procId。现在去 CE：attach -> 扫 AOB -> 下硬件断点。" -ForegroundColor Green

if ($AutoContinue) {
    Write-Host "半自动模式：在 CE 里执行 scripts/find_db_key.lua，断点下好后本窗口会自动放行。" -ForegroundColor Yellow
    $readyDeadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
    while (-not (Test-Path $readyFile) -and (Get-Date) -lt $readyDeadline) { Start-Sleep -Milliseconds 200 }
    if (Test-Path $readyFile) {
        Write-Host "检测到断点已就绪，放行。" -ForegroundColor Green
    }
    else {
        Write-Host "等待断点标记超时（$ReadyTimeoutSec 秒），仍然放行——这次很可能错过开库，建议重来。" -ForegroundColor Red
    }
}
else {
    Read-Host "全部下好之后，回到这里按回车放行"
}
[Native.ProcApi]::NtResumeProcess($h) | Out-Null
Write-Host "已放行，等断点命中。" -ForegroundColor Green

# 半自动模式：等 Lua 把密钥写出来，然后校验
if (-not $AutoContinue) { exit 0 }

$keyDeadline = (Get-Date).AddSeconds($KeyTimeoutSec)
$key = ""
while ((Get-Date) -lt $keyDeadline) {
    if (Test-Path $keyFile) {
        $key = (Get-Content $keyFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($key.Length -eq 64) { break }
    }
    Start-Sleep -Milliseconds 200
}
if ($key.Length -ne 64) {
    Write-Host "没能取到密钥（$KeyTimeoutSec 秒内没有 64 字符内容），检查游戏是否走到预加载开库。" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "KEY = $key" -ForegroundColor Cyan
Write-Host "已写入 $keyFile"

if (-not $DbPath) { $DbPath = Join-Path $repoRoot "work\db\ExcelDB.db" }
if (-not (Test-Path $DbPath)) {
    Write-Host "跳过校验：找不到 $DbPath（可用 -DbPath 指定库路径）。" -ForegroundColor Yellow
    exit 0
}

$verifyCode = @"
from batr.db import connect, list_tables
con = connect(r'''$DbPath''', "$key")
print(len(list_tables(con)))
"@
Push-Location $repoRoot
try {
    $out = & uv run python -c $verifyCode 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "校验通过：密钥可打开 $DbPath（$($out | Select-Object -Last 1) 张表）。" -ForegroundColor Green
    }
    else {
        Write-Host "校验失败：密钥打不开 $DbPath。" -ForegroundColor Red
        $out | ForEach-Object { Write-Host "  $_" }
    }
}
finally {
    Pop-Location
}
