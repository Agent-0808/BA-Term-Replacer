# commands/patch.py
"""patch 子命令：字段级文本补丁 + CRC 修正，可选覆盖安装到游戏目录。"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .. import patch as patch_mod
from ..config import (
    CONVERT_MODES,
    DEFAULT_CONVERT,
    DEFAULT_KEY,
    DEFAULT_OUT_DIR,
    DEFAULT_TABLE_PATTERN,
    GLOSSARY_COMPILED,
    GLOSSARY_PROFILES,
)
from ..glossary import Glossary
from ..utils.paths import BARegion, get_excel_db_path, resolve_excel_db
from .base import BaseTap


class PatchTap(BaseTap):
    """字段级文本补丁（支持变长替换）+ CRC 追加修正（产出可直接使用的库）。"""

    db: Path | None = None  # 输入 ExcelDB.db（不会被修改；省略时自动定位游戏安装路径，同 scan/export）
    out: Path | None = None  # 输出库（另存，CRC32 与输入一致；默认 output/<输入文件名>，--dry-run 时可省略）
    key: str = DEFAULT_KEY  # 32 字节 SQLCipher 密钥（hex）
    profile: str = "t2s"  # 词表流程：t2s 繁->简（默认）/ t2t 繁->繁（自动绑定 convert=none）
    convert: str | None = None  # OpenCC 模式，缺省 tw2sp（t2t profile 下缺省 none）；显式给出则覆盖 profile 缺省
    convert_kana: bool = False  # 不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）
    no_ascii_exact: bool = False  # 不替换纯 ASCII 字段（如角色名 "Kei"）
    tables: str = DEFAULT_TABLE_PATTERN  # 限定要处理的表名正则
    extra_bytes: str = "08080808"  # CRC 修正前附加到输出末尾的自定义字节（hex）
    glossary: Path = Path(GLOSSARY_COMPILED)  # 编译词表产物（batr glossary 生成），替换在 OpenCC 之前
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
    # convert 缺省按 profile 绑定：t2t 繁->繁自动用 none（不再要用户记参数），显式给出则覆盖
    if args.profile not in GLOSSARY_PROFILES:
        print(f"--profile 需为 {' / '.join(GLOSSARY_PROFILES)}")
        return 1
    convert = args.convert or ("none" if args.profile == "t2t" else DEFAULT_CONVERT)
    if convert not in CONVERT_MODES:
        print(f"--convert 需为 {' / '.join(CONVERT_MODES)}")
        return 1
    # 省略 --out 时默认写到 output/<输入文件名>（--dry-run 无输出，可省略）
    out = args.out or Path(DEFAULT_OUT_DIR) / db.name
    try:
        extra: bytes | None = bytes.fromhex(args.extra_bytes.removeprefix("0x"))
    except ValueError:
        print("--extra-bytes 需要偶数长度的 hex 字符串，如 DEADBEEF")
        return 1
    # 词表只读编译产物（合并顺序、黑名单过滤已在编译期完成，patch 端零合并逻辑）
    glossary: Glossary | None = None
    if Path(args.glossary).exists():
        glossary = Glossary.from_compiled(str(args.glossary))
    else:
        print(f"词表产物不存在: {args.glossary}（先运行 batr glossary 生成；本次仅做 OpenCC 转换）")
    patch_mod.patch_database(
        db,
        out,
        key=args.key,
        convert=convert,
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
