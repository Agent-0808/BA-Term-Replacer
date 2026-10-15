# 蔚蓝档案 国际服（Blue Archive GL）繁體 → 简体 本地汉化

把**国际服（Global / 繁中）客户端**的界面与剧情文本就地改成**简体中文**。

- ✅ **不需要 root**（`adb push` 到 `/sdcard/Android/data/...` 即可）
- ✅ **不需要重签 APK**、不需要 Magisk 模块、不碰服务器
- ✅ 改的是**本地显示文本**，不动账号、存档、网络请求
- ✅ 手机和模拟器都能用，Windows / Linux / macOS 都有脚本

> 仅适用于 **GL（国际服，繁中）**。日服/韩服/国服的库和文本表不同，不通用。

| 改之前 | 改之后 |
|---|---|
| ![before](docs/before.jpg) | ![after](docs/after.jpg) |

（左：`任務 / 學生 / 咖啡廳 / 活動進行中`；右：`任务 / 学生 / 咖啡厅 / 活动进行中`）

---

## 快速开始

### 0. 准备

```bash
pip install -r requirements.txt      # 只需要 sqlcipher3-wheels
```

另外需要 **adb**（Android platform-tools）在 PATH 里，手机打开「开发者选项 → USB 调试」。

### 1. Windows

```
双击 运行.bat
```

或者：

```powershell
.\localize_phone.ps1                 # 自动选设备
.\localize_phone.ps1 -Serial <序列号>
.\localize_phone.ps1 -DryRun         # 只转换不推送
```

### 2. Linux / macOS / WSL

```bash
chmod +x localize_phone.sh
./localize_phone.sh                  # 自动选设备
./localize_phone.sh <serial>
DRY_RUN=1 ./localize_phone.sh
```

### 3. 完事

脚本会自动：**停游戏 → 从手机拉出原文件（保留备份）→ 繁转简 → 重算 catalog 的 CRC32 → 推回手机**。
然后打开游戏，界面/剧情就是简体了。

**游戏每次大版本更新后重跑一次即可**（库会变）。

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
