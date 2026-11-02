# 原理与踩坑记录

> 本项目基于 [blue-archive-gl-simplified](https://github.com/alisns1/blue-archive-gl-simplified) 项目迭代而来。

本文记录 `BATR` 的**逆向结论与实现细节**，对应 `src/batr/` 的现行实现，供以后版本更新或移植其他服务器时快速复用。

旧版方案（整 blob 等长替换 + 改 `TableCatalog.bytes`）已废弃，历史版本见 git 或原项目。

***

## 一、数据存在哪

国际服客户端把表数据放在外部资源目录，**PC 与安卓结构相同**：

```
安卓  /sdcard/Android/data/com.nexon.bluearchive/files/PUB/Resource/
PC    SteamLibrary\steamapps\common\BlueArchive\BlueArchive_Data\StreamingAssets\PUB\Resource\
├── Preload/TableBundles/
│   ├── ExcelDB.db            ← 所有文本 + 数值表（约 330 MB，SQLCipher 加密）
│   ├── Excel.zip             ← 只有 62 张玩法常量表，没有任何文本表
│   └── *DBSchema.db          ← 3 个同样加密的附属库
└── Catalog/TableBundles/
    └── TableCatalog.bytes    ← 资源清单（含每个文件的 CRC32）
```

> `Excel.zip` 里面只有 `animationblend`、`bossphase` 之类的常量表，
> `LocalizeExcel` / `CharacterDialogExcel` / `ScenarioScriptExcel` 这些全是文本的库**只存在于 ExcelDB.db**。

`ExcelDB.db` 是 **SQLCipher 4** 加密的 SQLite：

| 参数   | 值                             |
| ---- | ----------------------------- |
| 页大小  | 4096                          |
| KDF  | PBKDF2-HMAC-SHA512，256000 次   |
| 保留区  | 80 字节（16 IV + 64 HMAC-SHA512） |
| 原始密钥 | 32 字节（直接当 AES-256 key 用）      |

`batr` 通过 [`sqlcipher3`](https://pypi.org/project/sqlcipher3/) 打开库（[db.py](../src/batr/db.py)）：
`PRAGMA key = "x'<hex>'"` 后执行一次 `SELECT count(*) FROM sqlite_master` 验证密钥——密钥错在这里就会抛
`sqlite3.DatabaseError`，而不是等到读到坏数据。

表结构（424 张表全都一样）：

```sql
CREATE TABLE LocalizeDBSchema (Key INTEGER, Bytes BLOB)
```

`Bytes` 是 **FlatBuffer**，真正的文本在里面。
（列名不一定叫 `Key`，有的表是 `Id`/`StringId`，所以我们统一用 `rowid` 操作。）

不是所有表都有玩家文本。默认只处理表名匹配以下正则的表（[config.py](../src/batr/config.py)）：

```
Localize|Dialog|Scenario|Subtitle|Talk|Mail|Name|Emoji|Voice|Messanger|SNSProfile
```

> 注意 `Messanger` 是游戏内部的拼写错误（实际是 Messenger 聊天正文，1.6 万个中文字段），
> `SNSProfile` 是 SNS 简介。全表清单可用 `scripts/scan_fields.py --uncovered` 找出
> "没匹配正则但含中文字段"的漏网表。

***

## 二、密钥

```
ef0aaca06f34b4a4be3172a75a3ea565e815f9ece35b1fb12b7a166ba0807bc4
```

- 这是社区工具（delayboy / BlueArchive-Tools）里公开的那把
- **PC 端和安卓端是同一把**（网上流传的"两端密钥不同"是错的）
- 服务端每期活动可能轮换，轮换后用 `--key` 覆盖（`Queuing_GetCryptoKeys` 接口需要已登录会话）

### ⚠️ 最大的坑：HMAC 子密钥长度是 32，不是 64

SQLCipher 校验页头的 HMAC 时，子密钥是这么来的：

```
hmac_key = PBKDF2-HMAC-SHA512(encryption_key, salt[i] ^ 0x3A, 2 iterations, dklen=32)
                                                                                  ^^^^^^
```

**`dklen`** **固定为 32**（SQLCipher 源码里的 `KEY_SIZE`），**不是 SHA512 的摘要长度 64**。

我一开始写成 64，结果是：**密钥完全正确，但所有校验都返回"不匹配"** —— 白白找了几小时。

一个不依赖 AES 的快速校验器（只用 `hashlib`/`hmac`）：

```python
salt   = page[:16]
msg    = page[16:4016] + page[4016:4032] + (1).to_bytes(4, 'little')   # 密文 + IV + 页号
stored = page[4032:4096]
hmac_key = hashlib.pbkdf2_hmac('sha512', raw_key, bytes(b ^ 0x3A for b in salt), 2, dklen=32)
assert hmac.compare_digest(stored, hmac.new(hmac_key, msg, 'sha512').digest())
```

（`reserve = 80` ⇒ `ciphertext_end = 4096 - 80 = 4016`。）

***

## 三、整体流程

[patch.py](../src/batr/patch.py) 的一次运行：

```
复制 src → src.db.tmp
  ↓
遍历匹配表：SELECT rowid, Bytes FROM [table]
  ↓ 每行
FlatBuffer 字段级解析（flatbuf.py）→ 逐字符串字段
  ↓ 每个字段
变换链：glossary exact → glossary sub → OpenCC（见 §5）
  ↓
等长 → 原地写字节；变长 → 追加到 blob 末尾 + 回填 uoffset（见 §4）
  ↓
executemany UPDATE ... SET Bytes=? WHERE rowid=?
  ↓
追加 extra_bytes（默认 08 08 08 08）
  ↓
CRC32 追加修正：输出整体 CRC32 与输入一致（见 §6）
  ↓
os.replace 到 --out → 自校验（重算 CRC + 可选 PRAGMA integrity_check）
```

几个全局约束：

- **输入文件永不修改**：先 `shutil.copy2` 到 `.tmp` 工作，成功后 `os.replace`；任何一步抛异常都会删掉 `.tmp` 与未完成的输出，不留半成品。
- 无法按 FlatBuffer 解析的行（`parse_failed`）**保留原样**，不中断整个流程——宁可少改一行，不能改坏一个 blob。
- `--dry-run` 只读打开源库统计，逐规则打印 `hits`，**不写任何文件**；`hits=0` 的词条多半是键写错，这是词表排查的主要手段。

***

## 四、FlatBuffer 字段级补丁（核心技术）

[flatbuf.py](../src/batr/flatbuf.py) 是 patch / preview / scan\_fields 共用的唯一解析实现。

### 4.1 blob 的结构

每行 `Bytes` 是一个完整的 FlatBuffer，根是一张表：

```
blob[0:4]           root uoffset（相对 blob 起点指向表对象）
表对象[0:4]         soffset（有符号）—— vtable 位置 = 表对象位置 - soffset
vtable              [u16 vtable_len][u16 object_len][u16 slot2 偏移][u16 slot3 偏移]...
字符串字段          一个 uoffset32，指向 [u32 字节长][UTF-8][0x00]
```

关键点：**所有偏移都是相对的**。只要不移动任何已有字节，全部旧偏移依然有效——这是整个方案的立足点。

### 4.2 为什么不再"整 blob 等长替换"

旧版把 blob 里连续的 3 字节 CJK 区段整段转换，长度不一致就整段放弃。缺陷：

- 只能处理繁→简这种"绝大多数等长"的转换，**无法支持自定义译名**（民译词表几乎必然变长）；
- 是无结构的字节扫描，理论上会命中非文本区段的巧合。

新版按 vtable 精确遍历**字符串字段**，每个字段独立决定原地写还是追加。代价是要写 FlatBuffer 解析器，收益是支持任意长度替换 + 天然不会碰坏非文本数据。实测 54,075 个字段与官方 FlatBuffers runtime 交叉解析，0 处不匹配。

### 4.3 读字符串的六条硬校验（[read\_string](../src/batr/flatbuf.py#L39-L68)）

vtable 槽位可能实际存标量或向量，uoffset 解引用是**猜**的，误判就会改坏数据。所以每个字符串必须全过六条：

1. 位置落在数据区（`4 <= spos <= n-5`，0 处是 root uoffset）；
2. 长度 ≤ 1 MiB（防把二进制巧合当字符串）；
3. 以 `0x00` 结尾；
4. 严格 UTF-8 解码通过；
5. 至少含一个 CJK 表意文字（假名/韩文/泰文/英文都不是目标）；
6. 除 `\n` 外不含控制字符。

任何一条不满足 → 当作"不是字符串"，跳过。第 5 条可用 `allow_ascii=False/True` 控制：纯 ASCII 字段（拉丁角色名 `"Kei"`、`"Ain"`）走单独的 exact-only 通道（见 §5.4）。

### 4.4 遍历字段（[iter\_string\_fields](../src/batr/flatbuf.py#L71-L107)）

- root/vtable 各自做越界与长度合法性检查（`vt_len ≥ 4`、偶数、不越界），不合法抛 `ValueError`，调用方保留原 blob；
- vtable 的 u16 序号 0/1 是 `vtable_len`/`object_len` 本身，**字段偏移从序号 2 开始**；
- 槽位偏移为 0 表示该字段用默认值（字符串默认 null），跳过；
- 字段位置 `fpos = root + off`，字符串位置 `spos = fpos + uoffset(fpos)`。

### 4.5 写回：等长原地 / 变长追加（[patch\_blob](../src/batr/flatbuf.py#L119-L166)）

对每个新文本（UTF-8 字节）：

- **等长**：直接原地覆写字节区段。零膨胀、结构零风险。注意共享同一字符串的其他字段会一并生效——它们语义相同，这是期望行为。
- **变长**：
  1. 把 blob 补零对齐到 4 字节；
  2. 在**末尾**追加 `[u32 长度][新 UTF-8][0x00]`；
  3. 把字段的 uoffset32 回填为 `spos_new - fpos`。

已有字节一概不移动，所以其它所有字段、向量、偏移全部照旧。同一字符串被多个字段共享时只追加一次（`appended: dict[spos → spos_new]`），其余字段只改各自的 uoffset。

假名判定在写回之前：字段含 U+3040–U+30FF 即视为日文列，**整体跳过**（默认 `skip_kana`，`--convert-kana` 关闭）。日文列在 GL 是死数据，跳过它们既省时间又避免把日文原文误转。

***

## 五、变换链与词表系统

### 5.1 顺序

每个字符串字段依次经过（[\_make\_transforms](../src/batr/patch.py#L51-L71)）：

```
glossary exact（整字段相等） → glossary sub（子串） → OpenCC（--convert 控制）
```

词表匹配发生在 OpenCC **之前**：输入固定是数据库里的繁体原文，译文直接写简体（或繁体，繁→繁模式配合 `--convert none`）。变换前后相同则该字段不动。

### 5.2 OpenCC 三层链（[convert.py](../src/batr/convert.py)）

`tw2sp`（默认）= `TWPhrasesRev` → `TSPhrases` → `TSCharacters`；`t2s` = 后两层。两层含义：

- **顺序是语义的一部分**：上一层输出是下一层输入。`TWPhrasesRev` 先把「資料」换成「數據」，单字层再把「數/據」转成「数/据」，最终才是大陆写法。如果合并成一次匹配，就丢掉了后半步。
- **词组优先于单字**：每层内部最长匹配优先（词组表先试，长度递减），避免"一简对多繁"拆错字。
- 是 OpenCC 规则的**独立实现**（纯标准库，只读取其词库数据，Apache-2.0）。

### 5.3 词表模型：编译式（[glossary.py](../src/batr/glossary.py) / [commands/glossary.py](../src/batr/commands/glossary.py)）

词表流程收敛为两步，所有隐式规则变成显式数据：

```
batr glossary = 编译：auto 条目 + 手写词表 + 黑名单过滤 → glossary/compiled.tsv（唯一产物）
batr patch    = 消费：只读 compiled.tsv，不再自己拼词表路径
```

手写词表放在三镜像目录（name.tsv / text.tsv / blacklist.txt 各一份，三个目录完全镜像）：

| 目录       | 定位                 | 入库？          |
| -------- | ------------------ | ------------ |
| `shared/` | 客观共识（可 PR）        | ✅            |
| `local/`  | 个人偏好（整目录 gitignore）| ❌ 缺文件自动从 `templates/` 复制 |
| `templates/` | 空模板，格式的事实来源     | ✅            |

**文件名不承载任何语义**：匹配方式由各文件头 `# mode: exact|sub` 声明（缺省 `sub`），用户可按内容任意拆分文件（如 `orgs.tsv`），编译器扫描 `shared/*.tsv` 与 `local/*.tsv` 每一个文件。

| mode    | 匹配方式            | 用途                                              |
| ------- | --------------- | ----------------------------------------------- |
| `exact` | **exact** 整字段相等 | 角色名。整字段匹配保证 `旬`/`希望` 这类歧义短词**只**命中真正的名字字段，不误伤正文 |
| `sub`   | **sub** 子串      | 正文替换（地名/组织/皮肤名等）                                |

sub 是**单趟扫描、最长键优先、不级联**：输出一旦产生就不再参与匹配，`A→B` 的结果不会被 `B→C` 再次命中（与 OpenCC 的逐层策略不同，这里是单层内不级联）。

编译加载顺序：**auto 条目 → shared/*.tsv（文件名字母序）→ local/*.tsv（文件名字母序），后加载者优先**（dict.update 语义，直觉对应「自动 < 共享 < 个人」）；同键覆盖时编译日志报告。同 mode 内重复键保留先出现的并告警；同名键允许跨表（exact/sub 各司其职）；恒等行（模板占位，旧词==新词）加载时跳过。黑名单在**编译期**对一切来源过滤。patch 端零合并逻辑，只 `from_compiled` 加载产物；每条规则的命中次数被记录，`--dry-run` 时逐条打印 `hits`。

### 5.4 纯 ASCII 字段：只做 exact

资源路径（`UIs/03_Scenario/...`）、内部标识符都是纯 ASCII，做子串替换大概率炸；但游戏里确实存在拉丁字母角色名（`Kei` / `Ain` / `Aur` / `Soph`），民译要换成汉字。所以 ASCII 字段只走 `apply_exact`（整字段相等才替换），`--no-ascii-exact` 可整体关闭。

### 5.5 auto 条目来源（[commands/glossary.py](../src/batr/commands/glossary.py)）

- 数据源：[KivoWiki（基沃托斯古书馆）](https://kivo.wiki/) 民译，经 [BA-characters-internal-id](https://github.com/Agent-0808/BA-characters-internal-id) 的 [`students.json`](https://agent-0808.github.io/BA-characters-internal-id/data/students.json)（姓名分离为 `family_name_*` / `given_name_*` 字段）与 [`skin_map.json`](https://agent-0808.github.io/BA-characters-internal-id/data/skin_map.json)（皮肤基名各语言译名）分发，缓存在 `work/BACII_students.json` / `work/BACII_skin_map.json`（`--refresh` 强制重下）；
- 键 = kivo 繁体字段（名段 `given_name_tw`、全名连写、皮肤繁中名）；值 = kivo 无后缀简中民译字段（`given_name` / `family_name`）。
  - 全名连写（姓氏连写形式）单独生成一条，如`聖園彌香 → 圣园未花`；
  - 皮肤名以 `角色名(皮肤)` 内嵌形式出现，text 用**带括号的键**，如`(單車) → (骑行服)`，只命中括号内，不动正文里的裸词；注意游戏内使用半角括号。
- auto 条目**不落盘**，每次编译从数据源重新生成，仅在 t2s profile 下编入（t2t 编入会把简中值带进繁→繁流程）。
- 过滤：OpenCC t2s 后已相等（无需词条）、空键、繁简同形键（如 `御稜名草`，无实际改动）；黑名单（见下）在编译末尾统一过滤。
- KivoWiki 键与游戏原文偶有差异（如游戏 `白子＊TERROR`、kivo `白子*TERROR`，全角/半角不同）导致 `hits=0`。**不做归一化映射表**：发现一处就在 `shared/` 或 `local/` 手写一条正确键的词条（值与 kivo 民译一致），原 auto 键保留——`hits=0` 本身就是诊断信号，手写条相当于「已知差异」的显式记录，并按后加载覆盖规则生效。排查路径对所有键一致：`batr scan <关键词>` 定位数据库真实写法 → `--dry-run` 看 `hits=0`。

### 5.6 用户自己加词表

个人内容写 `glossary/local/`（不入库），通用共识写 `glossary/shared/`（可 PR）。

判断标准：**这条词条换个玩家是否也该生效？** 该 → `shared/`；只是自己的口味 → `local/`。

想加词条时按用途选文件：

| 想改什么                         | 写哪个文件                          | mode  |
| ---------------------------- | ------------------------------ | ----- |
| 个人角色名译名修正/补充                 | `glossary/local/name.tsv`     | exact |
| 个人正文替换（台词措辞、皮肤名等）            | `glossary/local/text.tsv`      | sub   |
| 地名/组织/术语等**通用**词条（可 PR 入库共享） | `glossary/shared/text.tsv`           | sub   |
| 禁用某个词条（自动或手写都行）              | `glossary/local/blacklist.txt` | 禁用    |

- `local/` 缺文件时编译自动从 `templates/` 复制；已存在的不动（删除后重跑得到新空模板）。
- 格式：`旧词<TAB>新词`
  - **分隔符是 Tab 不是空格**，写错整行被跳过并告警）
  - `#` 开头是注释；整文件匹配方式由头部 `# mode: exact|sub` 声明
  - 键必须是数据库里的**繁体原文**——写错即零命中，可以用 `--dry-run` 的 `hits=0` 排查。
  - t2s 流程（默认）值写简体或繁体都行（繁体会再过 OpenCC 转简体）；t2t 流程（`--profile t2t`，patch 端自动绑定 `--convert none`）值必须写繁体，用 `batr glossary --template` 在 `local/` 生成恒等行脚手架（右列与左列相同的行 = 未填写，加载时跳过）。
- 编译优先级见 §5.3：后加载者优先，local 覆盖 shared、手写覆盖 auto。
- 禁用词条的粒度：黑名单第二列可限定匹配方式，如 `希望<TAB>sub` = 整字段匹配照常替换、正文子串替换跳过（避免误伤普通词"希望"），`键<TAB>exact` 反之，不写则两种都禁用；黑名单对自动与手写**一切来源**生效（`shared/blacklist.txt` 客观入库，`local/blacklist.txt` 个人）。
- 产物 `glossary/compiled.tsv`（gitignore）是 patch 的唯一输入，注释头记录 profile、生成时间与来源统计；重跑 `batr glossary --profile ...` 即切换流程。
- patch 结束时（含 `--dry-run`）把逐规则命中数写入 `glossary/hits.tsv`（gitignore，`--hit-log none` 关闭）：五列 `旧词/新词/mode/source/hits`，按 hits 降序、零命中沉底，是清理过期与拼错词条的主要依据。
- 以上文件名都是示例，实际文件名可以任意命名，也可以创建多个文件管理不同领域的词条。只需头部注明 `# mode: exact|sub` 即可。

***

## 六、CRC32 追加修正（替代 catalog 改写）

客户端启动时用 `TableCatalog.bytes` 校验每个资源文件的 CRC32，不匹配就当文件损坏重新下载。旧方案是解析 catalog、手工改写那一条 CRC；新方案（[utils/crc.py](../src/batr/utils/crc.py)，取自 [BA Modding Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)，GPL-3.0）**完全不碰 catalog**：

标准 CRC32（IEEE，反射算法）是 GF(2) 上的线性函数。在文件末尾追加 4 个字节，总能解出一组值使整体 CRC 等于任意目标：

```
base          = crc32(修改后的数据)
crc_with_zero = crc32(b'\x00\x00\x00\x00', base)      # 追加 4 个 0 后的 CRC
k             = bitrev32(target_crc ^ crc_with_zero)   # 逆比特
correction    = k * x^32 ≡ 目标差  在 GF(2)[x]/(poly) 下的解
                = gf2_mul_mod(k, GF2_INVERSE_X32)      # x^32 的乘法逆
末尾写入       = correction 的逐字节内比特反转
```

实现上就是 `apply_crc_fix`：算出差值 → `GF(2)` 上乘 `x^{-32}`（常量 `0xCBF1ACDA`）→ 得到 4 个修正字节，**解的唯一性有保证，不会失败**。

两个关键支撑：

1. **SQLite 按页计数读库，尾部多余字节被忽略**——库后面多 4 字节（修正值）+ 4 字节（`extra_bytes`）不影响任何读取；
2. **GL 的 catalog 只记录 CRC32、不记录文件大小**，文件变长无所谓。（日服似乎会存大小，此方法对日服无效。）

`extra_bytes` 默认 `08 08 08 08`，可用 `--extra-bytes` 换成任意 hex（含空串语义上的无操作）。

***

## 七、排查工具与手段

| 手段                                           | 用途                                                          |
| -------------------------------------------- | ----------------------------------------------------------- |
| `--dry-run` 逐规则 `hits`                       | `hits=0` = 键拼错/过期；正常应与词表条目数大致对应                             |
| `--verify`                                   | 输出后重开库跑 `PRAGMA integrity_check`                            |
| 输出日志的 `parse_failed`                         | 某表出现它说明 FlatBuffer 结构假设被打破（版本更新常见信号）                        |
| [scan\_fields.py](../scripts/scan_fields.py) | 关键词在哪些表/哪些字段以什么形态出现；`--diff` 两库对比验证替换效果；`--uncovered` 找漏掉的表 |
| [脚本用法说明.md](脚本用法说明.md)                       | 上述工具的完整参数                                                   |

***

## 八、走过但没用的路（别再重复踩）

| 尝试                                  | 结论                                                                                      |
| ----------------------------------- | --------------------------------------------------------------------------------------- |
| 扫内存找密钥                              | ❌ 客户端读完库就释放页缓存。全进程内存扫描（含文件映射）只有 `libsqlcipher.so` 自己的常量字符串，没有任何解密后的 `SQLite format 3` 页 |
| 等它打开库的瞬间连拍内存                        | ❌ 对比前后快照、只搜变化字节（138 MB、步长 1 全扫）——也没有                                                    |
| 在客户端 DB 里找明文                        | ❌ 磁盘上 4 个库全是密文，没有解密临时文件                                                                 |
| 重签 APK                              | ❌ 文本不在 APK 里，表数据全是从 CDN 下的                                                              |
| `Excel.zip`                         | ❌ 62 张表全是玩法常量，没有文本表                                                                     |
| 走 gateway 接口要密钥                     | ⚠️ 加上 `mx: 2` 请求头后 `Queuing_GetCryptoKeys` 会返回 200，但需要**已登录会话**才有内容                     |
| 不 root 的手机取内存                       | ❌ 读别的进程内存需要 root 或 ptrace 权限；Shizuku / adb 只到 shell（uid 2000）级别，达不到                     |
| IDA 断点抓 key                         | 汉化者建议的路子，能做但是几十小时级工程量（**最后没用上**：密钥本来就是公开的）                                              |
| 整 blob 等长替换                         | ❌ 已废弃：无法支持变长的自定义译名，且是无结构扫描。被 §4 的字段级方案取代                                                |
| 改 **`TableCatalog.bytes`** 的 CRC 条目 | ❌ 已废弃：要手工解析 FlatBuffer catalog 且只对 GL 成立。被 §6 的 CRC 追加修正取代（日服仍可能需要老办法）                  |

**教训**：先花 10 分钟验证"我的校验器对不对"，再去花 5 小时搜内存。
那次把 `dklen` 写成 64，让所有搜索都成了假阴性。

***

## 九、已知限制

1. **只有 GL（繁中）能用**。日服 / 韩服 / 国服的库、文本表、catalog 结构都不同（日服 catalog 记录文件大小，CRC 追加修正也会失效）
2. **图片上的文字改不了**（立绘、活动 banner、部分 logo 是烘焙进图的），只改**文本表**
3. 少数用词可能仍然偏台式（词库覆盖面有限），欢迎 PR 补词
4. 游戏大版本更新后要重跑（库变了 → 重新拉取执行 `batr`；换密钥时用 `--key`）
5. 简体字形渲染观感问题不在本工具范围内——用 [BA-Font-Replacer](https://github.com/Agent-0808/BA-Font-Replacer) 换字体解决，见 [字体问题.md](字体问题.md)

