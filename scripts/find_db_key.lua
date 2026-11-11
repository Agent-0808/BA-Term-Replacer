--[[
    拦截 ExcelDB.db 的 SQLCipher 密钥（Cheat Engine 7.6，需以管理员运行）

    用法：
      1. 管理员 pwsh 先跑 scripts/suspend_until_gameassembly.ps1，再从 Steam 启动游戏
      2. CE（管理员）→ Open Process → BlueArchive.exe
      3. Table → Show Cheat Table Lua Script，载入本文件后点 Execute
      4. 回到 ps1 窗口按回车放行，游戏预加载开库时命中，这里打印 KEY = ...

    说明：
      特征码命中点 +0x0F 是 `mov rbx, rax`。硬件执行断点在指令执行前触发，
      此刻 RAX 才是 hex 串（IL2CPP String 对象），RBX 尚未写入。
      String 布局：字符数在 +0x10，UTF-16LE 字符从 +0x14 起。
]]

local aob = "31 D2 E8 ?? ?? ?? ?? 48 89 C2 E8 ?? ?? ?? ?? 48 89 C3 48 8B 05 ?? ?? ?? ?? 48 8B 80 B8 00 00 00 48 8B 50 20"

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
    debug_removeBreakpoint(bp)
    return 0
end

debugProcess()
debug_setBreakpoint(bp, 1, bptExecute, bpmDebugRegister)
print("断点已下好，回 ps1 窗口按回车放行")
