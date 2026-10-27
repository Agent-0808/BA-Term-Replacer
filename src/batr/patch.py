"""一站式入口：遍历库 -> 等长转换 -> 写输出 -> CRC 追加修正 -> 自校验。

原理：游戏把表数据存在 SQLCipher 加密的 `ExcelDB.db` 里，每行 `(Key, Bytes BLOB)`，
`Bytes` 是 FlatBuffer。繁->简几乎都是 3 字节 UTF-8 汉字互换，做**等长字节替换**时
所有偏移字段保持有效，结构零风险；长度会变的映射逐字替换，仍要求等长，否则放弃。

转换完成后给输出文件追加 4 字节，使其 CRC32 与输入一致（见 `crc.py`），
客户端的 catalog 校验自然通过 —— **不再需要改 `TableCatalog.bytes`**。

Provenance / credits
--------------------
* SQLCipher 接口参数（页 4096、KDF 256000、HMAC-SHA512、保留 80 字节）经社区工具链
  （BlueArchive-Tools, AGPL-3.0）确认 —— 仅作参考，**未使用其代码**。
* 默认密钥为社区公开流传值，作为可覆盖默认提供。
* 繁简映射来自 OpenCC 词典（Apache-2.0，见 `data/`）；本文件的 blob 遍历逻辑为原创。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass, field

from . import db
from .config import DEFAULT_CONVERT_MODE, DEFAULT_KEY, DEFAULT_TABLE_PATTERN
from .convert import Converter
from .utils import crc


def is_cjk3(b: bytes | bytearray, i: int, n: int) -> bool:
    """True if a 3-byte UTF-8 CJK ideograph starts at i (U+4E00..U+9FFF range)."""
    return (i + 2 < n and 0xE4 <= b[i] <= 0xE9
            and (b[i + 1] & 0xC0) == 0x80 and (b[i + 2] & 0xC0) == 0x80)


def convert_blob(blob: bytes, conv: Converter) -> tuple[bytes | None, int]:
    """Return (new_blob_or_None, number_of_changed_characters)."""
    b = bytearray(blob)
    n = len(b)
    changed = 0
    i = 0
    while i < n:
        if not is_cjk3(b, i, n):
            i += 1
            continue

        # collect a maximal run of 3-byte CJK characters
        j = i
        run = bytearray()
        while is_cjk3(b, j, n):
            run += b[j:j + 3]
            j += 3

        try:
            text = run.decode("utf-8")
        except UnicodeDecodeError:
            i = j
            continue

        new_bytes = conv.convert(text).encode("utf-8")
        if len(new_bytes) == len(run):
            if new_bytes != bytes(run):
                b[i:j] = new_bytes
                changed += sum(1 for a, c in zip(text, new_bytes.decode("utf-8")) if a != c)
        else:
            # Fall back to per-character substitution (still length preserving).
            pos = i
            for ch in text:
                old = ch.encode("utf-8")
                new = conv.convert(ch).encode("utf-8")
                if len(new) == len(old) and new != old:
                    b[pos:pos + len(old)] = new
                    changed += 1
                pos += len(old)
        i = j

    return (bytes(b) if changed else None), changed


@dataclass
class PatchStats:
    """一次补丁运行的统计。"""
    target_crc: int = 0
    final_crc: int | None = None
    rows_seen: int = 0
    rows_changed: int = 0
    chars_changed: int = 0
    tables: list[str] = field(default_factory=list)


def patch_database(
    src: str,
    dst: str,
    *,
    key: str = DEFAULT_KEY,
    mode: str = DEFAULT_CONVERT_MODE,
    tables: str = DEFAULT_TABLE_PATTERN,
    dry_run: bool = False,
    verify: bool = False,
    log=print,
) -> PatchStats:
    """把 src 库的繁中文本转成简体，写入 dst（CRC32 与 src 一致）。

    dry_run 时直接只读打开 src 统计，不写任何文件。
    """
    if not os.path.exists(src):
        raise FileNotFoundError(f"输入不存在: {src}")
    if not dry_run and os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("--db 与 --out 不能是同一个文件（输入永远不被修改）")

    conv = Converter(mode)
    log(f"mode={mode}  phrases={len(conv.phrases)}  chars={len(conv.chars)}")

    stats = PatchStats(target_crc=crc.compute_crc32(src))
    log(f"输入 CRC32 = {stats.target_crc:08X}（输出将与之对齐）")

    work = dst + ".tmp" if not dry_run else src
    if not dry_run:
        shutil.copy2(src, work)

    try:
        con = db.connect(work, key)
        try:
            todo = db.select_tables(con, tables)
            all_tables = db.list_tables(con)
            log(f"tables={len(all_tables)}  text tables matched={len(todo)}")
            stats.tables = todo

            for table in todo:
                try:
                    rows = con.execute(f"SELECT rowid, Bytes FROM [{table}]").fetchall()
                except sqlite3.Error as exc:
                    log(f"  [{table}] skipped: {exc}")
                    continue

                updates: list[tuple[bytes, int]] = []
                t_chars = 0
                for rid, blob in rows:
                    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 16:
                        continue
                    new_blob, nchars = convert_blob(bytes(blob), conv)
                    if new_blob is not None:
                        updates.append((new_blob, rid))
                        stats.rows_changed += 1
                        t_chars += nchars
                if updates and not dry_run:
                    con.executemany(f"UPDATE [{table}] SET Bytes=? WHERE rowid=?", updates)
                    con.commit()
                if updates:
                    log(f"  [{table}] rows={len(rows)} changed={len(updates)} chars={t_chars}")
                stats.rows_seen += len(rows)
                stats.chars_changed += t_chars
        finally:
            con.close()

        if dry_run:
            log(f"[dry-run] rows scanned={stats.rows_seen} rows changed={stats.rows_changed} "
                f"chars={stats.chars_changed}（未写任何文件）")
            return stats

        # CRC 追加修正：让输出与输入的 CRC32 一致，替代旧的 catalog 改写。
        if not crc.manipulate_file_crc(work, stats.target_crc):
            raise RuntimeError("CRC 修正失败")
        os.replace(work, dst)
        stats.final_crc = crc.compute_crc32(dst)
        if stats.final_crc != stats.target_crc:
            raise RuntimeError(f"CRC 自校验失败: {stats.final_crc:08X} != {stats.target_crc:08X}")
        log(f"输出 CRC32 = {stats.final_crc:08X} ✅ 与输入一致")

        if verify:
            con = db.connect(dst, key)
            try:
                result = con.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                con.close()
            if result != "ok":
                raise RuntimeError(f"integrity_check: {result}")
            log("integrity_check = ok")

        log(f"rows scanned={stats.rows_seen} rows changed={stats.rows_changed} chars={stats.chars_changed}")
        log(f"output: {dst} ({os.path.getsize(dst) / 1048576:.1f} MB)")
        return stats
    except BaseException:
        # 绝不留下半成品：删除临时文件与未完成的输出。
        if os.path.exists(work) and os.path.abspath(work) != os.path.abspath(src):
            os.remove(work)
        if not dry_run and stats.final_crc is None and os.path.exists(dst):
            os.remove(dst)
        raise
