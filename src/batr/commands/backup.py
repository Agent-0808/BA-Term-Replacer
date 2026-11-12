# commands/backup.py
"""backup 子命令：把未改动的 ExcelDB.db 复制为本地干净副本（默认 work/db/ExcelDB.db）。

    uv run batr backup [--db <db>] [--to 路径] [--region ...] [--force]

游戏目录里的库可能已被 --install 改动过：拿它当输入等于二次补丁（词表键是繁体，
简体文本上大面积零命中），scan --diff 也失去原始库基准。因此推荐工作流先 backup
一次，之后 patch / scan / export 都显式 --db 指向这份干净副本。
目标已存在时默认拒绝覆盖（防误覆盖干净副本），--force 才重写。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from ..config import DEFAULT_BACKUP
from ..utils import crc
from ..utils.paths import BARegion, resolve_excel_db
from .base import BaseTap


def _describe(path: Path) -> str:
    """文件的大小与时间信息（不含路径）：大小 + 修改时间 + 创建时间（Windows 上 st_ctime 即创建时间）。"""
    st = path.stat()
    fmt = "%Y-%m-%d %H:%M:%S"
    mtime = datetime.fromtimestamp(st.st_mtime).strftime(fmt)
    ctime = datetime.fromtimestamp(st.st_ctime).strftime(fmt)
    return f"{st.st_size / 1048576:.1f} MB, 修改于 {mtime}, 创建于 {ctime}, CRC = {crc.compute_crc32(path)}"


def _print_pair(src: Path, dst: Path) -> None:
    """依次打印两个文件：各自路径一行、描述一行，文件之间空一行。"""
    for i, (label, path) in enumerate((("源", src), ("副本", dst))):
        if i:
            print()
        print(f"{label}: {path}")
        print(f"  {_describe(path)}")


class BackupTap(BaseTap):
    """把未改动的 ExcelDB.db 复制为本地干净副本。"""

    db: Path | None = None  # 源 ExcelDB.db（省略时自动定位游戏客户端内的库）
    to: Path = Path(DEFAULT_BACKUP)  # 干净副本目标路径
    region: BARegion = "auto"  # 自动定位游戏路径用的区服（auto = global 优先，japan 兜底）
    force: bool = False  # 目标已存在时覆盖（默认拒绝，防误覆盖干净副本）


def handle_backup(args: BackupTap) -> int:
    """处理 backup 子命令（args 为合并了子命令属性的主 namespace）。"""
    src = resolve_excel_db(args.db, args.region)
    if src is None:
        print("未指定 --db 且未能从注册表定位游戏安装路径；请显式给出 --db，或用 --region 指定区服")
        return 1
    if not src.exists():
        print(f"输入不存在: {src}")
        return 1
    dst = args.to
    if src.resolve() == dst.resolve():
        print("源与目标是同一个文件，无需复制")
        return 1
    if dst.exists() and not args.force:
        print(f"目标已存在: {dst}（防误覆盖干净副本；确认要覆盖请加 --force）")
        print()
        _print_pair(src, dst)
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    src_crc, dst_crc = crc.compute_crc32(src), crc.compute_crc32(dst)
    print(f"源:   {src} ({src.stat().st_size / 1048576:.1f} MB, CRC32 {src_crc:08X})")
    print(f"副本: {dst} ({dst.stat().st_size / 1048576:.1f} MB, CRC32 {dst_crc:08X})")
    if src_crc != dst_crc:
        print("错误: 副本 CRC32 与源不一致（复制损坏），请删除后重试")
        return 1
    print("CRC32 校验一致 ✅ 之后 patch / scan / export 用 --db 指向这份副本")
    return 0
