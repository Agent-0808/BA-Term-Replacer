<#
.SYNOPSIS
    等 BlueArchive.exe 加载 GameAssembly.dll 后立刻挂起进程，给 CE 留出 attach + 下断点的时间。

.DESCRIPTION
    游戏的 ExcelDB.db 在启动预加载阶段很快就打开，手动 attach 常常来不及。
    本脚本轮询进程与模块，一旦 GameAssembly.dll 映射进内存就 NtSuspendProcess 冻结整个进程；
    你在 CE 里 attach、扫 AOB、下硬件断点完成后，回到本窗口按回车放行即可。

.EXAMPLE
    pwsh -File .trae/temp/suspend_until_gameassembly.ps1
    然后从 Steam 启动游戏（或双击 BlueArchive.exe）。
#>
param(
    [string]$ProcessName = "BlueArchive",
    [string]$ModuleName  = "GameAssembly.dll",
    [int]$TimeoutSec     = 300
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
Read-Host "全部下好之后，回到这里按回车放行"
[Native.ProcApi]::NtResumeProcess($h) | Out-Null
Write-Host "已放行，等断点命中。" -ForegroundColor Green
