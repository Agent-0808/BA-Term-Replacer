# commands/scan.py
"""scan 子命令：字段级扫描（调试工具），关键词在哪些表、哪些字段、以什么形态出现。

用法（db 省略时自动定位游戏客户端内的库）：
    uv run batr scan <关键词...> [--db <db>] [--tables 正则] [--ascii] [--limit N]
    uv run batr scan <关键词...> --diff <另一个db>   # 两库命中数对比（验证替换效果）
    uv run batr scan --uncovered                    # 未匹配默认表正则但含中文字段的表

字段按三类统计：kana（含假名，日文死数据，只计数不出样本）/ cjk（中文字段）/ ascii（纯拉丁，
默认不扫，--ascii 开启后经 exact 整字段匹配可命中的那类，如角色名的拉丁写法 "Kei"）。
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

from tap import Positional

from .. import db as batr_db
from ..config import DEFAULT_KEY, DEFAULT_TABLE_PATTERN
from ..flatbuf import has_cjk, has_kana, iter_string_fields
from ..utils.paths import BARegion, resolve_excel_db
from .base import BaseTap

CLASSES = ("kana", "cjk", "ascii")
Counter = dict[str, int]  # 类 -> 计数


class ScanTap(BaseTap):
    """字段级扫描：关键词定位 / 两库对比 / 未覆盖表清单。"""

    keywords: Positional[list[str]] = []  # 要查找的关键词（--uncovered 时可省略）
    db: Path | None = None  # ExcelDB.db 路径（省略时自动定位游戏安装路径）
    region: BARegion = "auto"  # 自动定位游戏路径用的区服（auto = global 优先，japan 兜底）
    tables: str = ""  # 表名正则过滤（默认全部表）
    ascii: bool = False  # 连纯拉丁字段一起扫描（allow_ascii）
    limit: int = 30 # 每表每关键词的样本条数
    diff: Path | None = None  # 再扫另一个库，输出两库命中数对比（验证替换效果）
    uncovered: bool = False  # 列出未匹配默认表正则但含中文字段的表


def scan_db(
    path: str, keywords: list[str], *, tables_re: re.Pattern | None, ascii_on: bool, limit: int
) -> tuple[dict[str, dict[str, Counter]], dict[str, dict[str, list[str]]]]:
    """扫一个库：返回（表 -> 关键词 -> 各类计数, 表 -> 关键词 -> 样本文本）。"""
    counts: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(dict))
    samples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    con = batr_db.connect(path, DEFAULT_KEY)
    try:
        for table in batr_db.list_tables(con):
            if tables_re is not None and not tables_re.search(table):
                continue
            try:
                rows = con.execute(f"SELECT Bytes FROM [{table}]").fetchall()
            except Exception:
                continue
            for (blob,) in rows:
                if not isinstance(blob, (bytes, bytearray)) or len(blob) < 16:
                    continue
                try:
                    fields = iter_string_fields(bytes(blob), allow_ascii=ascii_on)
                except ValueError:
                    continue
                for _slot, _fp, _sp, text in fields:
                    if has_kana(text):
                        cls = "kana"
                    elif has_cjk(text):
                        cls = "cjk"
                    elif ascii_on:
                        cls = "ascii"
                    else:
                        continue
                    for kw in keywords:
                        if kw not in text:
                            continue
                        c = counts[table][kw]
                        c[cls] = c.get(cls, 0) + 1
                        # 假名字段只计数；样本去重，截到 limit 条
                        if cls != "kana" and len(samples[table][kw]) < limit \
                                and text not in samples[table][kw]:
                            samples[table][kw].append(text)
    finally:
        con.close()
    return counts, samples


def total(c: Counter) -> int:
    return sum(c.values())


def print_scan(path: str, keywords: list[str], counts: dict, samples: dict) -> None:
    print(f"=== {path} ===")
    for table in sorted(counts):
        for kw in keywords:
            if kw not in counts[table]:
                continue
            c = counts[table][kw]
            print(f"[{table}] {kw}: " + " ".join(f"{k}={c[k]}" for k in CLASSES if c.get(k)))
            for s in samples[table][kw]:
                print(f"  {s[:100]!r}")


def print_diff(db_a: str, db_b: str, keywords: list[str], counts_a: dict, counts_b: dict) -> None:
    # 相对路径显示，避免两库同名（output/ExcelDB.db vs work/db/ExcelDB.db）分不清
    name_a, name_b = os.path.relpath(db_a), os.path.relpath(db_b)
    for kw in keywords:
        tables = sorted({t for t, kws in counts_a.items() if kw in kws}
                        | {t for t, kws in counts_b.items() if kw in kws})
        if not tables:
            print(f"--- {kw}: 两库均无命中 ---")
            continue
        print(f"--- {kw} ---")
        for table in tables:
            ta = total(counts_a.get(table, {}).get(kw, {}))
            tb = total(counts_b.get(table, {}).get(kw, {}))
            if ta != tb:
                print(f"  [{table}] {name_a}={ta}  {name_b}={tb}")
        print(f"  合计: {name_a}={sum(total(counts_a.get(t, {}).get(kw, {})) for t in tables)}"
              f"  {name_b}={sum(total(counts_b.get(t, {}).get(kw, {})) for t in tables)}")


def print_uncovered(path: str) -> None:
    """列出含中文字段（不含假名）却不在 DEFAULT_TABLE_PATTERN 内的表 —— 「还有哪些表该进列表」。"""
    pattern = re.compile(DEFAULT_TABLE_PATTERN, re.IGNORECASE)
    per_table: dict[str, int] = defaultdict(int)
    con = batr_db.connect(path, DEFAULT_KEY)
    try:
        for table in batr_db.list_tables(con):
            if pattern.search(table):
                continue
            try:
                rows = con.execute(f"SELECT Bytes FROM [{table}]").fetchall()
            except Exception:
                continue
            for (blob,) in rows:
                if not isinstance(blob, (bytes, bytearray)) or len(blob) < 16:
                    continue
                try:
                    fields = iter_string_fields(bytes(blob))
                except ValueError:
                    continue
                per_table[table] += sum(1 for *_x, t in fields if not has_kana(t) and has_cjk(t))
    finally:
        con.close()
    print(f"=== {path} 未匹配默认表正则且含中文字段的表 ===")
    for table, n in sorted(per_table.items(), key=lambda x: -x[1]):
        if n:
            print(f"  {table}: {n}")


def handle_scan(args: ScanTap) -> int:
    """处理 scan 子命令（args 为合并了子命令属性的主 namespace）。"""
    db = resolve_excel_db(args.db, args.region)
    if db is None:
        print("未指定 --db 且未能从注册表定位游戏安装路径；请显式给出 --db，或用 --region 指定区服")
        return 1
    keywords: list[str] = args.keywords
    if args.uncovered and not keywords:
        print_uncovered(str(db))
        return 0
    if not keywords:
        print("至少给一个关键词（或使用 --uncovered）")
        return 2
    tables_re = re.compile(args.tables, re.IGNORECASE) if args.tables else None
    if args.diff:
        counts_a, _ = scan_db(str(db), keywords, tables_re=tables_re,
                              ascii_on=args.ascii, limit=0)
        counts_b, _ = scan_db(str(args.diff), keywords, tables_re=tables_re,
                              ascii_on=args.ascii, limit=0)
        print_diff(str(db), str(args.diff), keywords, counts_a, counts_b)
        return 0
    counts, samples = scan_db(str(db), keywords, tables_re=tables_re,
                              ascii_on=args.ascii, limit=args.limit)
    print_scan(str(db), keywords, counts, samples)
    return 0
