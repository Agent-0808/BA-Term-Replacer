"""
从 BA-characters-internal-id 的 students.json
自动生成 KivoWiki（基沃托斯古书馆）简中民译角色名词表

用法：
    uv run python scripts/make_kivowiki_names.py [--refresh] [--no-text]

* 数据源：https://agent-0808.github.io/BA-characters-internal-id/data/students.json
  缓存到 work/students.json（--refresh 重新下载）。
* 输出两张表（**每次完整重新生成**，手工内容不在其中）：
    glossary/names.tsv  exact 整字段匹配（角色名字段，如剧情说话人栏）
    glossary/text.tsv   sub 子串匹配（正文里出现的角色名）
  手工补充/修正写单独文件（首次运行自动建空模板）：
    glossary/names.local.tsv / glossary/text.local.tsv（本地，不入库；加载时优先于自动表）
  想禁用某个自动键写黑名单（见下），不要靠注释自动表 —— 那属于本文件，重生成会丢。
* 黑名单（glossary/blacklist.txt 客观项入库共享、glossary/blacklist.local.txt 个人项不入库）：
  一行一个键，可选第二列限定生效表（names / text），不写则两表都禁用。
  例：`希望<TAB>text` 让整字段匹配照常生成、但正文子串替换不生成（避免误伤普通词）。
* 规则：键 = name_tw 的「名」段（空格分隔取最后一段）；值 = 民间简体名（name/name_cn
  中与 name_tw 空格结构一致者）的对应段。t2s 转换后已相等、空的键跳过。
  皮肤名（skin_tw -> skin）同理生成。上游分开姓/名字段后，改「名段切分」处即可。
* 纯 ASCII 键不再跳过（游戏里有 Kei / Ain / Aur / Soph 这类拉丁字母角色名，
  民译会换成汉字，需生成词条）；若某条 ASCII 键在正文替换有误伤风险，按需写进黑名单。
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

from batr.convert import Converter

URL = "https://agent-0808.github.io/BA-characters-internal-id/data/students.json"
CACHE = "work/students.json"
OUT_NAMES = "glossary/names.tsv"
OUT_TEXT = "glossary/text.tsv"
LOCAL_NAMES = "glossary/names.local.tsv"  # 手工角色名表（本地，不入库，优先级更高）
LOCAL_TEXT = "glossary/text.local.tsv"    # 手工正文替换表（本地，不入库，优先级更高）
BLACKLIST = "glossary/blacklist.txt"            # 客观禁用项（入库共享）
BLACKLIST_LOCAL = "glossary/blacklist.local.txt"  # 个人禁用项（本地，不入库）
BLACKLIST_LOCAL_HEADER = (
    "# 个人黑名单（本地，不入库）：一行一个繁体键，生成脚本导入 students.json 时跳过\n"
    "# 可选第二列限定生效表：names（只跳角色名表）/ text（只跳正文替换表），不写则两表都跳过\n"
    "# 客观通用词请写 glossary/blacklist.txt（入库共享）\n"
    "# 示例（去掉行首的 # 即生效）：\n"
    "#三森\n"
    "#戈爾孔特&轉印\n"
)
HEADER_NAMES = (
    "# 角色名表（exact 整字段匹配：整字段等于旧词才替换，只命中角色名字段，不误伤正文）\n"
    "# 本文件由 scripts/make_kivowiki_names.py 每次完整重新生成，请勿手工编辑\n"
    "# 手工补充/修正请写 glossary/names.local.tsv（本地，不入库，优先级更高）\n"
    "# 格式：繁体旧词<TAB>新词；# 开头为注释\n"
)
HEADER_TEXT = (
    "# 正文替换表（sub 子串匹配：字段文本包含旧词即替换，单趟、最长键优先不级联）\n"
    "# 本文件由 scripts/make_kivowiki_names.py 每次完整重新生成，请勿手工编辑\n"
    "# 手工补充/修正请写 glossary/text.local.tsv；地名/术语等通用词条写 glossary/terms.tsv（入库共享）\n"
    "# 格式：繁体旧词<TAB>新词（分隔符是 Tab，不是空格）；键写数据库里的繁体原文，写错即零命中（用 --dry-run 的 hits=0 排查）\n"
)
LOCAL_HEADER_NAMES = (
    "# 手工角色名表（本地，不入库）：exact 整字段匹配，加载时优先于自动生成的 glossary/names.tsv\n"
    "# 用于个人偏好的译名修正/补充；本文件不会被生成脚本覆盖\n"
    "# 格式：繁体旧词<TAB>新词（分隔符是 Tab，不是空格）\n"
)
LOCAL_HEADER_TEXT = (
    "# 手工正文替换表（本地，不入库）：sub 子串匹配，加载时优先于自动生成的 glossary/text.tsv\n"
    "# 用于个人偏好的译名修正/补充；地名/术语等通用词条建议写 glossary/terms.tsv（入库共享）\n"
    "# 格式：繁体旧词<TAB>新词（分隔符是 Tab，不是空格）\n"
)


def download(refresh: bool) -> list[dict]:
    if refresh or not os.path.exists(CACHE):
        print(f"下载 {URL} -> {CACHE}")
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with urllib.request.urlopen(URL) as resp, open(CACHE, "wb") as f:
            f.write(resp.read())
    with open(CACHE, encoding="utf-8") as f:
        return json.load(f)


def load_blacklist() -> tuple[set[str], set[str]]:
    """合并客观黑名单与个人黑名单（后者可能不存在），返回 (names 禁用键, text 禁用键)。

    格式：一行一个繁体键；可选第二列限定生效表（names / text），不写则两表都禁用。
    例：`希望<TAB>text` 表示整字段匹配仍生成、但正文子串替换不生成（避免误伤）。
    """
    names: set[str] = set()
    text: set[str] = set()
    for path in (BLACKLIST, BLACKLIST_LOCAL):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig") as f:
            for ln, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, scope = line.partition("\t")
                key, scope = key.strip(), scope.strip().lower()
                if not key:
                    continue
                if scope == "names":
                    names.add(key)
                elif scope == "text":
                    text.add(key)
                elif scope:
                    print(f"[blacklist] {path}:{ln} 未知范围 {scope!r}（应为 names / text），按两表禁用处理")
                    names.add(key)
                    text.add(key)
                else:
                    names.add(key)
                    text.add(key)
    return names, text


def ensure_local_blacklist() -> None:
    """首次运行时生成空的个人黑名单模板，避免用户不知道去哪配置。"""
    if os.path.exists(BLACKLIST_LOCAL):
        return
    os.makedirs(os.path.dirname(BLACKLIST_LOCAL), exist_ok=True)
    with open(BLACKLIST_LOCAL, "w", encoding="utf-8", newline="\n") as f:
        f.write(BLACKLIST_LOCAL_HEADER)
    print(f"已生成个人黑名单模板: {BLACKLIST_LOCAL}（空模板，按需取消注释添加）")


def ensure_local_tables() -> None:
    """首次运行时生成空的手工词表模板（不会被生成脚本覆盖）。"""
    for path, header in ((LOCAL_NAMES, LOCAL_HEADER_NAMES), (LOCAL_TEXT, LOCAL_HEADER_TEXT)):
        if os.path.exists(path):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(header)
        print(f"已生成手工词表模板: {path}（空模板，按需添加）")


def local_keys(path: str) -> set[str]:
    """读手工表里已有的键：这些键由用户自己维护，自动表不再生成（避免重复条目与加载告警）。"""
    if not os.path.exists(path):
        return set()
    keys: set[str] = set()
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#") or "\t" not in line:
                continue
            key = line.split("\t")[0].strip()
            if key:
                keys.add(key)
    return keys


def given(full: str) -> str:
    """「名段切分」：官方名带姓带空格（聖園 彌香），游戏文本只出现名 -> 取最后一段。"""
    return full.split()[-1] if " " in full.strip() else full.strip()


def fansub_full(tw: str, name: str, name_cn: str) -> str:
    """选简体全名字段：name_tw 带空格时优先取**同样带空格**的字段，否则切不出「名」段。

    上游数据空格不统一（如 初音 未來 -> name「初音未来」、name_cn「初音 未来」），
    直接取 name 会把整串当成名段，生成「未來 -> 初音未来」这种错误条目。
    """
    if " " in tw:
        for cand in (name, name_cn):
            if " " in cand:
                return cand
    return name or name_cn


def add_entry(
    target: dict[str, str],
    key: str,
    value: str,
    *,
    blocked: set[str],
    covered: set[str],
    conv: Converter,
    stats: dict[str, int],
    dup: dict[str, str],
) -> None:
    """按过滤规则加入一条自动条目（names 与 text 两表共用，差异只在各自的 blocked/covered 集合）。"""
    if not key or not value:
        stats["skip_empty"] += 1
    elif key in target:
        stats["conflict"] += 1
        dup[key] = value
    elif key in blocked:
        stats["skip_blacklist"] += 1
    elif key in covered:
        stats["skip_local"] += 1
    elif conv.convert(key) == value:
        stats["skip_opencc"] += 1
    else:
        target[key] = value


def write_table(path: str, header: str, auto: dict[str, str]) -> None:
    """完整重写：注释头 + 全部自动条目（文件里没有手工区，手工内容在 *.local.tsv）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        for old, new in auto.items():
            f.write(f"{old}\t{new}\n")
    print(f"输出: {path}（自动 {len(auto)} 条）")


def report(label: str, stats: dict[str, int], dup: dict[str, str]) -> None:
    print(f"  {label}: {stats}")
    if dup:
        print(f"  另有 {len(dup)} 个键重复出现（保留先出现的值，示例前 5）:")
        for key, value in list(dup.items())[:5]:
            print(f"    {key} -> {value}")


def build(
    students: list[dict],
    black_names: set[str],
    black_text: set[str],
    *,
    covered_names: set[str] | None = None,
    covered_text: set[str] | None = None,
    with_text: bool = True,
) -> tuple[dict[str, str], dict[str, str]]:
    """按规则生成两张自动表（键 = 繁体名，值 = 民间简体名）。

    covered_* = *.local.tsv 里已有的键：用户已手工维护，自动表不再生成同键。
    """
    conv = Converter("t2s")  # 只转字形，用于判断「OpenCC 已处理、无需词条」
    covered_names = covered_names or set()
    covered_text = covered_text or set()
    auto_names: dict[str, str] = {}
    auto_text: dict[str, str] = {}
    s_names = {"skip_blacklist": 0, "skip_local": 0, "skip_empty": 0,
               "skip_opencc": 0, "conflict": 0}
    s_text = dict.fromkeys(s_names, 0)
    dup_names: dict[str, str] = {}
    dup_text: dict[str, str] = {}

    def feed(key: str, value: str) -> None:
        add_entry(auto_names, key, value, blocked=black_names, covered=covered_names,
                  conv=conv, stats=s_names, dup=dup_names)
        if with_text:
            add_entry(auto_text, key, value, blocked=black_text, covered=covered_text,
                      conv=conv, stats=s_text, dup=dup_text)

    for st in students:
        tw = (st.get("name_tw") or "").strip()
        name = fansub_full(tw, (st.get("name") or "").strip(), (st.get("name_cn") or "").strip())
        if tw and name:
            given_tw = given(tw)
            feed(given_tw, given(name))
            # 全名连写规则（仅中日文姓名：游戏正文里姓与名连写；拉丁字母名正文保留空格）
            # 名段被黑名单禁用时，由它派生的全名一并禁用（否则「黑名单 三森」仍会替换 水羽三森）
            joined_tw = tw.replace(" ", "")
            if not joined_tw.isascii() and given_tw not in black_names:
                feed(joined_tw, name.replace(" ", ""))
        # 皮肤名：游戏里以「角色名(皮肤)」的内嵌形式出现（如 白子(單車)、瀬奈(私服)），
        # 正文表因此用**带括号的键**，只命中括号内的皮肤词，不误伤正文里的裸词（如單車）。
        for page in st.get("pages", []):
            skin_tw = (page.get("skin_tw") or "").strip()
            skin = (page.get("skin") or "").strip() or (page.get("skin_cn") or "").strip()
            if skin_tw and skin:
                feed(skin_tw, skin)  # names：整字段兜底（少数界面单独显示皮肤名）
                if with_text:
                    add_entry(auto_text, f"({skin_tw})", f"({skin})", blocked=black_text,
                              covered=covered_text, conv=conv, stats=s_text, dup=dup_text)

    report("names", s_names, dup_names)
    if with_text:
        report("text", s_text, dup_text)
    return auto_names, auto_text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重新下载 students.json")
    ap.add_argument("--no-text", action="store_true", help="只生成 names.tsv，不生成 text.tsv")
    args = ap.parse_args()

    students = download(args.refresh)
    ensure_local_blacklist()
    ensure_local_tables()
    black_names, black_text = load_blacklist()
    auto_names, auto_text = build(
        students, black_names, black_text,
        covered_names=local_keys(LOCAL_NAMES),
        covered_text=local_keys(LOCAL_TEXT),
        with_text=not args.no_text,
    )

    write_table(OUT_NAMES, HEADER_NAMES, auto_names)
    if not args.no_text:
        write_table(OUT_TEXT, HEADER_TEXT, auto_text)


if __name__ == "__main__":
    main()
