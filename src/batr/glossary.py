"""译名对照表（TSV）的加载与匹配 —— 阶段 C 的最小实现。

与设计文档 §5.2 的差异（2026-10-28 按用户要求调整）：
* 键写**繁体原文**，匹配发生在 OpenCC 转换**之前**——输入固定是繁体，
  译文直接写简体；译文再过一遍 OpenCC 基本无变化（专有名词不在用词表内）。
* 每行两列 `旧词<TAB>新词`，`#` 开头为注释；匹配为子串替换、单趟最长键优先
  （与 `convert.py` 的匹配策略一致，避免 A->B 的结果再被 B->C 命中）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Glossary:
    """一组译名替换规则，附带逐规则命中计数（审计用）。"""
    rules: dict[str, str] = field(default_factory=dict)  # 旧词 -> 新词
    hits: dict[str, int] = field(default_factory=dict)   # 旧词 -> 命中次数
    maxlen: int = 0                                      # 最长旧词长度（匹配上界）

    @classmethod
    def load(cls, paths: list[str]) -> Glossary:
        """按顺序加载多个 TSV；重复键先出现者优先并警告。"""
        g = cls()
        for path in paths:
            g._load_file(path)
        return g

    def _load_file(self, path: str) -> None:
        with open(path, encoding="utf-8-sig") as f:  # 允许 BOM（Excel 导出常见）
            for ln, raw in enumerate(f, 1):
                line = raw.rstrip("\r\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 2 or not parts[0].strip() or not parts[1]:
                    print(f"[glossary] {path}:{ln} 跳过无效行（需要两列：旧词<TAB>新词）")
                    continue
                old, new = parts[0].strip(), parts[1]
                if old in self.rules:
                    print(f"[glossary] {path}:{ln} 重复键 {old!r}，保留先出现的")
                    continue
                self.rules[old] = new
                self.hits.setdefault(old, 0)
                self.maxlen = max(self.maxlen, len(old))

    def apply(self, text: str) -> str:
        """单趟、最长键优先的子串替换，并累计命中数。"""
        if not self.rules:
            return text
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            for ln in range(min(n - i, self.maxlen), 0, -1):
                seg = text[i:i + ln]
                new = self.rules.get(seg)
                if new is not None:
                    out.append(new)
                    self.hits[seg] += 1
                    i += ln
                    break
            else:
                out.append(text[i])
                i += 1
        return "".join(out)
