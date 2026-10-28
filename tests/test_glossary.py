"""glossary.py 的测试：双词表加载、exact 整字段 / sub 子串、最长优先与命中计数。"""
import os
import tempfile

from batr.glossary import Glossary


def _load(names: list[str], text: list[str]) -> Glossary:
    def write(lines: list[str]) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            return f.name

    n, t = write(names), write(text)
    try:
        return Glossary.load([n], [t])
    finally:
        os.remove(n)
        os.remove(t)


def test_load_skips_comments_and_blanks() -> None:
    g = _load(["# 注释", "", "彌香\t未花"], [])
    assert g.exact_map == {"彌香": "未花"} and g.sub_map == {}


def test_exact_whole_field_only() -> None:
    g = _load(["希望\t望", "旬\t瞬"], [])
    assert g.apply("希望") == "望"        # 整字段相等 -> 命中（角色名字段）
    assert g.apply("旬") == "瞬"
    # 嵌在句子/词语里的不算 -> 不误伤
    assert g.apply("抱有希望") == "抱有希望"
    assert g.apply("上旬です") == "上旬です"


def test_exact_takes_priority_then_sub() -> None:
    g = _load(["希望\t望"], ["希望\t願望", "抱有希望\t满怀希望"])
    assert g.apply("希望") == "望"           # exact 优先
    assert g.apply("抱有希望") == "满怀希望"  # 非 exact 命中走 sub


def test_sub_longest_first_and_single_pass() -> None:
    g = _load([], ["羽留奈\t晴奈", "旬\t瞬"])
    # 最长键优先：3 字键不被 1 字键拆开
    assert g.apply("与羽留奈对话") == "与晴奈对话"
    # 单趟：替换结果（瞬）不在键表里，不会被再次命中
    assert g.apply("旬間") == "瞬間"


def test_apply_counts_hits() -> None:
    g = _load(["彌香\t未花"], ["彌香\t未花"])
    g.apply("彌香與彌香")
    assert g.hits["彌香"] == 2  # 句中两处都走 sub


def test_duplicate_key_first_wins_across_files() -> None:
    def write(lines: list[str]) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            return f.name

    a, b = write(["彩奈\t阿罗娜"]), write(["彩奈\t别的", "星奈\t普拉娜"])
    try:
        g = Glossary.load([a, b], [])
        assert g.exact_map["彩奈"] == "阿罗娜"  # 先出现者优先
        assert g.exact_map["星奈"] == "普拉娜"
    finally:
        os.remove(a)
        os.remove(b)


def test_load_bom_and_invalid_lines() -> None:
    def write(content: str, encoding: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding=encoding) as f:
            f.write(content)
            return f.name

    a = write("\ufeff星奈\t普拉娜\n坏行\n", "utf-8")  # BOM + 无 TAB 的无效行
    try:
        g = Glossary.load([a], [])
        assert g.exact_map == {"星奈": "普拉娜"}
    finally:
        os.remove(a)
