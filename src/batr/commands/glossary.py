# commands/glossary.py
"""glossary 子命令：词表生成（自动表 / 自制模板两种模式）。

自动表模式（默认，繁→简流程）：
    uv run batr glossary [--refresh] [--no-text]
* 数据源：KivoWiki 民译，经 BA-characters-internal-id 分发：
    students.json  姓名（姓/名已分离为 family_name_* / given_name_* 字段）
    skin_map.json  皮肤基名的各语言译名（键 = 简中基名）
  缓存到 work/BACII_students.json / work/BACII_skin_map.json（--refresh 重新下载；
  旧格式缓存 —— 无 given_name_tw 字段 —— 视为过期自动重下）。
* 输出两张表（**每次完整重新生成**，手工内容不在其中）：
    glossary/names.tsv  exact 整字段匹配（角色名字段，如剧情说话人栏）
    glossary/text.tsv   sub 子串匹配（正文里出现的角色名）
  手工补充/修正写单独文件（首次运行自动建空模板）：
    glossary/names.local.tsv / glossary/text.local.tsv（本地，不入库；加载时优先于自动表）
  想禁用某个自动键写黑名单（见下），不要靠注释自动表 —— 注释会随重生成丢失。
* 黑名单（glossary/blacklist.txt 客观项入库共享、glossary/blacklist.local.txt 个人项不入库）：
  一行一个键，可选第二列限定生效表（names / text），不写则两表都禁用。
  例：`希望<TAB>text` 让整字段匹配照常生成、但正文子串替换不生成（避免误伤普通词）。
* 规则：键 = kivo 繁中字段（given_name_tw 名段 / family_name_tw+given_name_tw 全名连写）；
  值 = kivo 无后缀字段（given_name / family_name，即简中民译；kivo 字段必定有值）。
  t2s 转换后已相等、空的键跳过。
* 皮肤词条完全来自 skin_map.json：键（简中基名）为值、tw 字段（繁中基名）为键。
  text 表用带括号的键（如 (單車) -> (骑行服)），只命中「角色名(皮肤)」复合串，
  不误伤正文里的裸词（如單車）。
* 纯 ASCII 键不再跳过（游戏里有 Kei / Ain / Aur / Soph 这类拉丁字母角色名，
  民译会换成汉字，需生成词条）；若某条 ASCII 键在正文替换有误伤风险，按需写进黑名单。

模板模式（--template，繁→繁民译流程）：
    uv run batr glossary --template [--refresh]
* 数据源同自动表（students.json + skin_map.json）。
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

import json
import os
import urllib.request

from ..config import (
    DEFAULT_NAMES_GLOSSARY,
    DEFAULT_NAMES_LOCAL,
    DEFAULT_TEXT_GLOSSARY,
    DEFAULT_TEXT_LOCAL,
)
from ..convert import Converter
from .base import BaseTap

URL = "https://agent-0808.github.io/BA-characters-internal-id/data/students.json"
SKIN_MAP_URL = "https://agent-0808.github.io/BA-characters-internal-id/data/skin_map.json"
CACHE = "work/BACII_students.json"         # BACII（BA-characters-internal-id）students.json 缓存
CACHE_SKIN_MAP = "work/BACII_skin_map.json"  # BACII skin_map.json 缓存
OUT_NAMES = DEFAULT_NAMES_GLOSSARY          # glossary/names.tsv
OUT_TEXT = DEFAULT_TEXT_GLOSSARY            # glossary/text.tsv
LOCAL_NAMES = DEFAULT_NAMES_LOCAL           # 手工角色名表（本地，不入库，优先级更高）
LOCAL_TEXT = DEFAULT_TEXT_LOCAL             # 手工正文替换表（本地，不入库，优先级更高）
OUT_NAMES_CUSTOM = "glossary/names_custom.tsv"  # 自制角色名表（繁 -> 繁 民译恒等行模板）
OUT_TEXT_CUSTOM = "glossary/text_custom.tsv"    # 自制正文替换表（繁 -> 繁 民译，全手写）
BLACKLIST = "glossary/blacklist.txt"            # 客观禁用项（入库共享）
BLACKLIST_LOCAL = "glossary/blacklist.local.txt"  # 个人禁用项（本地，不入库）
BLACKLIST_LOCAL_HEADER = (
    "# 个人黑名单（本地，不入库）：一行一个繁体键，生成时跳过\n"
    "# 可选第二列限定生效表：names（只跳角色名表）/ text（只跳正文替换表），不写则两表都跳过\n"
    "# 客观通用词请写 glossary/blacklist.txt（入库共享）\n"
    "# 示例（去掉行首的 # 即生效）：\n"
    "#鹿江\n"
    "#三森\n"
)
HEADER_NAMES = (
    "# 角色名表（exact 整字段匹配：整字段等于旧词才替换，只命中角色名字段，不误伤正文）\n"
    "# 本文件由 batr glossary 每次完整重新生成，请勿手工编辑\n"
    "# 手工补充/修正请写 glossary/names.local.tsv（本地，不入库，优先级更高）\n"
    "# 格式：繁体旧词<TAB>新词；# 开头为注释\n"
)
HEADER_TEXT = (
    "# 正文替换表（sub 子串匹配：字段文本包含旧词即替换，单趟、最长键优先不级联）\n"
    "# 本文件由 batr glossary 每次完整重新生成，请勿手工编辑\n"
    "# 手工补充/修正请写 glossary/text.local.tsv；地名/术语等通用词条写 glossary/terms.tsv（入库共享）\n"
    "# 格式：繁体旧词<TAB>新词（分隔符是 Tab，不是空格）；键写数据库里的繁体原文，写错即零命中（用 --dry-run 的 hits=0 排查）\n"
)
LOCAL_HEADER_NAMES = (
    "# 手工角色名表（本地，不入库）：exact 整字段匹配，加载时优先于自动生成的 glossary/names.tsv\n"
    "# 用于个人偏好的译名修正/补充；本文件不会被生成覆盖\n"
    "# 格式：繁体旧词<TAB>新词（分隔符是 Tab，不是空格）\n"
)
LOCAL_HEADER_TEXT = (
    "# 手工正文替换表（本地，不入库）：sub 子串匹配，加载时优先于自动生成的 glossary/text.tsv\n"
    "# 用于个人偏好的译名修正/补充；地名/术语等通用词条建议写 glossary/terms.tsv（入库共享）\n"
    "# 格式：繁体旧词<TAB>新词（分隔符是 Tab，不是空格）\n"
)
CUSTOM_HEADER_NAMES = (
    "# 自制角色名表（繁 -> 繁 民译；exact 整字段匹配：整个字段等于左列才替换）\n"
    "# 用法：直接把右列改成你的繁体民译名；右列与左列相同的行 = 未填写，加载时自动跳过\n"
    "# 分隔符是 Tab（制表符）不是空格；在 Excel 里编辑后另存为「文本文件(制表符分隔)」即可\n"
    "# 想排除某个键请加入 glossary/blacklist.local.txt（删掉行会被重新生成复活）\n"
)
CUSTOM_HEADER_TEXT = (
    "# 自制正文替换表（繁 -> 繁 民译；sub 子串匹配：字段文本包含左列即替换，单趟、最长键优先不级联）\n"
    "# 用法：一行一条「繁体原文<TAB>你的繁体译文」，例如：奇普托斯<TAB>基沃托斯\n"
    "# 只放确定无歧义的词条；角色名建议优先放 names_custom.tsv（exact 整字段匹配）\n"
    "# 分隔符是 Tab（制表符）不是空格；内容和注释均手工维护\n"
)


class GlossaryTap(BaseTap):
    """词表生成：自动表（默认）或自制模板（--template）。"""

    template: bool = False  # 生成自制词表模板（繁->繁民译用）而不是自动表
    refresh: bool = False  # 强制重新下载 kivo 数据（students.json / skin_map.json）
    no_text: bool = False  # 只生成 names 表，不生成 text 表（仅自动表模式）


def fetch_json(url: str, cache: str, refresh: bool) -> list | dict:
    if refresh or not os.path.exists(cache):
        print(f"下载 {url} -> {cache}")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with urllib.request.urlopen(url) as resp, open(cache, "wb") as f:
            f.write(resp.read())
    with open(cache, encoding="utf-8") as f:
        return json.load(f)


def download(refresh: bool) -> tuple[list[dict], dict[str, dict]]:
    """拉取 kivo 数据：返回 (students, skin_map)。旧格式缓存（无 given_name_tw）自动重下。"""
    students = fetch_json(URL, CACHE, refresh)
    if students and "given_name_tw" not in students[0]:
        print("检测到旧格式缓存（姓名未分离），重新下载")
        students = fetch_json(URL, CACHE, True)
    skin_map = fetch_json(SKIN_MAP_URL, CACHE_SKIN_MAP, refresh)
    return students, skin_map


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
    """首次运行时生成空的手工词表模板（不会被生成覆盖）。"""
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
    skin_map: dict[str, dict],
    black_names: set[str],
    black_text: set[str],
    *,
    covered_names: set[str] | None = None,
    covered_text: set[str] | None = None,
    with_text: bool = True,
) -> tuple[dict[str, str], dict[str, str]]:
    """按规则生成两张自动表（键 = kivo 繁中名，值 = kivo 简中民译）。

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
        family_tw = (st.get("family_name_tw") or "").strip()
        given_tw = (st.get("given_name_tw") or "").strip()
        if not family_tw and not given_tw:
            continue
        # 名段：游戏文本只出现名（kivo 字段必定有值；无姓角色全名即名段）
        feed(given_tw, (st.get("given_name") or "").strip())
        # 全名连写（仅非拉丁姓名：游戏正文里姓与名连写）；
        # 名段被黑名单禁用时，由它派生的全名一并禁用（否则「黑名单 三森」仍会替换 水羽三森）
        joined_tw = family_tw + given_tw
        if family_tw and not joined_tw.isascii() and given_tw not in black_names:
            feed(joined_tw, (st.get("family_name") or "").strip() + (st.get("given_name") or "").strip())

    # 皮肤词条：完全来自 kivo skin_map（键 = 简中基名，tw = 繁中基名）。
    # text 表用带括号的键（如 (單車) -> (骑行服)），只命中「角色名(皮肤)」复合串，
    # 不误伤正文里的裸词（如單車）。
    for base, loc in skin_map.items():
        skin_tw = (loc.get("tw") or "").strip()
        if not skin_tw:
            continue
        feed(skin_tw, base)  # names：整字段兜底（少数界面单独显示皮肤名）
        if with_text:
            add_entry(auto_text, f"({skin_tw})", f"({base})", blocked=black_text,
                      covered=covered_text, conv=conv, stats=s_text, dup=dup_text)

    report("names", s_names, dup_names)
    if with_text:
        report("text", s_text, dup_text)
    return auto_names, auto_text


def collect_keys(students: list[dict], skin_map: dict[str, dict], blacklist: set[str]) -> list[str]:
    """与自动表相同的数据切分（名段 / 全名连写 / 皮肤名），按出现顺序去重（模板模式用）。"""
    keys: dict[str, None] = {}
    for st in students:
        family_tw = (st.get("family_name_tw") or "").strip()
        given_tw = (st.get("given_name_tw") or "").strip()
        if not family_tw and not given_tw:
            continue
        keys.setdefault(given_tw, None)
        # 名段被黑名单禁用时同时略过其全名（与自动表的生成规则一致）
        joined_tw = family_tw + given_tw
        if family_tw and not joined_tw.isascii() and given_tw not in blacklist:
            keys.setdefault(joined_tw, None)
    for loc in skin_map.values():
        skin_tw = (loc.get("tw") or "").strip()
        if skin_tw:
            keys.setdefault(skin_tw, None)
    return [k for k in keys if k and k not in blacklist]


def write_names_custom(path: str, keys: list[str]) -> None:
    """恒等行模板：已有内容逐行保留，只补新增键；未填写的（恒等）行若已不在生成集合里则删除。"""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            lines = [ln.rstrip("\r\n") for ln in f]
    else:
        lines = CUSTOM_HEADER_NAMES.rstrip("\n").split("\n")
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


def write_text_custom(path: str) -> None:
    """空模板：已存在则不动（用户内容不能被覆盖）。"""
    if os.path.exists(path):
        print(f"已存在，跳过: {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(CUSTOM_HEADER_TEXT)
    print(f"输出: {path}（空模板，内容手写）")


def handle_glossary(args: GlossaryTap) -> int:
    """处理 glossary 子命令（args 为合并了子命令属性的主 namespace）。"""
    students, skin_map = download(args.refresh)
    ensure_local_blacklist()
    if args.template:
        black_names, _ = load_blacklist()  # 模板只生成角色名表，取 names 范围
        write_names_custom(OUT_NAMES_CUSTOM, collect_keys(students, skin_map, black_names))
        write_text_custom(OUT_TEXT_CUSTOM)
        return 0
    ensure_local_tables()
    black_names, black_text = load_blacklist()
    auto_names, auto_text = build(
        students, skin_map, black_names, black_text,
        covered_names=local_keys(LOCAL_NAMES),
        covered_text=local_keys(LOCAL_TEXT),
        with_text=not args.no_text,
    )
    write_table(OUT_NAMES, HEADER_NAMES, auto_names)
    if not args.no_text:
        write_table(OUT_TEXT, HEADER_TEXT, auto_text)
    return 0
