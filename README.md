<div align="center" style="text-align:center">
  <h1>BA-Term-Replacer</h1>
  <p>
    蔚蓝档案国际服 - 繁體→简体本地化 / 自定义译名替换工具
  </p>
    <a href="https://www.gnu.org/licenses/gpl-3.0"><img alt="License: GPLv3" src="https://img.shields.io/badge/License-GPL--3.0-orange?style=for-the-badge"></a>
    <img alt="Blue Archive Global" src="https://img.shields.io/badge/Blue%20Archive-Global-blue?style=for-the-badge">
  </p>
</div>

把国际服（Global / 繁中）客户端的界面与剧情文本本地化为简体中文；或套用自制的繁体民译词表，保持繁体。
输入一个 `ExcelDB.db`，输出另一个可直接使用的 `ExcelDB.db`。

> 仅适用于 **国际服繁中**。

| 改之前 | 改之后 |
|---|---|
| ![before](docs/before.jpg) | ![docs/after.jpg](docs/after.jpg) |

---

## 安装

- 需要 [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/Agent-0808/BA-Term-Replacer.git
cd BA-Term-Replacer
uv sync
```

PC 端支持自动定位 Steam 客户端的 `ExcelDB.db` 文件，`uv run batr paths` 可查看检测结果；

## 详细使用教程

两种主要用途：
- **繁→简**（kivowiki 民译词表 + OpenCC 字形转换）
- **繁→繁民译**（不转字形，纯词表，自己写译文）

差别只在词表来源和 `--convert` 参数，命令骨架相同。

### 1. 获取词表

`glossary/` 里入库共享的只有 `blacklist.txt`（客观禁用项）与 `terms.tsv`（通用专名），词表本体需要本地生成：

```bash
uv run batr glossary             # 繁→简用：names.tsv（角色名）+ text.tsv（正文），kivowiki 古书馆民译
uv run batr glossary --template  # 繁→繁用：names_custom.tsv 恒等行模板 + text_custom.tsv 空表
```

- 自动表自动拉取民译数据（缓存于 `work/students.json`，`--refresh` 强制重新下载），生成后繁→简流程即可直接使用。
- `--template` 生成的 `names_custom.tsv` 每行都是恒等行（如`彌香<TAB>彌香`），把右列改成你要的繁体译名即生效；没改的行加载时自动跳过，不会产生替换。`text_custom.tsv` 需要手写（地名/术语等）。

### 2. 修改词表

| 想要修改 | 修改文件 |
|---|---|
| 写自己的角色名译名（繁→繁） | `names_custom.tsv`（改恒等行右列） |
| 补充/修正译名（繁→简） | `names.local.tsv` / `text.local.tsv`（首次运行自动生成空模板，优先级最高） |
| 地名/组织/术语 | `terms.tsv`（入库共享，CLI 始终自动加载） |
| 禁用某个自动词条 | `blacklist.local.txt`（个人喜好）或 `blacklist.txt`（入库共享） |

注意：

- `names.tsv` / `text.tsv` 是纯自动产物，每次重新生成都会被完整重写，不要直接编辑；个人内容一律写 `.local` 文件（重复键以先加载的为准，个人条目优先于自动表）。
- 分隔符是 **Tab** 不是空格；键必须是数据库里的繁体原文；值写译文（繁→繁写繁体；繁→简可以简体或繁体，还会通过 OpenCC 转成简体）。
- 黑名单可加第二列限定生效表：`希望<TAB>text` = 角色名照常生成、正文子串替换跳过（避免误伤普通词），`键<TAB>names` 反之。
- 皮肤名在 text 表里带括号生成（`(單車) → (骑行服)`），只命中 `白子(單車)` 这类复合串，不会动正文里的「單車」。

### 3. 运行命令

#### **繁→简**
默认：tw2sp + 自动词表 + terms.tsv

```bash
uv run batr patch --dry-run                                  # 预演：逐规则打印命中数，hits=0 多半是键写错
uv run batr patch --out output/ExcelDB.cn.db --verify        # 正式产出（CRC32 与输入一致）
```

#### **繁→繁民译**
`--convert none` 关闭字形转换；务必显式传 custom 表——默认加载的 names.tsv/text.tsv 值是简体，不覆盖会把文本转成简体：

```bash
uv run batr patch --convert none \
  --names glossary/names_custom.tsv --text glossary/text_custom.tsv --dry-run

uv run batr patch --convert none \
  --names glossary/names_custom.tsv --text glossary/text_custom.tsv \
  --out output/ExcelDB.tw.db
```

PC 端完成后 `uv run batr patch --install` 可直接覆盖安装到游戏目录（覆盖前自动备份原库为 `.bak`）；
移动端把输出产物放回设备原路径。游戏内点了「资源修复 / 重新下载」才需要重跑。
替换没生效、译名不对时，用 `uv run batr scan` 做字段级排查，完整参数与排查路径见 [docs/脚本用法说明.md](docs/脚本用法说明.md)。

### 命令一览

```
uv run batr -h
```


```
batr <子命令>
  patch      字段级文本补丁（支持变长替换）+ CRC 追加修正，--install 覆盖安装到游戏目录
  scan       字段级扫描（调试）：关键词定位 / 两库对比 / 未覆盖表清单
  export     把目标表的文本字段导出成每表一个 TSV
  glossary   词表生成：自动表（默认）或自制模板（--template）
  paths      显示检测到的游戏安装路径与 ExcelDB.db 路径

patch 常用参数（其余子命令见 -h）：
  --db <文件>        输入 ExcelDB.db（不会被修改；省略则自动定位游戏安装路径）
  --out <文件>       输出库（CRC32 与输入一致；默认 output/<输入文件名>）
  --convert <模式>   tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形，
                     none 只做替换表（默认 tw2sp）
  --convert-kana     不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）
  --tables <正则>    限定要处理的表（默认 Localize|Dialog|Scenario|...）
  --extra-bytes HEX  CRC 修正前附加到输出末尾的自定义字节（hex，如 DEADBEEF）
  --names TSV...     角色名表（exact 整字段匹配），默认 names.local.tsv + names.tsv（.local 优先）
  --text TSV...      正文替换表（sub 子串匹配），默认 text.local.tsv + text.tsv + terms.tsv
  --no-ascii-exact   关闭纯 ASCII 字段的 exact 匹配（默认开启，覆盖 "Kei" 这类拉丁角色名）
  --key <hex>        覆盖 SQLCipher 密钥（游戏换密钥时用）
  --dry-run          只统计，不写任何文件
  --verify           输出后进行 integrity_check
  --region <区服>    自动定位用的区服（auto = global 优先，japan 兜底）
  --install          补丁成功后覆盖安装到游戏目录（覆盖前备份 .bak，交互确认）
  --yes              覆盖安装跳过交互确认
```

---

## 它做了什么

游戏的表数据放在 **SQLCipher 加密**的 `ExcelDB.db` 里（约 330 MB、424 张表）。
每张表是 `(Key INTEGER, Bytes BLOB)`，`Bytes` 是装着整表数据的 **FlatBuffer**。

1. **字段级改写**：解析每行 blob 里的字符串字段，只改字符串内容、不动 FlatBuffer 结构。含假名的字段整体跳过（日文列在 GL 是死数据）；纯 ASCII 字段（拉丁角色名，如 "Kei"）只做整字段匹配，避免误伤资源路径与内部标识符。
2. **词表优先，可选转简**：先套译名词表——names 表 **exact 整字段匹配**（整个字段相等才替换，
   只命中角色名字段）、text/terms 表 **sub 子串匹配**（单趟、最长键优先、不级联）；
   之后按 `--convert` 做可选的繁中→简中（tw2sp / t2s；`none` 跳过转换，保持繁体民译）。
3. **结构零风险**：等长替换原地写字节；变长替换把新字符串**追加到 blob 末尾**并回填该字段的
   uoffset——已有字节一概不移动，所有旧偏移依然有效。
4. **CRC32 追加修正**：输出末尾追加 4 字节，使整体 CRC32 与输入完全一致（标准 CRC32 可逆构造，
   见 `src/batr/utils/crc.py`）。GL 的 `TableCatalog.bytes` 只记录 CRC32、不记录文件大小。**catalog 完全不用动**。
    - *注：本方法仅对国际服有效，日服似乎会保存大小，因此需要改动TableCatalog*

技术细节与踩坑记录见 [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)。

---

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| 打不开数据库（wrong key） | 游戏大版本更新换了密钥 → `--key` 覆盖 |
| 转换完少数词仍是台式 | 词库覆盖面问题，欢迎 PR 补词（改 `src/batr/data/`） |
| 某些字大小/粗细不统一 | 用 [BA-Font-Replacer](https://github.com/Agent-0808/BA-Font-Replacer) 替换字体即可，详见 [docs/字体问题.md](docs/字体问题.md) |
| 进游戏又变回繁体了 | 游戏本体更新了 → 使用新数据库重新执行即可 |
| 游戏更新后失效 | 库变了 → 重新拉取并跑 `batr patch`（对输出 CRC 自动对齐新库） |

## 字体观感问题

汉化后**被改动过的字**可能比繁简同形的字看起来更细或更小（根因分析见[docs/字体问题.md](docs/字体问题.md)）。

**已解决**：使用 [BA-Font-Replacer](https://github.com/Agent-0808/BA-Font-Replacer)
把客户端的繁体字体（TW 字体）替换为**思源黑体 SC 的 Medium 与 Bold** 两个字重即可，
简体字形将全部由同一款字体渲染，观感完全统一。

---

## 目录结构

```
.
├── pyproject.toml            uv 项目定义（依赖、batr 命令入口）
├── src/batr/
│   ├── cli.py                命令行入口（子命令注册与分发）
│   ├── commands/             各子命令（patch / scan / export / glossary / paths）
│   ├── patch.py              遍历库 → 等长转换 → CRC 修正 → 自校验
│   ├── convert.py            繁简映射（OpenCC 词库，纯 Python）
│   ├── db.py                 SQLCipher 打开 / 遍历
│   ├── utils/                paths.py（游戏路径定位）、crc.py（CRC32 追加修正，来自 BAMT，GPL-3.0）
│   ├── config.py             默认密钥、表过滤等
│   └── data/                 OpenCC 词库（Apache-2.0）
├── scripts/legacy/           从旧项目继承，已弃用的脚本
├── glossary/                 词表（自动生成的本体不入库；blacklist/terms 入库共享）
├── docs/                     原理、用法说明、字体问题
└── tests/                    pytest（CRC 已知向量、转换样例、端到端）
```

---

## License

本仓库：**GPL-3.0**（见 [LICENSE](LICENSE)）—— 因包含来自 BAMT（GPL-3.0）的
[src/batr/utils/crc.py](src/batr/utils/crc.py)，全仓库统一按 GPL-3.0 分发。
原项目 [alisns1/blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified) 的 MIT
许可证全文保留于 [licenses/](licenses/)。
`src/batr/data/` 下的 OpenCC 词库：**Apache-2.0**（见 [src/batr/data/LICENSE-OpenCC.txt](src/batr/data/LICENSE-OpenCC.txt)）。
其余第三方署名见 [THIRD_PARTY.md](THIRD_PARTY.md)。

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

---

## 免责声明 / Disclaimer

This project is intended solely for educational and demonstrative purposes and does not provide any actual resources. Please note that all content downloaded through this project should only be used for legal and legitimate purposes. The developers are not liable for any direct or indirect loss, damage, legal liability, or other consequences that may arise from the use of this project. Users assume all risks associated with the use of this project and must ensure compliance with all relevant laws and regulations. If anyone uses this project for any unauthorized or illegal activities, the developers bear no responsibility. Users are responsible for their own actions and should understand the risks involved in using this project.

"Blue Archive" is a registered trademark of NEXON Korea Corp. & NEXON GAMES Co., Ltd. All rights reserved.

该仓库仅供学习和展示用途，不托管任何实际资源。请注意，所有通过本项目下载的内容均应仅用于合法和正当的目的。开发者不对任何人因使用本项目而可能引发的直接或间接的损失、损害、法律责任或其他后果承担任何责任。用户在使用本项目时需自行承担风险，并确保遵守所有相关法律法规。如果有人使用本项目从事任何未经授权或非法的活动，开发者对此不承担任何责任。用户应对自身的行为负责，并了解使用本项目可能带来的任何风险。

“蔚蓝档案”是上海星啸网络科技有限公司的注册商标，版权所有。

「ブルーアーカイブ」は株式会社Yostarの登録商標です。著作権はすべて保有されています。
