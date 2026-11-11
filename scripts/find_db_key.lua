--[[
    拦截 ExcelDB.db 的 SQLCipher 密钥（Cheat Engine 7.6，需以管理员运行）

    配合 scripts/suspend_until_gameassembly.ps1 -AutoContinue 使用：
      1. 管理员 pwsh 跑上面的 ps1（它会先冻结游戏、等断点就绪）
      2. 从 Steam 启动游戏，CE（管理员）→ Table → Show Cheat Table Lua Script，载入本文件后 Execute
      3. 本脚本沿用已 attach 的进程（没 attach 时会试着打开，CE 可能弹进程列表让你选），
         扫特征码、下硬件断点，然后写标记让 ps1 自动放行
      4. 断点命中后把密钥写进 %LOCALAPPDATA%\batr\db_key.txt，ps1 会自动校验

    说明：
      特征码命中点 +0x0F 是 `mov rbx, rax`。硬件执行断点在指令执行前触发，
      此刻 RAX 才是 hex 串（IL2CPP String 对象），RBX 尚未写入。
      String 布局：字符数在 +0x10，UTF-16LE 字符从 +0x14 起。
]]

local aob = "31 D2 E8 ?? ?? ?? ?? 48 89 C2 E8 ?? ?? ?? ?? 48 89 C3 48 8B 05 ?? ?? ?? ?? 48 8B 80 B8 00 00 00 48 8B 50 20"

-- 与 ps1 约定的握手目录（两边都取 %LOCALAPPDATA%\batr）
local workDir = (os.getenv("LOCALAPPDATA") or ".") .. "\\batr"
local readyPath = workDir .. "\\.key_hook_ready"
local keyPath = workDir .. "\\db_key.txt"
pcall(function() os.execute('mkdir "' .. workDir .. '" 2>nul') end)

local function writeFile(path, text)
    local f = io.open(path, "w")
    if not f then
        print("写入失败：" .. path)
        return false
    end
    f:write(text)
    f:close()
    return true
end

local TARGET = "BlueArchive.exe"

-- 已 attach 就直接用；没 attach 才尝试按名字打开（CE 通常会把进程列表弹出来让你选）
if not getOpenedProcessID() or getOpenedProcessID() == 0 then
    print("正在连接 " .. TARGET .. "（若 CE 弹出进程列表，请选中它）...")
    pcall(function() openProcess(TARGET) end)
    local waited = 0
    while (not getOpenedProcessID() or getOpenedProcessID() == 0) and waited < 30000 do
        sleep(200)
        waited = waited + 200
    end
end

local pid = getOpenedProcessID()
if not pid or pid == 0 then
    print("未连接进程：请在 CE 里 Open Process 选 " .. TARGET .. "，再重新 Execute 本脚本")
    return
end
print(string.format("已连接 PID=%X", pid))

local tries = 0
while not getAddress("GameAssembly.dll") and tries < 100 do
    sleep(100)
    tries = tries + 1
end
if not getAddress("GameAssembly.dll") then
    print("当前进程里没有 GameAssembly.dll：确认 attach 的是 " .. TARGET)
    return
end

local hit = AOBScanModuleUnique("GameAssembly.dll", aob)
if not hit then
    print("AOB 未命中：确认 attach 的是 BlueArchive.exe，且该版本未改版（改版走 PRAGMA key 字符串法）")
    return
end

-- 当前版本 hit 的 RVA 固定为 0x1BFC38F，只在拿不到模块符号时兜底用
local base = getAddress("GameAssembly.dll") or (hit - 0x1BFC38F)
local bp = hit + 0xF
print(string.format("基址=%X  hit=%X  断点=%X", base, hit, bp))

function debugger_onBreakpoint()
    local n = readInteger(RAX + 0x10)
    local key = readString(RAX + 0x14, n * 2, true)
    print("KEY = " .. key)
    writeFile(keyPath, key)
    debug_removeBreakpoint(bp)
    return 0
end

debugProcess()
debug_setBreakpoint(bp, 1, bptExecute, bpmDebugRegister)

-- 断点就绪：通知 ps1 放行
if writeFile(readyPath, "1") then
    print("断点已下好，ps1 会自动放行；命中后密钥写到 " .. keyPath)
else
    print("断点已下好，但标记文件写入失败，请回 ps1 窗口手动按回车"
        .. "（检查目录是否存在：" .. workDir .. "）")
end
