"""OpenCC 字典驱动的 繁 -> 简 转换（纯标准库，无第三方依赖）。

字典来自 [OpenCC](https://github.com/BYVoid/OpenCC) 的 `data/dictionary/*.txt`
（**Apache License 2.0**，原样复制于 `batr/data/`，许可证全文见 `data/LICENSE-OpenCC.txt`）。

两种模式：
  tw2sp (默认) : TWPhrasesRev + TSPhrases + TSCharacters
                 台湾繁体 -> 大陆简体，**含用词转换**（伺服器->服务器、影片->视频…）
  t2s          : TSPhrases + TSCharacters
                 只转字形，不转用词

算法：按 OpenCC 的"最长匹配优先"，词组表优先于单字表；同键时靠前的字典优先。
本文件是这套规则的**独立实现**（只读取 OpenCC 的词库数据，未复制其源代码）。
更多第三方署名见仓库根目录 `THIRD_PARTY.md`。
"""
from __future__ import annotations

from pathlib import Path

# 词库随包安装（package data）。
DATA_DIR = Path(__file__).resolve().parent / "data"

CHAIN: dict[str, tuple[str, ...]] = {
    "tw2sp": ("TWPhrasesRev.txt", "TSPhrases.txt", "TSCharacters.txt"),
    "t2s": ("TSPhrases.txt", "TSCharacters.txt"),
}


def load_dict(path: Path) -> dict[str, str]:
    """OpenCC 字典格式: `键<TAB>值1[ 值2...]`，# 开头为注释，第一个值优先。"""
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            key, val = parts[0], parts[1]
            if key and val and key != val:
                out.setdefault(key, val)
    return out


def _split(path: str, dict_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """把一个字典文件拆成 (词组表, 单字表)。"""
    phrases: dict[str, str] = {}
    chars: dict[str, str] = {}
    for key, val in load_dict(dict_dir / path).items():
        if len(key) > 1:
            phrases.setdefault(key, val)
        else:
            chars.setdefault(key, val)
    return phrases, chars


class Converter:
    """按 OpenCC 的方式**顺序**套用每一层字典：上一层的输出是下一层的输入。

    顺序很关键：TWPhrasesRev 会把「資料」换成「數據」，紧接着的单字层再把
    「數/據」转成「数/据」，最终才是大陆写法「数据」。合并成一次匹配就丢掉了后半步。
    """

    def __init__(self, mode: str = "tw2sp", dict_dir: Path = DATA_DIR) -> None:
        if mode not in CHAIN:
            raise ValueError(f"未知模式 {mode!r}，可选: {sorted(CHAIN)}")
        self.mode = mode
        # [(名称, 词组表, 单字表, 最长键长), ...]
        self.steps: list[tuple[str, dict[str, str], dict[str, str], int]] = []
        for name in CHAIN[mode]:
            phrases, chars = _split(name, dict_dir)
            self.steps.append(
                (name, phrases, chars, max((len(k) for k in phrases), default=1))
            )
        self.phrases = {k: v for _, p, _, _ in self.steps for k, v in p.items()}
        self.chars = {k: v for _, _, c, _ in self.steps for k, v in c.items()}

    @staticmethod
    def _one_step(
        text: str, phrases: dict[str, str], chars: dict[str, str], maxlen: int
    ) -> str:
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            hi = min(n, i + maxlen)
            matched = False
            for ln in range(hi - i, 1, -1):  # 最长匹配优先
                val = phrases.get(text[i : i + ln])
                if val is not None:
                    out.append(val)
                    i += ln
                    matched = True
                    break
            if matched:
                continue
            c = text[i]
            out.append(chars.get(c, c))
            i += 1
        return "".join(out)

    def convert(self, text: str) -> str:
        if not text:
            return text
        for _, phrases, chars, maxlen in self.steps:
            text = self._one_step(text, phrases, chars, maxlen)
        return text

    def convert_marked(self, text: str) -> tuple[str, bool]:
        """返回 (结果, 是否发生改变)。"""
        new = self.convert(text)
        return new, new != text
