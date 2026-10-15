# 蔚蓝档案 国际服（Blue Archive GL）繁體 → 简体 本地汉化

把**国际服（Global / 繁中）客户端**的界面与剧情文本就地改成**简体中文**。

- ✅ **不需要 root**（`adb push` 到 `/sdcard/Android/data/...` 即可）
- ✅ **不需要重签 APK**、不需要 Magisk 模块、不碰服务器
- ✅ 改的是**本地显示文本**，不动账号、存档、网络请求
- ✅ **主要给真机（手机）用**；MuMu / LDPlayer 等模拟器也能用（方便测试）
- ✅ Windows / Linux / macOS 都有脚本

> 仅适用于 **GL（国际服，繁中）**。日服/韩服/国服的库和文本表不同，不通用。

| 改之前 | 改之后 |
|---|---|
| ![before](docs/before.jpg) | ![after](docs/after.jpg) |

（左：`任務 / 學生 / 咖啡廳 / 活動進行中`；右：`任务 / 学生 / 咖啡厅 / 活动进行中`）

---

## 快速开始

### 一次性准备（只做一次）

**① 装 Python（3.9 或更高）**

到 https://www.python.org/downloads/ 下载安装，**务必勾选 `Add python.exe to PATH`**。

**② 准备 adb（大概率不用装）**

脚本按这个顺序找 adb，找到一个就用：

1. 环境变量 `ADB`（你自己指定路径）
2. PATH 里的 `adb`
3. **模拟器自带的 adb** —— 装了 MuMu / LDPlayer / 夜神 / BlueStacks 就直接用它的，**不用额外装**
   （例如 MuMu 的就在 `...\Netease\MuMu\nx_main\adb.exe`）

如果上面都没有（比如你只用真机、没装模拟器），再去装：

1. 下载 [platform-tools](https://developer.android.com/tools/releases/platform-tools)，解压到例如 `C:\platform-tools`
2. 把这个目录加进系统 PATH
   （Win 搜索「环境变量」→ 编辑系统环境变量 → 环境变量 → Path → 新建 → 填目录）
3. **新开**一个 PowerShell 窗口验证：

   ```powershell
   adb version
   ```

   能打印出版本号就对了。

**③ 装依赖**（在仓库目录里跑一次）

```powershell
cd <仓库目录>
pip install -r requirements.txt
```

**④ 手机开启 USB 调试**

设置 → 关于手机 → **连点「版本号」7 次**（提示"你已处于开发者模式"）
→ 返回设置 → 系统 → **开发者选项** → 打开 **USB 调试**。

### 每次汉化（游戏更新后重跑）

| 步骤 | 操作 |
|---|---|
| 1 | 手机用 **USB 数据线**连电脑（有些线只能充电，认不到设备就换一根） |
| 2 | 手机弹出「**允许 USB 调试吗？**」→ 点**允许**（建议勾"一律允许"） |
| 3 | **关掉手机上的游戏**（开着会占用要替换的文件） |
| 4 | 双击仓库里的 **`运行.bat`** |
| 5 | 等 1–3 分钟（脚本会逐步打印 `[ok]`） |
| 6 | 打开游戏 → 界面和剧情就是简体了 |

脚本内部自动完成：

```
停游戏 → 从手机拉出原文件（备份到 work/） → 繁转简 → 重算 catalog 的 CRC32 → 推回手机
```

**游戏每次大版本更新后重跑一遍即可。** 重复运行是安全的（已转换过的内容不会被二次转换）。

### 命令行用法

Windows：

```powershell
.\localize_phone.ps1                  # 自动选设备（优先挑非模拟器）
.\localize_phone.ps1 -Serial <序列号>  # 多台设备时指定
.\localize_phone.ps1 -DryRun          # 只拉取 + 转换 + 改 catalog，不推送
.\localize_phone.ps1 -Key <64位hex>   # 指定密钥
```

Linux / macOS / WSL：

```bash
chmod +x localize_phone.sh
./localize_phone.sh                   # 自动选设备
./localize_phone.sh <serial>
DRY_RUN=1 ./localize_phone.sh
BA_KEY=<64位hex> ./localize_phone.sh
```

### 先确认设备连上了

```powershell
adb devices
```

输出里要看到 `XXXXXXXX	device`。
如果是 `unauthorized` → 手机上重新点一次"允许 USB 调试"；
如果是 `offline` → 拔插一次数据线。

---

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| `adb not found` / 不是内部或外部命令 | platform-tools 没加进 PATH，或装完没重开窗口 |
| `no device` / 设备列表为空 | USB 调试没开；没点"允许"；数据线只能充电（换线）；换个 USB 口 |
| `unauthorized` | 手机上重新点「允许 USB 调试」；或在开发者选项里"撤销 USB 调试授权"后重插 |
| 卡在 `pull` 很久 | 手机锁屏了 → 保持解锁；或换 USB 3.0 口（330 MB 正常约 10 秒） |
| `wrong key` / 打不开数据库 | 游戏大版本更新换了密钥 → 提 Issue 并说明游戏版本号 |
| `catalog patch failed` | 游戏改了 catalog 格式 → 提 Issue 并附上你的 `TableCatalog.bytes` |
| 进游戏又变回繁体了 | 你点了游戏内「资源修复 / 重新下载」→ 重跑 `运行.bat` 即可 |
| 手机重启后连不上 | adb 授权会掉，重新插线点一次"允许" |
| 只想先试不想推送 | 用命令行跑 `.\localize_phone.ps1 -DryRun` |
| 能在模拟器上用吗 | 能（MuMu / LDPlayer 等都能推）。**本工具主要面向真机手机**，模拟器适合先试；同时连着手机和模拟器时脚本会**优先选真机**，要指定就加 `-Serial <序列号>` |
| 转换完界面正常但少数词仍是台式 | 词库覆盖面问题，欢迎 PR 补词（改 `dict/` 或提 Issue 给具体词条） |

---

## 它到底做了什么

游戏的表数据放在一个 **SQLCipher 加密的 SQLite 库** `ExcelDB.db` 里（约 330 MB、424 张表）。
每张表是 `(Key INTEGER, Bytes BLOB)`，`Bytes` 是装着整表数据的 **FlatBuffer**。

脚本做三件事：

1. 用密钥打开这个库（SQLCipher 参数见 [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)）
2. 在每行 blob 内部做**等长字节替换**：繁→简几乎都是 3 字节 UTF-8 汉字互换（`學園→学院`、`檔案→档案`）。
   **长度不变 ⇒ FlatBuffer 的所有偏移字段保持有效 ⇒ 结构零风险。**
3. 把 `TableCatalog.bytes` 里 `ExcelDB.db` 那条的 **CRC32** 改成新库的值 —— 客户端按本地 catalog 校验，于是校验通过、不会触发重新下载。

实测转换量：**267,036 行 / 1,775,029 字**。

技术细节、踩过的坑、SQLCipher 参数、catalog 二进制布局都在
👉 [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)

---

## 注意

1. **游戏更新后要重跑**：库变了，catalog 的 CRC 也变了
2. **不要点游戏里的「资源修复 / 重新下载」**：会把原文件覆盖回去，重跑脚本即可
3. 脚本只改本地**文本**。严格来说修改客户端文件违反游戏用户协议，**风险请自行评估**
4. 请自行保留备份（脚本会把原文件存到 `work/`）

---

## 目录结构

```
.
├── localize_phone.ps1        Windows 一键脚本
├── localize_phone.sh         Linux / macOS / WSL 一键脚本
├── 运行.bat                  Windows 双击入口
├── tools/
│   ├── patch_db.py           繁→简（打开加密库、逐 blob 等长替换）
│   ├── patch_catalog.py      改 catalog 里的 CRC32
│   └── t2s.py                繁简映射（OpenCC 词库，纯 Python）
├── dict/                     OpenCC 词库（Apache-2.0）
├── docs/HOW_IT_WORKS.md      原理与踩坑记录
└── requirements.txt
```

---

## English summary

Convert the **Blue Archive Global (Traditional Chinese)** client's UI and story text to
**Simplified Chinese** by patching two local files on the device — no root, no APK
re-signing, no server interaction.

The game keeps its tables in a SQLCipher-encrypted SQLite database (`ExcelDB.db`); each row
is `(key, Bytes)` where `Bytes` is a FlatBuffer. The script performs **equal-length UTF-8
byte substitution** inside those blobs (Traditional→Simplified is almost always a 3-byte
CJK swap), so every FlatBuffer offset stays valid, then rewrites the CRC32 recorded in
`TableCatalog.bytes` so the client's integrity check still passes.

Requires `adb` + `sqlcipher3-wheels`. Re-run after each game update.

See [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) for the reverse-engineered details
(SQLCipher parameters, the HMAC key-length gotcha, the catalog binary layout).

---

## 署名与第三方组件

本项目站在社区成果之上，逐项署名见 **[THIRD_PARTY.md](THIRD_PARTY.md)**：

| 来源 | 许可证 | 用在哪 |
|---|---|---|
| [OpenCC](https://github.com/BYVoid/OpenCC) | **Apache-2.0** | `dict/` 下 3 个词库文件（原样复制，许可证全文见 [`dict/LICENSE-OpenCC.txt`](dict/LICENSE-OpenCC.txt)） |
| [asfu222/BlueArchiveLocalizationTools](https://github.com/asfu222/BlueArchiveLocalizationTools) | **MIT** | `TableCatalog.bytes` 的条目字段布局（`tools/patch_catalog.py` 为独立实现） |
| BlueArchive-Tools / BlueArchive-Tools-CLI（delayboy 系） | AGPL-3.0 | 仅作 SQLCipher 参数的**参考**；**本仓库不含其任何代码** |
| [headless-bluearchive / SDK](https://github.com/) | MIT | `Excel.zip` 口令推导（纯分析，未收录） |
| 社区所有做国际服/日服汉化的朋友 | — | 思路与经验 |

> **声明**：本仓库不含任何游戏素材。密钥 `ef0aaca0…` 是社区公开流传的**数据值**，
> 作为可覆盖的默认值提供（`--key` / `BA_KEY`）。

## License

本仓库自有代码：**MIT**（见 [LICENSE](LICENSE)）。
`dict/` 下的 OpenCC 词库：**Apache-2.0**（见 [dict/LICENSE-OpenCC.txt](dict/LICENSE-OpenCC.txt)）。
其余第三方署名见 [THIRD_PARTY.md](THIRD_PARTY.md)。
