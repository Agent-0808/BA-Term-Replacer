"""临时脚本（早期方案，非正式代码）：从 BA-characters-internal-id 的 students.json 生成角色名表。

用法：
    uv run python scripts/make_names.py [--refresh]

* 数据源：https://agent-0808.github.io/BA-characters-internal-id/data/students.json
  缓存到 work/students.json（--refresh 重新下载）。
* 输出 glossary/names.tsv（exact 整字段匹配）；已有文件中的手工条目**自动保留**且优先。
* 黑名单 glossary/blacklist.txt：一行一个键，命中则不导入（用户手工维护）。
* 规则：键 = name_tw 的「名」段（空格分隔取最后一段）；值 = 民间简体名（name，
  空缺回退 name_cn）的对应段。t2s 转换后已相等、纯 ASCII、空的键跳过。
  皮肤名（skin_tw -> skin）同理生成。上游分开姓/名字段后，改「名段切分」处即可。
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

from batr.convert import Converter

URL = "https://agent-0808.github.io/BA-characters-internal-id/data/students.json"
CACHE = "work/students.json"
OUT = "glossary/names.tsv"
BLACKLIST = "glossary/blacklist.txt"
HEADER = (
    "# 角色名表（exact 整字段匹配：整字段等于旧词才替换，只命中角色名字段，不误伤正文）\n"
    "# 由 scripts/make_names.py 从 students.json 自动生成；手工条目直接加在文件里，重新生成时会保留并优先\n"
    "# 格式：繁体旧词<TAB>新词；# 开头为注释\n"
)


def download(refresh: bool) -> dict:
    if refresh or not os.path.exists(CACHE):
        print(f"下载 {URL} -> {CACHE}")
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with urllib.request.urlopen(URL) as resp, open(CACHE, "wb") as f:
            f.write(resp.read())
    with open(CACHE, encoding="utf-8") as f:
        return json.load(f)


def load_blacklist() -> set[str]:
    if not os.path.exists(BLACKLIST):
        return set()
    with open(BLACKLIST, encoding="utf-8-sig") as f:
        return {line.strip() for line in f
                if line.strip() and not line.lstrip().startswith("#")}


def load_manual() -> dict[str, str]:
    """旧 names.tsv 中已有的条目（视为手工，重新生成时保留并优先）。"""
    manual: dict[str, str] = {}
    if not os.path.exists(OUT):
        return manual
    with open(OUT, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].strip() and parts[1]:
                manual[parts[0].strip()] = parts[1]
    return manual


def given(full: str) -> str:
    """「名段切分」：官方名带姓带空格（聖園 彌香），游戏文本只出现名 -> 取最后一段。"""
    return full.split()[-1] if " " in full.strip() else full.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重新下载 students.json")
    args = ap.parse_args()

    students = download(args.refresh)
    blacklist = load_blacklist()
    manual = load_manual()
    conv = Converter("t2s")  # 只转字形，用于判断「OpenCC 已处理、无需词条」

    auto: dict[str, str] = {}
    stats = {"skip_opencc": 0, "skip_ascii": 0, "skip_blacklist": 0, "skip_empty": 0, "conflict": 0}
    dup: dict[str, str] = {}

    def add(key: str, value: str) -> None:
        if not key or not value:
            stats["skip_empty"] += 1
        elif key in manual or key in auto:
            stats["conflict"] += 1
            dup[key] = value
        elif key.isascii():
            stats["skip_ascii"] += 1
        elif key in blacklist:
            stats["skip_blacklist"] += 1
        elif conv.convert(key) == value:
            stats["skip_opencc"] += 1
        else:
            auto[key] = value

    for st in students:
        tw = (st.get("name_tw") or "").strip()
        name = (st.get("name") or "").strip() or (st.get("name_cn") or "").strip()
        if tw and name:
            add(given(tw), given(name))
            # 全名连写规则
            if " " in tw:
                add(tw.replace(" ", ""), name.replace(" ", ""))
        # 皮肤名（exact 无误伤风险；仅民间名与 t2s 不同时才需要词条）
        for page in st.get("pages", []):
            skin_tw = (page.get("skin_tw") or "").strip()
            skin = (page.get("skin") or "").strip() or (page.get("skin_cn") or "").strip()
            if skin_tw and skin:
                add(skin_tw, skin)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER)
        for old, new in manual.items():
            f.write(f"{old}\t{new}\n")
        for old, new in auto.items():
            f.write(f"{old}\t{new}\n")

    print(f"manual(保留)={len(manual)}  auto={len(auto)}  {stats}")
    if dup:
        print("冲突（保留先出现者）：")
        for k, v in dup.items():
            print(f"  {k} -> {v}")
    print(f"输出: {OUT}（共 {len(manual) + len(auto)} 条）")


if __name__ == "__main__":
    main()
