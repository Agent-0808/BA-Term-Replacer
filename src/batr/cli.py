"""batr 命令行入口"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from tap import Tap, Positional

from . import __version__, patch as patch_mod
from .config import DEFAULT_CONVERT, DEFAULT_KEY, DEFAULT_NAMES_GLOSSARY, DEFAULT_OUT_DIR, DEFAULT_TABLE_PATTERN, DEFAULT_TEXT_GLOSSARY
from .glossary import Glossary


def _setup_stdout() -> None:
    """避免在非 UTF-8 控制台打印中文时报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class BaseTap(Tap):
    """基础 Tap 类，提供共享配置。"""

    def configure(self) -> None:
        self._underscores_to_dashes = True


class PatchArgs(BaseTap):
    """字段级文本补丁（支持变长替换）+ CRC 追加修正（产出可直接使用的库）。"""

    db: Positional[Path]  # 输入 ExcelDB.db（不会被修改）
    out: Path | None = None  # 输出库（另存，CRC32 与输入一致；默认 output/<输入文件名>，--dry-run 时可省略）
    key: str = DEFAULT_KEY  # 32 字节 SQLCipher 密钥（hex）
    convert: Literal["tw2sp", "t2s", "none"] = DEFAULT_CONVERT  # tw2sp 含台湾用词转换，t2s 只转字形，none 只做替换表
    convert_kana: bool = False  # 不跳过含假名的字段（默认跳过：日文列在 GL 是死数据）
    tables: str = DEFAULT_TABLE_PATTERN  # 限定要处理的表名正则
    extra_bytes: str = "08080808"  # CRC 修正前附加到输出末尾的自定义字节（hex）
    names: list[Path] = []  # 角色名表（exact 整字段匹配），默认 glossary/names.tsv
    text: list[Path] = []  # 正文替换表（sub 子串匹配），默认 glossary/text.tsv
    dry_run: bool = False  # 只统计会改什么，不写任何文件
    verify: bool = False  # 完成后对输出库跑 PRAGMA integrity_check


def _cmd_patch(args: PatchArgs) -> int:
    # 省略 --out 时默认写到 output/<输入文件名>（--dry-run 无输出，可省略）
    out = args.out or Path(DEFAULT_OUT_DIR) / args.db.name
    try:
        extra: bytes | None = bytes.fromhex(args.extra_bytes.removeprefix("0x"))
    except ValueError:
        print("--extra-bytes 需要偶数长度的 hex 字符串，如 DEADBEEF")
        return 1
    names_paths = args.names or [DEFAULT_NAMES_GLOSSARY]
    text_paths = args.text or [DEFAULT_TEXT_GLOSSARY]
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
        args.db,
        out,
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


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    if argv is None:
        argv = sys.argv[1:]
    if "--version" in argv:
        print(f"batr {__version__}")
        return 0
    args = PatchArgs().parse_args(argv)
    try:
        return _cmd_patch(args)
    except KeyboardInterrupt:
        print("\n已中止（不会留下半成品）")
        return 130
    except Exception as exc:
        print(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
