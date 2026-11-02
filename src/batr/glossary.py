"""译名词表：手写文件解析（mode 由文件头声明）+ 编译产物加载。

* 手写文件（glossary/shared/*.tsv 与 glossary/local/*.tsv）一律两列 `旧词<TAB>新词`，
  `#` 开头为注释；整文件的匹配方式由文件头 `# mode: exact|sub` 声明（缺省 sub）。
  键为**繁体原文**，匹配发生在 OpenCC 转换**之前**——输入固定是繁体，译文按流程写
  简体（t2s）或繁体（t2t）。
* 加载顺序（编译时）：auto 条目 -> shared/*.tsv -> local/*.tsv，**后加载者优先**
  （dict.update 语义，直觉对应「自动 < 共享 < 个人」）；同一文件内重复键先出现者优先。
* 黑名单（shared/local/blacklist.txt）在编译期对一切来源过滤，见 commands/glossary.py。
* patch 端只读编译产物 compiled.tsv（四列：旧词/新词/mode/source），零合并逻辑。
* 模式语义：exact = 整字段相等才替换（只命中角色名字段，旬/希望 这类歧义短词也安全）；
  sub = 子串替换（单趟、最长键优先，与 `convert.py` 的匹配策略一致，避免 A->B 的
  结果再被 B->C 命中）；同名键 exact 优先。
"""
from __future__ import annotations

from dataclasses import dataclass, field

MODES = ("exact", "sub")
DEFAULT_MODE = "sub"


def parse_mode(path: str) -> str:
    """从文件头注释里解析 `# mode: exact|sub`（只看开头的注释块，缺省 sub）。"""
    mode: str | None = None
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line.startswith("#"):
                break  # 头部注释块结束，mode 只能声明在这里
            if line.startswith("# mode:"):
                declared = line.removeprefix("# mode:").strip().lower()
                if declared in MODES:
                    mode = declared
                else:
                    print(f"[glossary] {path} 未知 mode 声明 {declared!r}（应为 exact / sub），按 {DEFAULT_MODE} 处理")
    return mode or DEFAULT_MODE


def load_entries(path: str, mode: str) -> dict[str, str]:
    """读一份手写词表（两列），返回 旧词 -> 新词；重复键先出现者优先。

    恒等行（旧词 == 新词，模板里「待填」的占位）跳过：无实际改动，以免淹没命中日志。
    """
    entries: dict[str, str] = {}
    with open(path, encoding="utf-8-sig") as f:  # 允许 BOM（Excel 导出常见）
        for ln, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0].strip() or not parts[1]:
                print(f"[glossary] {path}:{ln} 跳过无效行 {line!r}（需要「旧词<TAB>新词」，分隔符是 Tab，不是空格）")
                continue
            old, new = parts[0].strip(), parts[1]
            if old == new:
                continue  # 恒等行：模板里「待填」的占位
            if old in entries:
                print(f"[glossary] {path}:{ln} 重复键 {old!r}，保留先出现的")
                continue
            entries[old] = new
    if entries:
        print(f"[glossary] {path} mode={mode} {len(entries)} 条")
    return entries


@dataclass
class Glossary:
    """双词表 + 逐规则命中计数（审计用）。"""
    exact_map: dict[str, str] = field(default_factory=dict)  # exact：旧词 -> 新词
    sub_map: dict[str, str] = field(default_factory=dict)    # sub：旧词 -> 新词
    hits: dict[tuple[str, str], int] = field(default_factory=dict)   # (旧词, mode) -> 命中次数
    sources: dict[tuple[str, str], str] = field(default_factory=dict)  # (旧词, mode) -> 来源（compiled.tsv 第 4 列）
    sub_maxlen: int = 0                                      # sub 键最大长度（匹配上界）

    @classmethod
    def from_compiled(cls, path: str) -> Glossary:
        """从编译产物 compiled.tsv（四列：旧词/新词/mode/source）加载；合并逻辑已在编译期完成。"""
        g = cls()
        with open(path, encoding="utf-8-sig") as f:
            for ln, raw in enumerate(f, 1):
                line = raw.rstrip("\r\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 3 or not parts[0].strip() or not parts[1]:
                    print(f"[glossary] {path}:{ln} 跳过无效行 {line!r}")
                    continue
                old, new, mode = parts[0].strip(), parts[1], parts[2].strip().lower()
                src = parts[3].strip() if len(parts) > 3 else ""
                if old == new:
                    continue  # 恒等行（未填写的脚手架）
                if mode not in MODES:
                    print(f"[glossary] {path}:{ln} 未知 mode {mode!r}，跳过")
                    continue
                target = g.exact_map if mode == "exact" else g.sub_map
                if old in target:  # 同一 mode 内先出现者优先；同名键允许跨表（exact/sub 各司其职）
                    print(f"[glossary] {path}:{ln} 重复键 {old!r}，保留先出现的")
                    continue
                target[old] = new
                if mode == "sub":
                    g.sub_maxlen = max(g.sub_maxlen, len(old))
                g.hits.setdefault((old, mode), 0)
                g.sources[(old, mode)] = src
        return g

    def apply(self, text: str) -> str:
        """先 exact（整字段相等），后 sub（单趟、最长键优先），并累计命中数。"""
        new = self.exact_map.get(text)
        if new is not None:
            self.hits[(text, "exact")] += 1
            return new
        if not self.sub_map:
            return text
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            for ln in range(min(n - i, self.sub_maxlen), 0, -1):
                seg = text[i:i + ln]
                new = self.sub_map.get(seg)
                if new is not None:
                    out.append(new)
                    self.hits[(seg, "sub")] += 1
                    i += ln
                    break
            else:
                out.append(text[i])
                i += 1
        return "".join(out)

    def apply_exact(self, text: str) -> str | None:
        """只做 exact 整字段匹配，不返回原文（无命中为 None）。

        纯 ASCII 字段（角色名的拉丁写法，如 "Kei"）专用：不做 sub，避免误伤资源路径与内部标识符。
        """
        new = self.exact_map.get(text)
        if new is not None:
            self.hits[(text, "exact")] += 1
        return new
