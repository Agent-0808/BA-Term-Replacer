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

## 2. OpenCC 词库（已包含在仓库内）

| 项 | 内容 |
|---|---|
| 文件 | `src/batr/data/TSCharacters.txt`、`src/batr/data/TSPhrases.txt`、`src/batr/data/TWPhrasesRev.txt` |
| 来源 | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) — `data/dictionary/` |
| 许可证 | **Apache License 2.0** |
| 使用方式 | **原样复制，未作修改** |
| 许可证全文 | [`src/batr/data/LICENSE-OpenCC.txt`](src/batr/data/LICENSE-OpenCC.txt) |

`src/batr/convert.py` 只是这套词库的**读取与应用逻辑**（我们自己写的），词库数据本身版权归 OpenCC 项目所有。

---

## 3. CRC32 追加修正（已包含在仓库内）

| 项 | 内容 |
|---|---|
| 文件 | `src/batr/utils/crc.py` |
| 来源 | [BA-Modding-Toolkit（BAMT）](https://github.com/Agent-0808/BA-Modding-Toolkit) — `src/ba_modding_toolkit/utils/crc.py` |
| 许可证 | **GNU GPL-3.0**（本仓库因此整体以 GPL-3.0 分发，见根目录 `LICENSE`） |
| 使用方式 | `patch.py` 在输出文件末尾追加 4 字节，使整体 CRC32 等于原文件值，从而替代旧的 catalog 改写。 |

---

## 4. SQLCipher 参数与密钥（事实性信息，未包含其代码）

| 项 | 内容 |
|---|---|
| 参考来源 | [BlueArchive-Tools / BlueArchive-Tools-CLI](https://github.com/DelAD/delayboy) — `utils/sqlcipher.py` 等 |
| 许可证 | **AGPL-3.0** ⚠️ |
| 使用方式 | **仅作为参考**，用于确认 SQLCipher 4 的参数（页大小 4096、KDF 迭代 256000、HMAC-SHA512、保留区 80 字节）。 |
| 重要说明 | **本仓库不包含该项目的任何代码**，因此不受 AGPL-3.0 的传染性约束。数据库的打开/读写全部交给独立的第三方库 `sqlcipher3`。 |

我们自己的密钥校验器（仅用于开发期验证，**未包含在本仓库**）曾按该实现的逻辑重写，
过程中发现其 HMAC 子密钥长度参数为 32 —— 该参数属于 SQLCipher 的**接口事实**，不受版权保护。

### 关于密钥本身

`ef0aaca0…807bc4` 是社区**公开流传**的密钥值（上述项目及相关文档中均有记载）。
密钥属于**数据/事实**，不是受版权保护的表达；本仓库将其作为可覆盖的默认值提供
（`--key` / `BA_KEY`）。

---

## 5. 运行时依赖（未包含在仓库内，由用户自行安装）

| 包 | 许可证 | 用途 |
|---|---|---|
| [`sqlcipher3-wheels`](https://pypi.org/project/sqlcipher3-wheels/) | 见 PyPI 页面（SQLCipher 本体为 BSD 风格） | 打开/写入 SQLCipher 加密的 SQLite 库 |

安装方式见 `pyproject.toml`（`uv sync`）。依赖的许可证随其发行包一并提供，本仓库不再重复分发。

---

## 6. 其他参考（思路借鉴，未使用其代码）

| 项目 | 许可证 | 借鉴内容 |
|---|---|---|
| [BAJP2CNPatch](https://github.com/) （BAJP2CNPatch-main） | MIT | 用代理替换资源文件的整体思路；以及"改 catalog 而非伪造文件"的做法 |
| [headless-bluearchive / SDK](https://github.com/) （SDK-main） | MIT | `Excel.zip` 口令的推导方式（纯分析用，未收录） |
| BlueArchive-Translator（相关文档） | 未声明 | 社区文档中关于密钥来源的说明 |

---

## 如果你要复用本仓库

- 本仓库（含自有代码与 `src/batr/utils/crc.py`）：**GPL-3.0**（见 [`LICENSE`](LICENSE)）
- 原项目的 MIT 许可证与署名：见第 1 节，请一并保留
- `src/batr/data/` 下词库：**Apache-2.0**（保留 `src/batr/data/LICENSE-OpenCC.txt` 即可）
- 上面第 3、4 节的署名请一并保留

如发现署名有遗漏或不当，欢迎提 Issue 或 PR 指出，我们会立刻更正。
