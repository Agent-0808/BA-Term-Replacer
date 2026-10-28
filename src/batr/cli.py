"""batr 命令行入口：patch / crc-fix 子命令。"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import __version__, patch as patch_mod
from .config import DEFAULT_CONVERT, DEFAULT_KEY, DEFAULT_TABLE_PATTERN, CONVERT_MODES
from .glossary import Glossary
from .utils import crc


def _setup_stdout() -> None:
    """避免在非 UTF-8 控制台打印中文时报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _cmd_patch(args: argparse.Namespace) -> int:
    if not args.out and not args.dry_run:
        print("需要 --out <输出文件>（--dry-run 时可省略）")
        return 1
    extra: bytes | None = None
    if args.extra_bytes is not None:
        if isinstance(args.extra_bytes, int):  # 代码内默认值直接写 int（如 0x08080808）
            extra = args.extra_bytes.to_bytes(4, "big")
        else:
            try:
                extra = bytes.fromhex(args.extra_bytes.removeprefix("0x"))
            except ValueError:
                print("--extra-bytes 需要偶数长度的 hex 字符串，如 DEADBEEF")
                return 1
    glossary: Glossary | None = None
    if args.glossary:
        try:
            glossary = Glossary.load(args.glossary)
        except OSError as exc:
            print(f"无法读取词表: {exc}")
            return 1
    patch_mod.patch_database(
        args.db,
        args.out or "",
        key=args.key,
        convert=args.convert,
        skip_kana=not args.convert_kana,
        tables=args.tables,
        extra_bytes=extra,
        glossary=glossary,
        dry_run=args.dry_run,
        verify=args.verify,
    )
    return 0


def _cmd_crc_fix(args: argparse.Namespace) -> int:
    if not os.path.exists(args.src):
        print(f"输入不存在: {args.src}")
        return 1
    if args.target_from:
        target = crc.compute_crc32(args.target_from)
    elif args.target_crc:
        target = int(args.target_crc, 16)
    else:
        print("需要 --target-from <基准文件> 或 --target-crc <8位hex> 之一")
        return 1

    src_crc = crc.compute_crc32(args.src)
    print(f"输入   CRC32 = {src_crc:08X}")
    print(f"目标   CRC32 = {target:08X}")

    shutil.copyfile(args.src, args.out)
    if not crc.manipulate_file_crc(args.out, target):
        print("CRC 修正失败")
        return 1
    final = crc.compute_crc32(args.out)
    ok = final == target
    print(f"输出   CRC32 = {final:08X} {'✅' if ok else '❌ 不一致'}")
    print(f"大小变化: {os.path.getsize(args.src)} -> {os.path.getsize(args.out)}（+4 字节）")
    if args.verify:
        result = crc.compute_crc32(args.out)
        print(f"verify: crc32 = {result:08X} {'OK' if result == target else 'MISMATCH'}")
        return 0 if result == target else 1
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="batr",
        description="BA-Term-Replacer：蔚蓝档案国际服 译名替换 / 繁简转换工具",
    )
    parser.add_argument("--version", action="version", version=f"batr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_patch = sub.add_parser(
        "patch", help="字段级文本补丁（支持变长替换）+ CRC 追加修正（产出可直接使用的库）")
    p_patch.add_argument("--db", required=True, help="输入 ExcelDB.db（不会被修改）")
    p_patch.add_argument("--out", default=None, help="输出库（另存，CRC32 与输入一致；--dry-run 时可省略）")
    p_patch.add_argument("--key", default=DEFAULT_KEY, help="32 字节 SQLCipher 密钥（hex）")
    p_patch.add_argument("--convert", default=DEFAULT_CONVERT, choices=CONVERT_MODES,
                         help="tw2sp 含台湾用词转换，t2s 只转字形，none 只做替换表")
    p_patch.add_argument("--convert-kana", action="store_true",
                         help="不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）")
    p_patch.add_argument("--tables", default=DEFAULT_TABLE_PATTERN,
                         help="限定要处理的表名正则")
    p_patch.add_argument("--extra-bytes", default=0x08080808, metavar="HEX",
                         help="CRC 修正前附加到输出末尾的自定义字节（hex，如 DEADBEEF；默认 08080808）")
    p_patch.add_argument("--glossary", action="append", metavar="TSV",
                         help="译名对照表（TSV：繁体旧词<TAB>新词），可重复传入")
    p_patch.add_argument("--dry-run", action="store_true",
                         help="只统计会改什么，不写任何文件")
    p_patch.add_argument("--verify", action="store_true",
                         help="完成后对输出库跑 PRAGMA integrity_check")
    p_patch.set_defaults(func=_cmd_patch)

    p_crc = sub.add_parser(
        "crc-fix", help="给任意文件追加 4 字节修正，使其 CRC32 等于目标值")
    p_crc.add_argument("--in", dest="src", required=True, help="输入文件（不会被修改）")
    p_crc.add_argument("--out", required=True, help="输出文件（输入内容 + 4 字节修正）")
    p_crc.add_argument("--target-from", help="从这个文件读取目标 CRC32")
    p_crc.add_argument("--target-crc", help="显式指定 8 位 hex 目标 CRC32")
    p_crc.add_argument("--verify", action="store_true", help="完成后重算输出 CRC 复核")
    p_crc.set_defaults(func=_cmd_crc_fix)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中止（不会留下半成品）")
        return 130
    except Exception as exc:
        print(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
