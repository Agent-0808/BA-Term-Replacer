"""glossary.py 的测试：TSV 加载、最长优先、级联防护与命中计数。"""
from batr.glossary import Glossary


def _load(lines: list[str]) -> Glossary:
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        path = f.name
    try:
        return Glossary.load([path])
    finally:
        os.remove(path)


def test_load_skips_comments_and_blanks() -> None:
    g = _load(["# 注释", "", "彌香\t未花"])
    assert g.rules == {"彌香": "未花"}


def test_apply_longest_first_and_single_pass() -> None:
    g = _load(["羽留奈\t晴奈", "旬\t瞬"])
    # 最长键优先：3 字键不被 1 字键拆开
    assert g.apply("与羽留奈对话") == "与晴奈对话"
    # 单趟：替换结果（瞬）不在键表里，不会被再次命中
    assert g.apply("旬間") == "瞬間"


def test_apply_counts_hits() -> None:
    g = _load(["彌香\t未花"])
    g.apply("彌香與彌香")
    assert g.hits["彌香"] == 2


def test_load_bom_and_duplicate_key() -> None:
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p1 = os.path.join(tmp, "a.tsv")
        p2 = os.path.join(tmp, "b.tsv")
        with open(p1, "w", encoding="utf-8-sig") as f:  # BOM
            f.write("彩奈\t阿罗娜\n")
        with open(p2, "w", encoding="utf-8") as f:
            f.write("彩奈\t别的\n星奈\t普拉娜\n")
        g = Glossary.load([p1, p2])
        assert g.rules["彩奈"] == "阿罗娜"  # 先出现者优先
        assert g.rules["星奈"] == "普拉娜"
