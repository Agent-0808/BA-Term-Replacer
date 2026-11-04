# commands/glossary.py
"""glossary 子命令：词表编译器（数据源 + 手写词表 + 黑名单 → compiled.tsv）。

    uv run batr glossary [--profile t2s|t2t] [--template] [--refresh]

* 数据源：KivoWiki 民译，经 BA-characters-internal-id 分发：
    students.json  姓名（姓/名已分离为 family_name_* / given_name_* 字段）
    skin_map.json  皮肤基名的各语言译名（键 = 简中基名）
  缓存到 work/BACII_students.json / work/BACII_skin_map.json（--refresh 重新下载；
  旧格式缓存 —— 无 given_name_tw 字段 —— 视为过期自动重下）。
* auto 条目规则（仅 t2s profile 编入；键 = kivo 繁中字段，值 = kivo 简中民译）：
    名段 / 全名连写（仅非拉丁姓名） -> exact（角色名字段）+ sub（正文里出现的角色名）
    皮肤名 -> exact（整字段兜底）；正文 sub 用带括号的键（如 (單車) -> (骑行服)），
    只命中「角色名(皮肤)」复合串，不误伤正文里的裸词（如單車）。
  t2s 转换后已相等、空的键跳过；纯 ASCII 键保留（游戏里有 Kei / Ain 这类拉丁名）。
* 手写词表：glossary/shared/*.tsv（客观共识，入库可 PR）与 glossary/local/*.tsv
  （个人偏好，不入库）全部扫描，匹配方式由注释行 `# mode: exact|sub|re` 声明
  （文件头为第一段缺省值，文件中间可切换、分块混用多种 mode）。
  加载顺序 auto -> shared -> local，后加载者优先（个人覆盖共享、手写覆盖自动），
  同键覆盖时报告；local/ 缺文件自动从 templates/ 复制（绝不覆盖已有内容）。
* 黑名单（shared/blacklist.txt 客观 + local/blacklist.txt 个人，合并）：
  编译期对一切来源（自动 + 手写）过滤；可选第二列限定匹配方式
  （exact / sub / re），不写则全部禁用。想禁用某个自动键写黑名单，不要靠删行 ——
  auto 条目不落盘，每次编译都从数据源重新生成。
* 产物 compiled.tsv（gitignore）：四列 旧词/新词/mode/source，patch 的唯一输入；
  文件头记录 profile、生成时间与来源统计。

模板模式（--template，繁→繁民译流程）：
* 往 glossary/local/name.tsv 追加名段 / 全名连写 / 皮肤名恒等行（键=KivoWiki 繁体
  字段，右列待填）；往 glossary/local/text.tsv 追加皮肤括号恒等行（如 (單車)<TAB>(單車)，
  没有模板用户很难自己发现皮肤词条的带括号格式）。
* 已有内容逐行保留、只补新增键；shared/ 与 local/ 中同 mode 已存在的键不补
  （完整词条无需模板）；未填写的恒等行若已不在生成集合里则删除。
* 右列与左列相同的行 = 未填写，编译加载时自动跳过，不产生任何替换。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path

from ..config import (
    DEFAULT_GLOSSARY_PROFILE,
    GLOSSARY_COMPILED,
    GLOSSARY_LOCAL,
    GLOSSARY_PROFILES,
    GLOSSARY_SHARED,
    GLOSSARY_TEMPLATES,
)
from ..convert import Converter
from ..glossary import DEFAULT_MODE, MODES, iter_rows, load_entries
from .base import BaseTap

URL = "https://agent-0808.github.io/BA-characters-internal-id/data/students.json"
SKIN_MAP_URL = "https://agent-0808.github.io/BA-characters-internal-id/data/skin_map.json"
CACHE = "work/BACII_students.json"         # BACII（BA-characters-internal-id）students.json 缓存
CACHE_SKIN_MAP = "work/BACII_skin_map.json"  # BACII skin_map.json 缓存

# local/ 的三个文件缺哪个就从 templates/ 补哪个（已存在的不动，绝不覆盖用户内容）
LOCAL_FILES = ("name.tsv", "text.tsv", "blacklist.txt")


class GlossaryTap(BaseTap):
    """词表编译：数据源 + 手写词表 + 黑名单 -> glossary/compiled.tsv。"""

    profile: str = DEFAULT_GLOSSARY_PROFILE  # 词表流程：t2s 繁->简（编入 auto）/ t2t 繁->繁（只编手写）
    template: bool = False  # 模板模式：往 local/ 补恒等行模板（繁->繁民译用），不编译
    refresh: bool = False  # 强制重新下载 kivo 数据（students.json / skin_map.json）


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


def ensure_local_files() -> None:
    """local/ 缺文件时从 templates/ 复制（已存在的不动；删除后重跑即得新模板）。"""
    for name in LOCAL_FILES:
        dest = Path(GLOSSARY_LOCAL) / name
        if dest.exists():
            continue
        src = Path(GLOSSARY_TEMPLATES) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"已从模板生成: {dest}")


def load_blacklist() -> tuple[set[str], set[str], set[str]]:
    """合并 shared 与 local 的黑名单（不存在则跳过），返回 (exact 禁用键, sub 禁用键, re 禁用键)。

    格式：一行一个繁体键；可选第二列限定匹配方式（exact / sub / re），不写则全部禁用。
    例：`希望<TAB>sub` = 整字段匹配照常、但正文子串替换禁用（避免误伤普通词）；
    re 规则的键就是它的 pattern 字符串（须与词表里写的完全一致）。
    """
    buckets: dict[str, set[str]] = {"exact": set(), "sub": set(), "re": set()}
    for directory in (GLOSSARY_SHARED, GLOSSARY_LOCAL):
        path = Path(directory) / "blacklist.txt"
        if not path.exists():
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
                if scope in buckets:
                    buckets[scope].add(key)
                elif scope:
                    print(f"[blacklist] {path}:{ln} 未知范围 {scope!r}（应为 {' / '.join(buckets)}），按全部禁用处理")
                    for bucket in buckets.values():
                        bucket.add(key)
                else:
                    for bucket in buckets.values():
                        bucket.add(key)
    return buckets["exact"], buckets["sub"], buckets["re"]


def add_entry(
    target: dict[str, str],
    key: str,
    value: str,
    *,
    conv: Converter,
    stats: dict[str, int],
    dup: dict[str, str],
) -> None:
    """加入一条 auto 条目（exact 与 sub 两张表共用）：空键、恒等、OpenCC 兜底、键内重复时跳过。"""
    if not key or not value:
        stats["skip_empty"] += 1
    elif key == value:  # kivo 繁简同形的键（如 御稜名草）：无实际改动，不写入产物
        stats["skip_same"] += 1
    elif key in target:
        stats["conflict"] += 1
        dup[key] = value
    elif conv.convert(key) == value:
        stats["skip_opencc"] += 1
    else:
        target[key] = value


def report(label: str, stats: dict[str, int], dup: dict[str, str]) -> None:
    print(f"  {label}: {stats}")
    if dup:
        print(f"  另有 {len(dup)} 个键重复出现（保留先出现的值，示例前 5）:")
        for key, value in list(dup.items())[:5]:
            print(f"    {key} -> {value}")


def build_auto(
    students: list[dict],
    skin_map: dict[str, dict],
    black_exact: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """按规则生成 auto 条目（键 = kivo 繁中名，值 = kivo 简中民译）。

    黑名单在这里只做「名段被禁 -> 全名连带禁用」的派生门控（避免「黑名单 三森」
    仍替换 水羽三森）；逐键过滤统一在编译末尾对所有来源执行。
    """
    conv = Converter("t2s")  # 只转字形，用于判断「OpenCC 已处理、无需词条」
    auto_exact: dict[str, str] = {}
    auto_sub: dict[str, str] = {}
    s_exact = {"skip_empty": 0, "skip_same": 0, "skip_opencc": 0, "conflict": 0}
    s_sub = dict.fromkeys(s_exact, 0)
    dup_exact: dict[str, str] = {}
    dup_sub: dict[str, str] = {}

    def feed(key: str, value: str) -> None:
        add_entry(auto_exact, key, value, conv=conv, stats=s_exact, dup=dup_exact)
        add_entry(auto_sub, key, value, conv=conv, stats=s_sub, dup=dup_sub)

    for st in students:
        family_tw = (st.get("family_name_tw") or "").strip()
        given_tw = (st.get("given_name_tw") or "").strip()
        if not family_tw and not given_tw:
            continue
        # 名段：游戏文本只出现名（kivo 字段必定有值；无姓角色全名即名段）
        feed(given_tw, (st.get("given_name") or "").strip())
        # 全名连写（仅非拉丁姓名：游戏正文里姓与名连写）；
        # 名段被黑名单禁用时，由它派生的全名一并禁用
        joined_tw = family_tw + given_tw
        if family_tw and not joined_tw.isascii() and given_tw not in black_exact:
            feed(joined_tw, (st.get("family_name") or "").strip() + (st.get("given_name") or "").strip())

    # 皮肤词条：完全来自 kivo skin_map（键 = 简中基名，tw = 繁中基名）。
    # 正文 sub 用带括号的键（如 (單車) -> (骑行服)），只命中「角色名(皮肤)」复合串，
    # 不误伤正文里的裸词（如單車）。
    for base, loc in skin_map.items():
        skin_tw = (loc.get("tw") or "").strip()
        if not skin_tw:
            continue
        feed(skin_tw, base)  # exact：整字段兜底（少数界面单独显示皮肤名）；sub：裸词
        add_entry(auto_sub, f"({skin_tw})", f"({base})", conv=conv, stats=s_sub, dup=dup_sub)

    report("auto exact", s_exact, dup_exact)
    report("auto sub", s_sub, dup_sub)
    return auto_exact, auto_sub


def hand_files(directory: str) -> list[Path]:
    """目录下全部 .tsv（仅一层，文件名字母序；文件名不承载语义，mode 由文件头声明）。"""
    return sorted(Path(directory).glob("*.tsv"))


def valid_re(entries: dict[str, str], path: str) -> dict[str, str]:
    """编译期校验 re 块的 pattern；非法正则报错并剔除，不进产物。"""
    ok: dict[str, str] = {}
    for old, new in entries.items():
        try:
            re.compile(old)
        except re.error as e:
            print(f"[glossary] {path} 非法正则 {old!r}（{e}），跳过")
            continue
        ok[old] = new
    return ok


def compile_glossary(
    students: list[dict],
    skin_map: dict[str, dict],
    profile: str,
) -> int:
    """编译：auto（仅 t2s）+ shared/*.tsv + local/*.tsv，后者优先；黑名单过滤后写产物。"""
    black_exact, black_sub, black_re = load_blacklist()
    exact: dict[str, str] = {}
    sub: dict[str, str] = {}
    regex: dict[str, str] = {}  # pattern -> 替换串（dict 保持插入序，规则序即应用序）
    src: dict[str, str] = {}  # 旧词 -> 来源（用于 compiled.tsv 的 source 列）
    sources: list[str] = []

    if profile == "t2s":
        auto_exact, auto_sub = build_auto(students, skin_map, black_exact)
        exact.update(auto_exact)
        sub.update(auto_sub)
        src.update({k: "auto" for k in auto_exact})
        src.update({k: "auto" for k in auto_sub})
        sources.append(f"auto(exact {len(auto_exact)}条 / sub {len(auto_sub)}条)")

    for directory in (GLOSSARY_SHARED, GLOSSARY_LOCAL):  # 后加载者优先：local 覆盖 shared
        for path in hand_files(directory):
            groups = load_entries(str(path))
            if not groups:
                sources.append(f"{path}(0条)")
                continue
            for mode, entries in groups.items():  # 单文件可分块混用多种 mode，逐桶归位
                if mode == "re":
                    entries = valid_re(entries, str(path))  # 编译期校验 pattern，坏正则不进产物
                target = regex if mode == "re" else (exact if mode == "exact" else sub)
                overridden = [k for k in entries if k in target]
                target.update(entries)
                src.update({k: str(path) for k in entries})
                if overridden:
                    print(f"[glossary] {path} 覆盖了先加载的 {len(overridden)} 个 {mode} 键（后加载者优先），示例前 5:")
                    for key in overridden[:5]:
                        print(f"    {key} -> {entries[key]}")
            # 单 mode 与旧格式一致 `路径(exact, N条)`，多 mode 逐块展开
            desc = ", ".join(f"{m}, {len(entries)}条" for m, entries in groups.items())
            sources.append(f"{path}({desc})")

    # 黑名单过滤：对一切来源（自动 + 手写）生效
    removed_exact = sorted(set(exact) & black_exact)
    removed_sub = sorted(set(sub) & black_sub)
    removed_regex = sorted(set(regex) & black_re)
    exact = {k: v for k, v in exact.items() if k not in black_exact}
    sub = {k: v for k, v in sub.items() if k not in black_sub}
    regex = {k: v for k, v in regex.items() if k not in black_re}
    src = {k: s for k, s in src.items() if k in exact or k in sub or k in regex}  # 同键可部分保留
    removed = removed_exact + removed_sub + removed_regex
    if removed:
        print(f"黑名单过滤: exact 移除 {len(removed_exact)} 条，sub 移除 {len(removed_sub)} 条"
              + (f"，re 移除 {len(removed_regex)} 条" if removed_regex else ""))
        for key in removed[:5]:
            print(f"    {key}")

    # 写 compiled.tsv（四列：旧词/新词/mode/source，gitignore，patch 的唯一输入）
    out = Path(GLOSSARY_COMPILED)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# compiled.tsv — batr glossary 产物，勿手编（patch 的唯一输入）\n")
        f.write(f"# profile={profile}  generated={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# sources: {' '.join(sources)}\n")
        for old, new in exact.items():
            f.write(f"{old}\t{new}\texact\t{src[old]}\n")
        for old, new in sub.items():
            f.write(f"{old}\t{new}\tsub\t{src[old]}\n")
        for old, new in regex.items():
            f.write(f"{old}\t{new}\tre\t{src[old]}\n")
    stats = f"exact {len(exact)} 条 / sub {len(sub)} 条"
    if regex:
        stats += f" / re {len(regex)} 条"
    print(f"输出: {out} （{stats}）")
    return 0


def collect_name_keys(students: list[dict], skin_map: dict[str, dict], black_exact: set[str]) -> list[str]:
    """与 auto 相同的数据切分（名段 / 全名连写 / 皮肤名），按出现顺序去重（模板模式用）。"""
    keys: dict[str, None] = {}
    for st in students:
        family_tw = (st.get("family_name_tw") or "").strip()
        given_tw = (st.get("given_name_tw") or "").strip()
        if not family_tw and not given_tw:
            continue
        keys.setdefault(given_tw, None)
        # 名段被 exact 黑名单禁用时同时略过其全名（与 auto 的派生门控一致）
        joined_tw = family_tw + given_tw
        if family_tw and not joined_tw.isascii() and given_tw not in black_exact:
            keys.setdefault(joined_tw, None)
    for loc in skin_map.values():
        skin_tw = (loc.get("tw") or "").strip()
        if skin_tw:
            keys.setdefault(skin_tw, None)
    return [k for k in keys if k]


def handwritten_keys(mode: str) -> set[str]:
    """shared/ 与 local/ 中该 mode 块下已存在的键（含恒等行）：完整词条无需再补模板。"""
    keys: set[str] = set()
    for directory in (GLOSSARY_SHARED, GLOSSARY_LOCAL):
        for path in hand_files(directory):
            for cursor, _, line in iter_rows(str(path)):
                if cursor == mode and "\t" in line:
                    key = line.split("\t")[0].strip()
                    if key:
                        keys.add(key)
    return keys


def write_identity_rows(path: Path, mode: str, keys: list[str], existing: set[str]) -> None:
    """恒等行模板：已有内容逐行保留，只补新增键；本 mode 下未填写的（恒等）行
    若已不在生成集合里则删除。追加行前确保文件末尾处于本 mode（必要时补 `# mode:` 头）。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        lines = [ln.rstrip("\r\n") for ln in f]
    valid = set(keys)
    kept: list[str] = []
    present: set[str] = set()
    pruned = 0
    cursor = DEFAULT_MODE
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if stripped.startswith("# mode:"):
                declared = stripped.removeprefix("# mode:").strip().lower()
                if declared in MODES:
                    cursor = declared
            kept.append(line)
            continue
        if "\t" not in line:
            kept.append(line)
            continue
        key, value = line.split("\t")[:2]
        key = key.strip()
        if cursor == mode and key and key not in valid and key == value:
            pruned += 1  # 本 mode 未填写的恒等行 + 键已不在生成集合（黑名单等）-> 删除，避免模板里留陈旧条目
            continue
        if cursor == mode and key:
            present.add(key)
        kept.append(line)
    added = 0
    tail: list[str] = []
    new_keys = [k for k in keys if k not in present and k not in existing]
    if new_keys:
        if cursor != mode:  # 文件末尾停在别的 mode 块，补声明头防止追加行落错桶
            tail.append(f"# mode: {mode}")
        tail.extend(f"{key}\t{key}" for key in new_keys)
        added = len(new_keys)
        present.update(new_keys)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for line in kept + tail:
            f.write(f"{line}\n")
    print(f"输出: {path} （共 {len(present)} 条，新增 {added} 条，清理陈旧恒等行 {pruned} 条）")


def update_template(students: list[dict], skin_map: dict[str, dict]) -> None:
    """往 local/ 补恒等行模板：name.tsv 名段/全名/皮肤名 + text.tsv 皮肤括号行。"""
    black_exact, black_sub, _ = load_blacklist()
    name_keys = [k for k in collect_name_keys(students, skin_map, black_exact) if k not in black_exact]
    # text.tsv 只补皮肤括号恒等行：t2t 下 auto 不编入，皮肤 text 键没有模板用户很难自己发现格式
    text_keys = [
        f"({(loc.get('tw') or '').strip()})"
        for loc in skin_map.values()
        if (loc.get("tw") or "").strip()
    ]
    text_keys = [k for k in dict.fromkeys(text_keys) if k not in black_sub]
    write_identity_rows(Path(GLOSSARY_LOCAL) / "name.tsv", "exact", name_keys, handwritten_keys("exact"))
    write_identity_rows(Path(GLOSSARY_LOCAL) / "text.tsv", "sub", text_keys, handwritten_keys("sub"))


def handle_glossary(args: GlossaryTap) -> int:
    """处理 glossary 子命令（args 为合并了子命令属性的主 namespace）。"""
    if args.profile not in GLOSSARY_PROFILES:
        print(f"--profile 需为 {' / '.join(GLOSSARY_PROFILES)}")
        return 1
    ensure_local_files()
    if args.template:
        students, skin_map = download(args.refresh)
        update_template(students, skin_map)
        return 0
    students, skin_map = download(args.refresh)
    return compile_glossary(students, skin_map, args.profile)
