"""生成「自制词表」模板：繁中 -> 民译（用户自己填写）。

用法：
    uv run python scripts/make_name_template.py [--refresh]

* 数据源同 make_kivowiki_names.py（kivowiki 古书馆 students.json，缓存 work/students.json）。
* 输出 glossary/names_custom.tsv（exact 整字段匹配）：
  key 列 = 繁体原名（名段 / 全名连写 / 皮肤名），value 列默认**与 key 相同**（恒等行），
  用户直接把右列改成自己的繁体民译名即可，不用自己想 key 怎么写。
  右列与左列相同的行视为「未填写」，glossary 加载时自动跳过，不会产生任何替换。
* 输出 glossary/text_custom.tsv（sub 子串匹配）：纯空模板（只有注释头，不存在时才创建），
  用于地名/术语等正文替换（如 奇普托斯 -> 基沃托斯），内容全部手写。
* 已有文件不重写：原内容逐行保留，只把数据源里新增的键补到末尾。
  想排除某个自动键，加入 glossary/blacklist.local.txt（个人）或 glossary/blacklist.txt（客观共享）。
* 运行（繁->繁）：batr patch <db> --convert none \\
      --names glossary/names_custom.tsv --text glossary/text_custom.tsv
"""
from __future__ import annotations

import argparse
import os

from make_kivowiki_names import download, ensure_local_blacklist, fansub_full, given, load_blacklist

OUT_NAMES = "glossary/names_custom.tsv"
OUT_TEXT = "glossary/text_custom.tsv"
HEADER_NAMES = (
    "# 自制角色名表（繁 -> 繁 民译；exact 整字段匹配：整个字段等于左列才替换）\n"
    "# 用法：直接把右列改成你的繁体民译名；右列与左列相同的行 = 未填写，加载时自动跳过\n"
    "# 分隔符是 Tab（制表符）不是空格；在 Excel 里编辑后另存为「文本文件(制表符分隔)」即可\n"
    "# 想排除某个键请加入 glossary/blacklist.local.txt（删掉行会被重新生成复活）\n"
)
HEADER_TEXT = (
    "# 自制正文替换表（繁 -> 繁 民译；sub 子串匹配：字段文本包含左列即替换，单趟、最长键优先不级联）\n"
    "# 用法：一行一条「繁体原文<TAB>你的繁体译文」，例如：奇普托斯<TAB>基沃托斯\n"
    "# 只放确定无歧义的词条；角色名建议优先放 names_custom.tsv（exact 整字段匹配）\n"
    "# 分隔符是 Tab（制表符）不是空格；内容和注释均手工维护\n"
)


def collect_keys(students: list[dict], blacklist: set[str]) -> list[str]:
    """与 make_kivowiki_names 相同的数据切分（名段 / 全名连写 / 皮肤名），按出现顺序去重。"""
    keys: dict[str, None] = {}
    for st in students:
        tw = (st.get("name_tw") or "").strip()
        name = fansub_full(tw, (st.get("name") or "").strip(), (st.get("name_cn") or "").strip())
        if tw and name:
            given_tw = given(tw)
            keys.setdefault(given_tw, None)
            # 名段被黑名单禁用时同时略过其全名（与 make_kivowiki_names 的生成规则一致）
            joined_tw = tw.replace(" ", "")
            if not joined_tw.isascii() and given_tw not in blacklist:
                keys.setdefault(joined_tw, None)
        for page in st.get("pages", []):
            skin_tw = (page.get("skin_tw") or "").strip()
            skin = (page.get("skin") or "").strip() or (page.get("skin_cn") or "").strip()
            if skin_tw and skin:
                keys.setdefault(skin_tw, None)
    return [k for k in keys if k and k not in blacklist]


def write_names(path: str, keys: list[str]) -> None:
    """恒等行模板：已有内容逐行保留，只补新增键；未填写的（恒等）行若已不在生成集合里则删除。"""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            lines = [ln.rstrip("\r\n") for ln in f]
    else:
        lines = HEADER_NAMES.rstrip("\n").split("\n")
    valid = set(keys)
    kept: list[str] = []
    present: set[str] = set()
    pruned = 0
    for line in lines:
        if "\t" not in line or line.lstrip().startswith("#"):
            kept.append(line)
            continue
        key, value = line.split("\t")[:2]
        key = key.strip()
        if key and key not in valid and key == value:
            pruned += 1  # 未填写的恒等行 + 键已不在生成集合（黑名单等）-> 删除，避免模板里留陈旧条目
            continue
        kept.append(line)
        if key:
            present.add(key)
    added = 0
    for key in keys:
        if key not in present:
            kept.append(f"{key}\t{key}")
            present.add(key)
            added += 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for line in kept:
            f.write(f"{line}\n")
    print(f"输出: {path}（共 {len(present)} 条，新增 {added} 条，清理陈旧恒等行 {pruned} 条）")


def write_text(path: str) -> None:
    """空模板：已存在则不动（用户内容不能被覆盖）。"""
    if os.path.exists(path):
        print(f"已存在，跳过: {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER_TEXT)
    print(f"输出: {path}（空模板，内容手写）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重新下载 students.json")
    args = ap.parse_args()

    students = download(args.refresh)
    ensure_local_blacklist()
    black_names, _ = load_blacklist()  # 模板只生成角色名表，取 names 范围
    write_names(OUT_NAMES, collect_keys(students, black_names))
    write_text(OUT_TEXT)


if __name__ == "__main__":
    main()
