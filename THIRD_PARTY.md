# 第三方组件与署名 / Third-party notices

本仓库**不包含任何游戏素材**，本身只处理用户自己设备上已有的文件。
下面是开发过程中使用或参考过的第三方成果，按许可证要求逐项署名。

---

## 1. 原项目（本工具的前身）

| 项 | 内容 |
|---|---|
| 来源 | [alisns1/blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified) |
| 许可证 | **MIT License**，Copyright (c) 2026 Blue Archive GL Simplified Chinese localization contributors |
| 许可证全文 | [`licenses/blue-archive-gl-simplified-LICENSE.txt`](licenses/blue-archive-gl-simplified-LICENSE.txt) |
| 说明 | 本工具在其「SQLCipher 打开 + FlatBuffer 内等长字节替换」的基础上现代化重构而来，原项目的思路与代码是本仓库的起点。 |

---

## 2. OpenCC 词库

| 项 | 内容 |
|---|---|
| 文件 | `src/batr/data/OpenCC/TSCharacters.txt`、`src/batr/data/OpenCC/TSPhrases.txt`、`src/batr/data/OpenCC/TWPhrasesRev.txt` |
| 来源 | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) — `data/dictionary/` |
| 许可证 | **Apache License 2.0** |
| 使用方式 | **原样复制，未作修改** |
| 许可证全文 | [`src/batr/data/OpenCC/LICENSE-OpenCC.txt`](src/batr/data/OpenCC/LICENSE-OpenCC.txt) |

`src/batr/convert.py` 只是这套词库的读取与应用逻辑，词库数据本身版权归 OpenCC 项目所有。

---

## 3. CRC32 追加修正

| 项 | 内容 |
|---|---|
| 文件 | `src/batr/utils/crc.py` |
| 来源 | [BA-Modding-Toolkit（BAMT）](https://github.com/Agent-0808/BA-Modding-Toolkit) — `src/ba_modding_toolkit/utils/crc.py` |
| 许可证 | **GNU GPL-3.0**（本仓库因此整体以 GPL-3.0 分发，见根目录 `LICENSE`） |
| 使用方式 | `patch.py` 在输出文件末尾追加 4 字节，使整体 CRC32 等于原文件值，从而替代旧的 catalog 改写。 |

---

## 4. SQLCipher 参数与密钥

| 项 | 内容 |
|---|---|
| 参考来源 | [BlueArchive-Translation/BlueArchive-Tools](https://github.com/BlueArchive-Translation/BlueArchive-Tools) — `utils/sqlcipher.py` 等 |
| 许可证 | **AGPL-3.0** |
| 使用方式 | **仅作为参考**，用于确认 SQLCipher 4 的参数（页大小 4096、KDF 迭代 256000、HMAC-SHA512、保留区 80 字节）。 |

- 本仓库不包含该项目的任何代码。
- 参数属于 SQLCipher 的**接口事实**，不受版权保护。

### 关于密钥本身

密钥属于**数据/事实**，不是受版权保护的表达；本仓库将其作为可覆盖的默认值提供
（`--key` / `BA_KEY`）。

---

## 5. 密钥动态获取方法

| 项 | 内容 |
|---|---|
| 参考来源 | [delayboy/BlueArchive-Translator](https://github.com/delayboy/BlueArchive-Translator) — `相关文档/` 下的《游戏密钥 hook 点迁移总结》 |
| 许可证 | **未声明**（该仓库为 monorepo，聚合了大量第三方工具与作者自撰文档，根目录没有 LICENSE） |
| 使用方式 | **仅参考其公开的逆向思路**：IL2CPP 下 `KeyData` 三段拼接 → `PRAGMA key` 的拦截点位置、以及用 CE 特征码免静态分析定位 Hook 点的方法。|

本仓库不包含该项目的任何代码。

特征码、断点偏移与操作步骤均由本项目在自己的游戏副本上重新实测验证并重写，见 [获取数据库密钥](docs/获取数据库密钥.md) 与 `scripts/find_db_key.lua`。 

---

## F. 运行时依赖

| 包 | 许可证 | 用途 |
|---|---|---|
| [`sqlcipher3-wheels`](https://pypi.org/project/sqlcipher3-wheels/) | **zlib**（[sqlcipher3 绑定](https://github.com/coleifer/sqlcipher3/blob/master/LICENSE)）；SQLCipher 本体为 BSD 风格 | 打开/写入 SQLCipher 加密的 SQLite 库 |
| [`typed-argument-parser`](https://github.com/swansonk14/typed-argument-parser) | MIT | 命令行参数解析 |

安装方式见 `pyproject.toml`（`uv sync`）。依赖的许可证随其发行包一并提供，本仓库不再重复分发。

---

如发现署名有遗漏或不当，欢迎提 Issue 或 PR 指出，我们会立刻更正。