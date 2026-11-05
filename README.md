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

> 根据国际服的加载机制与中文语言的性质做了特化 
>
> 因此仅适用于 **国际服繁中**。

| 改之前 | 改之后 |
|---|---|
| ![before](docs/before.jpg) | ![docs/after.jpg](docs/after.jpg) |

## 安装

- 需要 [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/Agent-0808/BA-Term-Replacer.git
cd BA-Term-Replacer
uv sync
```

## 详细使用教程

两种主要用途，各自是一条完整流程（备份 → 定制词表 → 编译 → 应用）：

- **流程 A：繁→简**    —— KivoWiki 民译词表自动获取 + OpenCC 繁体转简体，不改词表也能直接跑
- **流程 B：繁→繁民译** —— 不转字形，auto 不编入，需要自己填写译文

命令参数与排查路径详解见 [docs/脚本用法说明.md](docs/脚本用法说明.md)；词表文件语法与运作机制见 [docs/词表系统.md](docs/词表系统.md)。

### 流程 A：繁→简

1. **备份文本数据库（推荐）**：

先复制一份游戏目录里库的干净副本，防止修改后产生错误。之后所有命令都用备份的文件作为原数据：

```bash
uv run batr backup     # 复制为 work/db/ExcelDB.db（自动定位游戏库；已存在不覆盖，--force 重写）
```

2. **（可选）添加自己的词条**：

KivoWiki 获取的民译条目已覆盖角色名与皮肤名，不改也能直接用；想调整偏好再编辑 `glossary/local/` 里的文件。

3. **编译词表**：

```bash
uv run batr glossary   # 默认 t2s：auto 条目 + 手写词表 → glossary/compiled.tsv
```

4. **应用到游戏**：

```bash
uv run batr patch --db work/db/ExcelDB.db --dry-run   # 预演：逐规则打印命中数，hits=0 多半是键写错
uv run batr patch --db work/db/ExcelDB.db             # 正式产出
# 确认没问题后覆盖安装到游戏目录（覆盖前自动备份原库为 .bak）：
uv run batr patch --db work/db/ExcelDB.db --install
```

### 流程 B：繁→繁民译

1. **备份文本数据库（推荐）**：

```bash
# 复制为 work/db/ExcelDB.db（自动定位游戏库；已存在不覆盖，--force 重写）
uv run batr backup     
`````

同流程 A 第 1 步。

2. **生成待填模板**：

```bash
# 往 glossary/local/ 补恒等行模板，不编译
uv run batr glossary --template
```

3. **填写模板**：

进入 `glossary/local/` 目录，把恒等行右列改成你喜欢的繁体译文；未填的行（右列 = 左列）编译时自动跳过。

4. **编译词表**：

```bash
# t2t 模式只编译手写词表，不获取简体民译
uv run batr glossary --profile t2t
```

5. **应用到游戏**

`--profile t2t` 参数会自动绑定 `--convert none`，不进行 OpenCC 的繁体→简体转换流程。：

```bash
uv run batr patch --db work/db/ExcelDB.db --profile t2t --out output/ExcelDB.db
# 确认没问题后覆盖安装到游戏目录：
uv run batr patch --db work/db/ExcelDB.db --profile t2t --install
```

替换没生效、译名不对时，用 `uv run batr scan` 做字段级排查，完整参数与排查路径见 [docs/脚本用法说明.md](docs/脚本用法说明.md)。

### 词表文件夹内容

`glossary/` 目录下存放将要编译的词表文件。

使用 `uv run batr glossary` 命令后便会生成 `glossary/compiled.tsv` 文件，供 `patch` 命令使用。

想改什么 → 写哪个文件（两条流程通用）：

| 想要修改 | 修改文件 |
|---|---|
| 写自己的角色名译名 | `local/name.tsv`（`--template` 生成空模板） |
| 补充/修正译名（个人偏好） | `local/name.tsv` / `local/text.tsv`（不入库，后加载优先于 shared） |
| 地名/组织/术语等通用共识 | `shared/text.tsv`（入库共享，可 PR） |
| 禁用某个词条（自动或手写都行） | `local/blacklist.txt` |

格式：TSV 两列 `旧词<TAB>新词`，**分隔符是 Tab 不是空格**；键必须是数据库里的繁体原文；值写译文（繁→繁写繁体；繁→简可以简体或繁体，还会通过 OpenCC 转成简体）。

其余语法（`# mode:` 声明、歧义词处理、黑名单 scope、皮肤名括号键等）见 [docs/词表系统.md](docs/词表系统.md)。

## 命令一览

> [!TIP]
> 详细说明见 [脚本用法说明](./docs/脚本用法说明.md)

```
# 查看所有命令
uv run batr -h
```

PC 端支持自动定位 Steam 客户端的 `ExcelDB.db` 文件，`uv run batr paths` 可查看检测结果

大部分命令都支持 --db 参数，用于指定输入 `ExcelDB.db` 文件。当不输入时，自动根据注册表定位游戏的 `ExcelDB.db` 文件。

```
batr <子命令>
  patch      字段级文本补丁（支持变长替换）+ CRC 追加修正，--install 覆盖安装到游戏目录
  backup     把未改动的库复制为本地干净副本（默认 work/db/ExcelDB.db）
  scan       字段级扫描（调试）：关键词定位 / 两库对比 / 未覆盖表清单
  export     把目标表的文本字段导出成每表一个 TSV
  glossary   词表编译：数据源 + 手写词表 + 黑名单 -> glossary/compiled.tsv（--template 生成恒等行模板）
  paths      显示检测到的游戏安装路径与 ExcelDB.db 路径

patch 常用参数（其余子命令见 -h）：
  --db <文件>        输入 ExcelDB.db（不会被修改；省略则自动定位游戏安装路径）
  --out <文件>       输出库（CRC32 与输入一致；默认 output/<输入文件名>）
  --convert <模式>   tw2sp 含台湾用词转换（伺服器->服务器），t2s 只转字形，
                     none 只做替换表（默认 tw2sp）
  --convert-kana     不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）
  --tables <正则>    限定要处理的表（默认 Localize|Dialog|Scenario|...）
  --extra-bytes HEX  CRC 修正前附加到输出末尾的自定义字节（hex，如 DEADBEEF）
  --profile <流程>   词表流程：t2s 繁→简（默认）/ t2t 繁→繁（自动绑定 convert=none）
  --glossary <文件>  编译词表产物（默认 glossary/compiled.tsv，batr glossary 生成）
  --no-ascii-exact   关闭纯 ASCII 字段的 exact 匹配（默认开启，覆盖 "Kei" 这类拉丁角色名）
  --key <hex>        覆盖 SQLCipher 密钥（游戏换密钥时用）
  --dry-run          只统计，不写任何文件
  --verify           输出后进行 integrity_check
  --region <区服>    自动定位用的区服（auto = global 优先，japan 兜底）
  --install          补丁成功后覆盖安装到游戏目录（覆盖前备份 .bak，交互确认）
  --yes              覆盖安装跳过交互确认
```

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
    - *注：本方法仅对国际服有效，日服似乎会保存大小，因此需要改动TableCatalog。*

> [!TIP]
> 技术细节与踩坑记录见 [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)

## 字体观感问题

汉化后**被改动过的字**可能比繁简同形的字看起来更细或更小（根因分析见[docs/字体问题.md](docs/字体问题.md)）。

解决方法：使用 [BA-Font-Replacer](https://github.com/Agent-0808/BA-Font-Replacer)
把客户端的繁体字体（TW 字体）替换为**思源黑体 SC 的 Medium 与 Bold** 两个字重即可，
简体字形将全部由同一款字体渲染，观感完全统一。

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
├── docs/                     原理、用法说明、词表系统、字体问题
└── tests/                    pytest（CRC 已知向量、转换样例、端到端）
```

## License

**GPL-3.0**（见 [LICENSE](LICENSE)）。

## 署名与第三方组件

本工具基于原项目 [alisns1/blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified)（**MIT**，[许可证全文](licenses/blue-archive-gl-simplified-LICENSE.txt)）现代化重构而来 —— 致谢原作者与所有贡献者。

本项目站在社区成果之上，逐项署名见 **[THIRD_PARTY.md](THIRD_PARTY.md)**：

- [blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified)：本仓库的前身（等长替换思路与初始实现）（MIT）
- [OpenCC](https://github.com/BYVoid/OpenCC)：繁简映射词库（Apache-2.0）
- [BA-Characters-Internal-ID](https://github.com/Agent-0808/BA-characters-internal-id)：繁中译名列表与简中民译，运行时动态获取（CC BY-SA 4.0）
- [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)：CRC32 追加修正（GPL-3.0）
- BlueArchive-Tools / BlueArchive-Tools-CLI（delayboy 系）：仅作 SQLCipher 参数的参考；**本仓库不含其任何代码**（AGPL-3.0）
- 社区所有做国际服/日服汉化的朋友：思路与经验

运行时依赖（由 `uv sync` 自动安装，定义见 [pyproject.toml](pyproject.toml)）：

- [sqlcipher3-wheels](https://pypi.org/project/sqlcipher3-wheels/)：SQLCipher 加密 SQLite 库的 Python 绑定，负责打开/写入 `ExcelDB.db`（zlib；SQLCipher 本体 BSD 风格）
- [typed-argument-parser](https://github.com/swansonk14/typed-argument-parser)：类型注解驱动的命令行参数解析（MIT）

## 免责声明 / Disclaimer
<sub>
This project is intended solely for educational and demonstrative purposes and does not provide any actual resources. Please note that all content downloaded through this project should only be used for legal and legitimate purposes. The developers are not liable for any direct or indirect loss, damage, legal liability, or other consequences that may arise from the use of this project. Users assume all risks associated with the use of this project and must ensure compliance with all relevant laws and regulations. If anyone uses this project for any unauthorized or illegal activities, the developers bear no responsibility. Users are responsible for their own actions and should understand the risks involved in using this project.
</sub>

"Blue Archive" is a registered trademark of NEXON Korea Corp. & NEXON GAMES Co., Ltd. All rights reserved.

该仓库仅供学习和展示用途，不托管任何实际资源。请注意，所有通过本项目下载的内容均应仅用于合法和正当的目的。开发者不对任何人因使用本项目而可能引发的直接或间接的损失、损害、法律责任或其他后果承担任何责任。用户在使用本项目时需自行承担风险，并确保遵守所有相关法律法规。如果有人使用本项目从事任何未经授权或非法的活动，开发者对此不承担任何责任。用户应对自身的行为负责，并了解使用本项目可能带来的任何风险。

“蔚蓝档案”是上海星啸网络科技有限公司的注册商标，版权所有。

「ブルーアーカイブ」は株式会社Yostarの登録商標です。著作権はすべて保有されています。

> 本仓库不含任何游戏素材。密钥 `ef0aaca0…` 是社区公开流传的**数据值**，
> 作为可覆盖的默认值提供（`--key` / `BA_KEY`）。