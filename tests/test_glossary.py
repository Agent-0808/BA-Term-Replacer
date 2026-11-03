"""glossary.py 的测试：行级 mode 游标加载、exact 整字段 / sub 子串、最长优先与命中计数。"""
import os
import tempfile
from pathlib import Path

from batr.glossary import Glossary, load_entries


def _write(lines: list[str], encoding: str = "utf-8") -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding=encoding) as f:
        f.write("\n".join(lines) + "\n")
        return f.name


def _compiled(rows: list[str]) -> Glossary:
    """用四列格式（旧词/新词/mode/source）的临时产物构造 Glossary。"""
    path = _write(rows)
    try:
        return Glossary.from_compiled(path)
    finally:
        os.remove(path)


def test_load_entries_mode_blocks() -> None:
    # 行级游标：文件头声明 + 中途切换，同一文件分块混用两种 mode
    path = _write([
        "# mode: exact",
        "彌香\t未花",
        "# mode: sub",
        "希望\t願望",
        "# mode: exact",
        "旬\t瞬",
    ])
    try:
        groups = load_entries(path)
    finally:
        os.remove(path)
    assert groups == {"exact": {"彌香": "未花", "旬": "瞬"}, "sub": {"希望": "願望"}}


def test_load_entries_defaults_and_identity() -> None:
    # 无声明按 sub；恒等行（待填占位）与无效行跳过；同 mode 重复键先出现者优先
    path = _write(["星奈\t普拉娜", "待填\t待填", "坏行", "彩奈\t阿罗娜", "彩奈\t别的"])
    try:
        groups = load_entries(path)
    finally:
        os.remove(path)
    assert groups == {"sub": {"星奈": "普拉娜", "彩奈": "阿罗娜"}}


def test_load_entries_unknown_mode_keeps_cursor() -> None:
    path = _write(["# mode: exact", "彌香\t未花", "# mode: typo", "希望\t願望"])
    try:
        groups = load_entries(path)
    finally:
        os.remove(path)
    # 未知声明告警并保持游标，希望 仍归 exact
    assert groups == {"exact": {"彌香": "未花", "希望": "願望"}}


def test_load_entries_bom() -> None:
    path = _write(["\ufeff星奈\t普拉娜"], "utf-8")  # BOM（Excel 导出常见）
    try:
        groups = load_entries(path)
    finally:
        os.remove(path)
    assert groups == {"sub": {"星奈": "普拉娜"}}


def test_exact_whole_field_only() -> None:
    g = _compiled(["希望\t望\texact\tx", "旬\t瞬\texact\tx"])
    assert g.apply("希望") == "望"        # 整字段相等 -> 命中（角色名字段）
    assert g.apply("旬") == "瞬"
    # 嵌在句子/词语里的不算 -> 不误伤
    assert g.apply("抱有希望") == "抱有希望"
    assert g.apply("上旬です") == "上旬です"


def test_exact_takes_priority_then_sub() -> None:
    g = _compiled(["希望\t望\texact\tx", "希望\t願望\tsub\tx", "抱有希望\t满怀希望\tsub\tx"])
    assert g.apply("希望") == "望"           # exact 优先
    assert g.apply("抱有希望") == "满怀希望"  # 非 exact 命中走 sub


def test_sub_longest_first_and_single_pass() -> None:
    g = _compiled(["羽留奈\t晴奈\tsub\tx", "旬\t瞬\tsub\tx"])
    # 最长键优先：3 字键不被 1 字键拆开
    assert g.apply("与羽留奈对话") == "与晴奈对话"
    # 单趟：替换结果（瞬）不在键表里，不会被再次命中
    assert g.apply("旬間") == "瞬間"


def test_apply_counts_hits() -> None:
    g = _compiled(["彌香\t未花\texact\tx", "彌香\t未花\tsub\tx"])
    g.apply("彌香與彌香")
    assert g.hits[("彌香", "sub")] == 2  # 句中两处都走 sub


def test_apply_exact_ascii_only() -> None:
    g = _compiled(["Kei\t凯\texact\tx"])
    assert g.apply_exact("Kei") == "凯"
    assert g.apply_exact("Kei") == "凯"   # 重复调用仍命中（计数继续累加）
    assert g.apply("some/Kei/path") == "some/Kei/path"  # sub 不参与，路径安全


def test_compiled_duplicate_key_first_wins() -> None:
    # 产物内同 mode 重复键先出现者优先（编译端跨文件覆盖在 commands 层，见其编译测试）
    g = _compiled(["彩奈\t阿罗娜\texact\ta", "彩奈\t别的\texact\tb"])
    assert g.exact_map["彩奈"] == "阿罗娜"


def test_write_identity_rows_appends_with_mode_header(tmp_path: Path) -> None:
    from batr.commands.glossary import write_identity_rows

    path = tmp_path / "mixed.tsv"
    path.write_text("# mode: exact\n甲\t甲\n# mode: sub\n乙\t乙\n", encoding="utf-8")
    # 向 exact 补脚手架：文件末尾停在 sub 块，追加前必须补 `# mode: exact` 头
    write_identity_rows(path, "exact", ["甲", "丙"], existing=set())
    assert path.read_text(encoding="utf-8") == "# mode: exact\n甲\t甲\n# mode: sub\n乙\t乙\n# mode: exact\n丙\t丙\n"

    # 已处于本 mode 时直接追加，不重复声明；非本 mode 的恒等行（甲）不受本次 valid 集合影响
    write_identity_rows(path, "sub", ["乙", "丁"], existing=set())
    assert path.read_text(encoding="utf-8") == (
        "# mode: exact\n甲\t甲\n# mode: sub\n乙\t乙\n# mode: exact\n丙\t丙\n# mode: sub\n丁\t丁\n"
    )


def test_write_identity_rows_prunes_stale_only_in_mode(tmp_path: Path) -> None:
    from batr.commands.glossary import write_identity_rows

    path = tmp_path / "mixed.tsv"
    path.write_text("# mode: exact\n旧名\t旧名\n# mode: sub\n旧词\t旧词\n", encoding="utf-8")
    # 只对 exact 块做脚手架：exact 的陈旧恒等行被删，sub 块的「旧词」保留
    write_identity_rows(path, "exact", ["新名"], existing=set())
    text = path.read_text(encoding="utf-8")
    assert "旧名" not in text
    assert "旧词\t旧词" in text
    assert "新名\t新名" in text
