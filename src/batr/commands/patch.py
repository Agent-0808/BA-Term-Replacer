# commands/patch.py
"""patch 子命令：字段级文本补丁 + CRC 修正，可选覆盖安装到游戏目录。"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from .. import patch as patch_mod
from ..config import (
    DEFAULT_CONVERT,
    DEFAULT_KEY,
    DEFAULT_NAMES_GLOSSARY,
    DEFAULT_NAMES_LOCAL,
    DEFAULT_OUT_DIR,
    DEFAULT_TABLE_PATTERN,
    DEFAULT_TERMS_GLOSSARY,
    DEFAULT_TEXT_GLOSSARY,
    DEFAULT_TEXT_LOCAL,
)
from ..glossary import Glossary
from ..utils.paths import BARegion, get_excel_db_path, resolve_excel_db
from .base import BaseTap


class PatchTap(BaseTap):
    """字段级文本补丁（支持变长替换）+ CRC 追加修正（产出可直接使用的库）。"""

    db: Path | None = None  # 输入 ExcelDB.db（不会被修改；省略时自动定位游戏安装路径，同 scan/export）
    out: Path | None = None  # 输出库（另存，CRC32 与输入一致；默认 output/<输入文件名>，--dry-run 时可省略）
    key: str = DEFAULT_KEY  # 32 字节 SQLCipher 密钥（hex）
    convert: Literal["tw2sp", "t2s", "none"] = DEFAULT_CONVERT  # tw2sp 含台湾用词转换，t2s 只转字形，none 只做替换表
    convert_kana: bool = False  # 不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）
    no_ascii_exact: bool = False  # 不替换纯 ASCII 字段（如角色名 "Kei"）
    tables: str = DEFAULT_TABLE_PATTERN  # 限定要处理的表名正则
    extra_bytes: str = "08080808"  # CRC 修正前附加到输出末尾的自定义字节（hex）
    names: list[Path] = []  # 角色名表（exact 整字段匹配），默认 glossary/names.tsv
    text: list[Path] = []  # 正文替换表（sub 子串匹配），默认 glossary/text.tsv
    dry_run: bool = False  # 只统计会改什么，不写任何文件
    verify: bool = False  # 完成后对输出库跑 PRAGMA integrity_check
    region: BARegion = "auto"  # 自动定位游戏路径用的区服（auto = global 优先，japan 兜底）
    install: bool = False  # 补丁成功后覆盖安装到游戏目录（覆盖前备份 .bak，默认交互确认）
    yes: bool = False  # 覆盖安装跳过交互确认（非交互环境必须显式给出）


def _mtime(st: os.stat_result) -> str:
    """文件修改时间的可读格式。"""
    return datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _install(src: Path, dest: Path, *, yes: bool) -> int:
    """把补丁输出库覆盖到游戏目录，覆盖前先备份原库为 .bak。"""
    if not dest.exists():
        print(f"游戏库不存在: {dest}")
        return 1
    print(f"源文件: {src}（{src.stat().st_size} 字节, {_mtime(src.stat())}）")
    print(f"目标:   {dest}（{dest.stat().st_size} 字节, {_mtime(dest.stat())}）")
    if not yes:
        if not sys.stdin.isatty():
            print("非交互环境拒绝覆盖安装；如确认请加 --yes")
            return 1
        if input("确认覆盖游戏库? [y/N] ").strip().lower() != "y":
            print("已取消")
            return 0
    bak = dest.with_name(dest.name + ".bak")
    shutil.copy2(dest, bak)
    print(f"已备份: {bak}")
    try:
        shutil.copy2(src, dest)
    except PermissionError:
        print("覆盖失败：目标文件被占用，请先关闭游戏后重试")
        return 1
    print("已安装到游戏目录")
    return 0


def handle_patch(args: PatchTap) -> int:
    """处理 patch 子命令（args 为合并了子命令属性的主 namespace）。"""
    db = resolve_excel_db(args.db, args.region)
    if db is None:
        print("未指定 db 且未能从注册表定位游戏安装路径；请显式给出 db 路径，或用 --region 指定区服")
        return 1
    if args.install and args.dry_run:
        print("--install 不能与 --dry-run 同用（预演不产出文件）")
        return 1
    # 省略 --out 时默认写到 output/<输入文件名>（--dry-run 无输出，可省略）
    out = args.out or Path(DEFAULT_OUT_DIR) / db.name
    try:
        extra: bytes | None = bytes.fromhex(args.extra_bytes.removeprefix("0x"))
    except ValueError:
        print("--extra-bytes 需要偶数长度的 hex 字符串，如 DEADBEEF")
        return 1
    # 手工表排在最前（重复键先出现者优先），自动生成的表其次，通用专名表最后（个人优先于共享）。
    names_paths = args.names or [DEFAULT_NAMES_LOCAL, DEFAULT_NAMES_GLOSSARY]
    text_paths = args.text or [DEFAULT_TEXT_LOCAL, DEFAULT_TEXT_GLOSSARY]
    if os.path.exists(DEFAULT_TERMS_GLOSSARY):
        text_paths = [*text_paths, DEFAULT_TERMS_GLOSSARY]
    glossary: Glossary | None = None
    if any(os.path.exists(p) for p in names_paths + text_paths):
        try:
            glossary = Glossary.load(
                [p for p in names_paths if os.path.exists(p)],
                [p for p in text_paths if os.path.exists(p)],
            )
        except OSError as exc:
            print(f"无法读取词表: {exc}")
            return 1
    patch_mod.patch_database(
        db,
        out,
        key=args.key,
        convert=args.convert,
        skip_kana=not args.convert_kana,
        tables=args.tables,
        extra_bytes=extra,
        glossary=glossary,
        ascii_exact=not args.no_ascii_exact,
        dry_run=args.dry_run,
        verify=args.verify,
    )
    if args.install:
        dest = get_excel_db_path(args.region)
        if dest is None:
            print("未能从注册表定位游戏安装路径，无法安装；请检查游戏是否已安装或用 --region 指定区服")
            return 1
        return _install(out, Path(dest), yes=args.yes)
    return 0
