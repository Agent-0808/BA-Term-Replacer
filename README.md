# BA-Term-Replacer · 蔚蓝档案国际服繁體 → 简体 / 译名替换工具

把**国际服（Global / 繁中）客户端**的界面与剧情文本就地改成**简体中文**。
输入一个 `ExcelDB.db`，输出另一个**可直接使用**的 `ExcelDB.db` —— 不改 catalog、不碰设备。

- ✅ **不需要 root**、不重签 APK、不碰服务器
- ✅ **不再需要改 `TableCatalog.bytes`**：输出库的 CRC32 与原库完全一致（末尾追加 4 字节修正），客户端校验自然通过
- ✅ **输入文件永不修改**，原版始终在你手上
- ✅ 结构零风险：只在 FlatBuffer 内做**等长字节替换**

> 仅适用于 **GL（国际服，繁中）**。日服/韩服/国服的库和文本表不同，不通用。

| 改之前 | 改之后 |
|---|---|
| ![before](docs/before.jpg) | ![docs/after.jpg](docs/after.jpg) |

---

## 快速开始（需要 [uv](https://docs.astral.sh/uv/)）

```bash
uv sync

# 只看会改什么，不写任何文件
uv run batr ExcelDB.db --dry-run

# 转换 + CRC 修正，产出可直接使用的库（省略 --out 时写到 output/ExcelDB.db）
uv run batr ExcelDB.db --out output/ExcelDB.cn.db --verify
```

把 `db` 换成你从设备拉出的 `ExcelDB.db`（放在 `/sdcard/Android/data/com.nexon.bluearchive/files/PUB/Resource/Preload/TableBundles/`），
完成后把 `--out` 的产物放回同一路径即可。`--verify` 会对输出跑 `PRAGMA integrity_check`。

### 命令一览

```
batr <db>   字段级文本补丁（支持变长替换）+ CRC 追加修正
  db                输入 ExcelDB.db（位置参数，不会被修改）
  --out <文件>       输出库（CRC32 与输入一致；默认 output/<输入文件名>）
  --convert <模式>   tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形，
                     none 只做替换表（默认 tw2sp）
  --convert-kana     不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）
  --tables <正则>    限定要处理的表（默认 Localize|Dialog|Scenario|...）
  --extra-bytes HEX  CRC 修正前附加到输出末尾的自定义字节（hex，如 DEADBEEF）
  --names TSV...     角色名表（exact 整字段匹配），默认 glossary/names.tsv，空格分隔可传多个
  --text TSV...      正文替换表（sub 子串匹配），默认 glossary/text.tsv，空格分隔可传多个
  --key <hex>        覆盖 SQLCipher 密钥（游戏换密钥时用）
  --dry-run          只统计，不写任何文件
  --verify           输出库跑 integrity_check
```

### 繁中 → 繁中民译（只换译名，不转简体）

`--convert none` 关闭字形转换、只套词表，产物仍是繁体：

```bash
# 先预览：逐规则 hits=0 的条目多半是键写错或词条过期
uv run batr ExcelDB.db --convert none \
  --names glossary/names_custom.tsv --text glossary/text_custom.tsv --dry-run

# 正式产出
uv run batr ExcelDB.db --convert none \
  --names glossary/names_custom.tsv --text glossary/text_custom.tsv --out output/ExcelDB.tw.db
```

务必显式传 `--names` / `--text`：默认的 `glossary/names.tsv` / `text.tsv`（及 `.local` 变体）值是简体，不覆盖会把文本转成简体。

词表（`glossary/` 自动产物与个人词表不入库；仅 `blacklist.txt`（客观禁用）与 `terms.tsv`（通用专名）跟踪）：

```bash
uv run python scripts/make_kivowiki_names.py   # names.tsv / text.tsv：kivowiki 古书馆民译（繁->简流程用）
uv run python scripts/make_name_template.py    # names_custom.tsv / text_custom.tsv：繁->繁模板，右列自己填
```

- `names.tsv` / `text.tsv` 是**纯自动产物，每次完整重新生成**，不含任何手工内容，不要直接编辑。个人补充/修正写 `glossary/names.local.tsv` / `glossary/text.local.tsv`（本地、不入库，首次运行自动建空模板）；CLI 默认把它们排在自动表**之前**加载，重复键以先出现的为准，即个人条目优先。
- 禁用某个自动键写黑名单：`glossary/blacklist.local.txt`（个人、不入库，首次运行自动建模板）或 `glossary/blacklist.txt`（客观、入库）。默认两表都排除；写第二列可限定生效表：`希望<TAB>text` = 角色名表照常生成、正文子串替换跳过（防止误伤普通词），`键<TAB>names` 反之。
- `glossary/terms.tsv`（入库共享）放地名/组织/术语的社区通用民译（如 `奇普托斯<TAB>基沃托斯`），只做 sub 匹配；文件存在时 CLI **始终自动加载**，个人表同名键优先。
- `names_custom.tsv` 是恒等行模板（`彌香<TAB>彌香`），右列与左列相同 = 未填写，加载时自动跳过，不会产生任何替换。
- 键必须写数据库里的**繁体原文**，分隔符是 Tab 不是空格；值写译文即可（繁->繁用繁体，繁->简流程最终由 OpenCC 转简体）。

### 可选：adb 一键脚本（不保证维护）

`scripts/legacy/运行.bat` / `scripts/legacy/localize_phone.ps1` / `scripts/legacy/localize_phone.sh`：
自动「停游戏 → 拉库（备份到 work/）→ `batr patch` → 推回」，需要 uv 和 adb。
主路径完全不依赖 adb —— 手动放文件即可。

---

## 它到底做了什么

游戏的表数据放在 **SQLCipher 加密**的 `ExcelDB.db` 里（约 330 MB、424 张表）。
每张表是 `(Key INTEGER, Bytes BLOB)`，`Bytes` 是装着整表数据的 **FlatBuffer**。

1. 用密钥打开库，在每行 blob 内做**等长字节替换**：繁→简几乎都是 3 字节 UTF-8 汉字互换
   （`學園→学园`、`檔案→档案`）。**长度不变 ⇒ FlatBuffer 的所有偏移字段保持有效 ⇒ 结构零风险。**
2. 转换完成后，在输出文件**末尾追加 4 字节**，使整体 CRC32 与输入完全一致
   （标准 CRC32 可逆构造，见 `src/batr/crc.py`）。GL 的 `TableCatalog.bytes` 只记录
   CRC32、不记录文件大小，因此客户端校验必然通过 —— **catalog 完全不用动**。

实测（与旧版等长转换完全一致）：**267,036 行 / 1,775,029 字**；输出 CRC `C3F4D218` == 输入；
`PRAGMA integrity_check` = ok。

技术细节与踩坑记录见 [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)。

---

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| 打不开数据库（wrong key） | 游戏大版本更新换了密钥 → `--key` 覆盖 |
| 转换完少数词仍是台式 | 词库覆盖面问题，欢迎 PR 补词（改 `src/batr/data/`） |
| 某些字大小/粗细不统一 | 用 [BA-Font-Replacer](https://github.com/Agent-0808/BA-Font-Replacer) 替换字体即可，详见 [docs/字体问题.md](docs/字体问题.md) |
| 进游戏又变回繁体了 | 点了游戏内「资源修复 / 重新下载」→ 重新执行即可 |
| 游戏更新后要重跑 | 库变了 → 重新拉取并跑 `batr patch`（对输出 CRC 自动对齐新库） |

---

## 目录结构

```
.
├── pyproject.toml            uv 项目定义（依赖、batr 命令入口）
├── src/batr/
│   ├── cli.py                命令行入口（patch / crc-fix）
│   ├── patch.py              遍历库 → 等长转换 → CRC 修正 → 自校验
│   ├── convert.py            繁简映射（OpenCC 词库，纯 Python）
│   ├── db.py                 SQLCipher 打开 / 遍历
│   ├── utils/crc.py          CRC32 追加修正（来自 BAMT，GPL-3.0；替代旧的 catalog 改写）
│   ├── config.py             默认密钥、表过滤等
│   └── data/                 OpenCC 词库（Apache-2.0）
├── scripts/                  词表生成脚本（make_kivowiki_names / make_name_template）
│   └── legacy/               从旧项目继承，已弃用的脚本
├── docs/                     原理、字体问题
└── tests/                    pytest（CRC 已知向量、转换样例、端到端）
```

---

## English summary

Convert the **Blue Archive Global (Traditional Chinese)** client's UI and story text to
**Simplified Chinese**. Input: an `ExcelDB.db` pulled from the device; output: another
`ExcelDB.db` usable as-is — no catalog rewriting needed.

The game keeps its tables in a SQLCipher-encrypted SQLite database; each row is
`(key, Bytes)` where `Bytes` is a FlatBuffer. The tool performs **equal-length UTF-8
byte substitution** inside those blobs (Traditional→Simplified is almost always a 3-byte
CJK swap), so every FlatBuffer offset stays valid. It then **appends 4 bytes** so the
whole file's CRC32 matches the original — the GL `TableCatalog.bytes` records only a
CRC (no size), so the client's integrity check passes untouched.

```bash
uv sync
uv run batr patch --db ExcelDB.db --out ExcelDB.cn.db --verify
```

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12+, dependency: `sqlcipher3-wheels`).
Re-run after each game update. Deprecated adb helpers live in `scripts/legacy/`.

---

## 署名与第三方组件

本工具基于原项目 [alisns1/blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified)
（**MIT**，许可证全文见 [licenses/blue-archive-gl-simplified-LICENSE.txt](licenses/blue-archive-gl-simplified-LICENSE.txt)）
现代化重构而来 —— 致谢原作者与所有贡献者。

本项目站在社区成果之上，逐项署名见 **[THIRD_PARTY.md](THIRD_PARTY.md)**：

| 来源 | 许可证 | 用在哪 |
|---|---|---|
| [alisns1/blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified)（原项目） | **MIT** | 本仓库的前身（等长替换思路与初始实现） |
| [OpenCC](https://github.com/BYVoid/OpenCC) | **Apache-2.0** | `src/batr/data/` 下 3 个词库文件（原样复制） |
| [BA-Modding-Toolkit（BAMT）](https://github.com/Agent-0808/BA-Modding-Toolkit) | **GPL-3.0** | `src/batr/utils/crc.py`（CRC32 追加修正，替代旧的 catalog 改写） |
| BlueArchive-Tools / BlueArchive-Tools-CLI（delayboy 系） | AGPL-3.0 | 仅作 SQLCipher 参数的**参考**；**本仓库不含其任何代码** |
| 社区所有做国际服/日服汉化的朋友 | — | 思路与经验 |

> **声明**：本仓库不含任何游戏素材。密钥 `ef0aaca0…` 是社区公开流传的**数据值**，
> 作为可覆盖的默认值提供（`--key` / `BA_KEY`）。

## License

本仓库：**GPL-3.0**（见 [LICENSE](LICENSE)）—— 因包含来自 BAMT（GPL-3.0）的
[src/batr/utils/crc.py](src/batr/utils/crc.py)，全仓库统一按 GPL-3.0 分发。
原项目 [alisns1/blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified) 的 MIT
许可证全文保留于 [licenses/](licenses/)。
`src/batr/data/` 下的 OpenCC 词库：**Apache-2.0**（见 [src/batr/data/LICENSE-OpenCC.txt](src/batr/data/LICENSE-OpenCC.txt)）。
其余第三方署名见 [THIRD_PARTY.md](THIRD_PARTY.md)。

---

## 字体观感问题

汉化后**被改动过的字**可能比繁简同形的字看起来更细或更小（根因分析见[docs/字体问题.md](docs/字体问题.md)）。

**已解决**：使用 [BA-Font-Replacer](https://github.com/Agent-0808/BA-Font-Replacer)
把客户端的繁体字体（TW 字体）替换为**思源黑体 SC 的 Medium 与 Bold** 两个字重即可，
简体字形将全部由同一款字体渲染，观感完全统一。

---

## 免责声明 / Disclaimer

This project is intended solely for educational and demonstrative purposes and does not provide any actual resources. Please note that all content downloaded through this project should only be used for legal and legitimate purposes. The developers are not liable for any direct or indirect loss, damage, legal liability, or other consequences that may arise from the use of this project. Users assume all risks associated with the use of this project and must ensure compliance with all relevant laws and regulations. If anyone uses this project for any unauthorized or illegal activities, the developers bear no responsibility. Users are responsible for their own actions and should understand the risks involved in using this project.

"Blue Archive" is a registered trademark of NEXON Korea Corp. & NEXON GAMES Co., Ltd. All rights reserved.

该仓库仅供学习和展示用途，不托管任何实际资源。请注意，所有通过本项目下载的内容均应仅用于合法和正当的目的。开发者不对任何人因使用本项目而可能引发的直接或间接的损失、损害、法律责任或其他后果承担任何责任。用户在使用本项目时需自行承担风险，并确保遵守所有相关法律法规。如果有人使用本项目从事任何未经授权或非法的活动，开发者对此不承担任何责任。用户应对自身的行为负责，并了解使用本项目可能带来的任何风险。

“蔚蓝档案”是上海星啸网络科技有限公司的注册商标，版权所有。

「ブルーアーカイブ」は株式会社Yostarの登録商標です。著作権はすべて保有されています。
