"""译名对照表：names.tsv（角色名，exact 整字段匹配）+ text.tsv（正文，sub 子串匹配）。

* 模式由文件决定：`names` 表整字段相等才替换（只命中角色名字段，旬/希望 这类
  歧义短词也安全）；`text` 表做子串替换（单趟、最长键优先，与 `convert.py`
  的匹配策略一致，避免 A->B 的结果再被 B->C 命中）。
* TSV 格式：`旧词<TAB>新词`，`#` 开头为注释；键为**繁体原文**，匹配发生在
  OpenCC 转换**之前**——输入固定是繁体，译文直接写简体。
* 匹配顺序：先 names（exact），后 text（sub）；同名键 exact 优先。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Glossary:
    """双词表 + 逐规则命中计数（审计用）。"""
    exact_map: dict[str, str] = field(default_factory=dict)  # names.tsv：旧词 -> 新词
    sub_map: dict[str, str] = field(default_factory=dict)    # text.tsv：旧词 -> 新词
    hits: dict[str, int] = field(default_factory=dict)       # 旧词 -> 命中次数
    sub_maxlen: int = 0                                      # sub 键最大长度（匹配上界）

    @classmethod
    def load(cls, names: list[str], text: list[str]) -> Glossary:
        """按顺序加载；names 全部 exact，text 全部 sub；重复键先出现者优先。"""
        g = cls()
        for path in names:
            g._load_file(path, exact=True)
        for path in text:
            g._load_file(path, exact=False)
        return g

    def _load_file(self, path: str, *, exact: bool) -> None:
        target = self.exact_map if exact else self.sub_map
        with open(path, encoding="utf-8-sig") as f:  # 允许 BOM（Excel 导出常见）
            for ln, raw in enumerate(f, 1):
                line = raw.rstrip("\r\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 2 or not parts[0].strip() or not parts[1]:
                    print(f"[glossary] {path}:{ln} 跳过无效行（需要：旧词<TAB>新词）")
                    continue
                old, new = parts[0].strip(), parts[1]
                if old in target:  # 同一张表内先出现者优先；同名键允许跨表（exact/sub 各司其职）
                    print(f"[glossary] {path}:{ln} 重复键 {old!r}，保留先出现的")
                    continue
                target[old] = new
                self.hits.setdefault(old, 0)
                if not exact:
                    self.sub_maxlen = max(self.sub_maxlen, len(old))

    def apply(self, text: str) -> str:
        """先 exact（整字段相等），后 sub（单趟、最长键优先），并累计命中数。"""
        new = self.exact_map.get(text)
        if new is not None:
            self.hits[text] += 1
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
                    self.hits[seg] += 1
                    i += ln
                    break
            else:
                out.append(text[i])
                i += 1
        return "".join(out)
