"""一站式入口：遍历库 -> 字段级补丁 -> 写输出 -> CRC 追加修正 -> 自校验。

原理：游戏把表数据存在 SQLCipher 加密的 `ExcelDB.db` 里，每行 `(Key, Bytes BLOB)`，
`Bytes` 是 FlatBuffer。文本改写走 `flatbuf.py` 的字段级补丁：等长替换原地写字节，
变长替换把新字符串追加到 blob 末尾并回填 uoffset（不移动已有字节，结构零风险），
因此支持任意长度的文本替换。

转换完成后给输出文件追加 4 字节，使其 CRC32 与输入一致（见 `utils/crc.py`），
客户端的 catalog 校验自然通过 —— **不再需要改 `TableCatalog.bytes`**。

Provenance / credits
--------------------
* SQLCipher 接口参数（页 4096、KDF 256000、HMAC-SHA512、保留 80 字节）经社区工具链
  （BlueArchive-Tools, AGPL-3.0）确认 —— 仅作参考，**未使用其代码**。
* 默认密钥为社区公开流传值，作为可覆盖默认提供。
* 繁简映射来自 OpenCC 词典（Apache-2.0，见 `data/`）；本文件的库遍历逻辑为原创。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from . import db
from .config import DEFAULT_CONVERT, DEFAULT_KEY, DEFAULT_TABLE_PATTERN
from .convert import Converter
from .flatbuf import patch_blob
from .glossary import Glossary
from .utils import crc


@dataclass
class PatchStats:
    """一次补丁运行的统计。"""
    target_crc: int = 0
    final_crc: int | None = None
    rows_seen: int = 0
    rows_changed: int = 0
    fields_changed: int = 0   # 改动的字符串字段数（原地 + 追加）
    inplace: int = 0          # 等长原地写字段数
    appended: int = 0         # 变长追加字段数
    bytes_appended: int = 0   # 变长追加带来的 blob 增量
    kana_skipped: int = 0     # 因含假名跳过的字段数
    parse_failed: int = 0     # 无法按 FlatBuffer 解析而保留原样的行数
    tables: list[str] = field(default_factory=list)


def _make_transform(conv: Converter | None, glossary: Glossary | None) -> Callable[[str], str | None]:
    """文本改写链：先套译名对照表（键为繁体原文），再做 OpenCC 繁->简（见 glossary.py）。"""
    def transform(text: str) -> str | None:
        new = glossary.apply(text) if glossary else text
        if conv is not None:
            new = conv.convert(new)
        return None if new == text else new
    return transform


def patch_database(
    src: str,
    dst: str,
    *,
    key: str = DEFAULT_KEY,
    convert: str = DEFAULT_CONVERT,
    skip_kana: bool = True,
    tables: str = DEFAULT_TABLE_PATTERN,
    extra_bytes: bytes | None = None,
    glossary: Glossary | None = None,
    dry_run: bool = False,
    verify: bool = False,
    log=print,
) -> PatchStats:
    """把 src 库的文本按 convert 模式转换，写入 dst（CRC32 与 src 一致）。

    convert: tw2sp / t2s 做 OpenCC 繁->简；none 只做替换表（当前无替换表则无操作）。
    skip_kana: 含平/片假名的字段整体跳过（日文列是 GL 死数据，见设计文档 §6）。
    extra_bytes: CRC 修正前附加到输出末尾的自定义字节，修正后的 CRC 仍与输入一致。
    glossary: 译名对照表（先于 OpenCC 匹配，键为繁体原文）。
    dry_run 时直接只读打开 src 统计，不写任何文件。
    """
    if not os.path.exists(src):
        raise FileNotFoundError(f"输入不存在: {src}")
    if not dry_run and os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("--db 与 --out 不能是同一个文件（输入永远不被修改）")

    conv = Converter(convert) if convert != "none" else None
    if conv is not None:
        log(f"convert={convert}  phrases={len(conv.phrases)}  chars={len(conv.chars)}")
    else:
        log("convert=none（只做译名对照表）")
    if glossary is not None:
        log(f"glossary: {len(glossary.rules)} 条规则")
    transform = _make_transform(conv, glossary)
    log(f"kana-skip={'on' if skip_kana else 'off'}")

    stats = PatchStats(target_crc=crc.compute_crc32(src))
    log(f"输入 CRC32 = {stats.target_crc:08X}（输出将与之对齐）")

    def log_glossary_hits() -> None:
        """逐规则命中数：零命中 = 拼错/过期词条的主要排查线索。"""
        if glossary is None:
            return
        for old, new in glossary.rules.items():
            log(f"  glossary[{old} -> {new}] hits={glossary.hits[old]}")

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
                t_fields = t_inplace = t_appended = t_bytes = t_kana = t_bad = 0
                for rid, blob in rows:
                    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 16:
                        continue
                    try:
                        new_blob, bs = patch_blob(bytes(blob), transform, skip_kana=skip_kana)
                    except ValueError:
                        stats.parse_failed += 1
                        t_bad += 1
                        continue
                    stats.kana_skipped += bs.kana_skipped
                    t_kana += bs.kana_skipped
                    if new_blob is None:
                        continue
                    updates.append((new_blob, rid))
                    stats.rows_changed += 1
                    stats.fields_changed += bs.inplace + bs.appended
                    stats.inplace += bs.inplace
                    stats.appended += bs.appended
                    stats.bytes_appended += bs.bytes_appended
                    t_fields += bs.inplace + bs.appended
                    t_inplace += bs.inplace
                    t_appended += bs.appended
                    t_bytes += bs.bytes_appended
                if updates and not dry_run:
                    con.executemany(f"UPDATE [{table}] SET Bytes=? WHERE rowid=?", updates)
                    con.commit()
                if updates or t_kana or t_bad:
                    log(f"  [{table}] rows={len(rows)} changed={len(updates)} "
                        f"fields={t_fields} (inplace={t_inplace} appended={t_appended} "
                        f"+{t_bytes}B) kana_skipped={t_kana}"
                        + (f" parse_failed={t_bad}" if t_bad else ""))
                stats.rows_seen += len(rows)
        finally:
            con.close()

        if dry_run:
            log(f"[dry-run] rows scanned={stats.rows_seen} rows changed={stats.rows_changed} "
                f"fields={stats.fields_changed}（未写任何文件）")
            log_glossary_hits()
            return stats

        # 附加自定义字节（若有）：紧跟库数据之后、CRC 修正字节之前。
        # SQLite 按页计数读库，尾部多余字节会被忽略（与 CRC 修正的 +4 字节同理）。
        if extra_bytes:
            with open(work, "ab") as f:
                f.write(extra_bytes)
            log(f"已附加 extra_bytes：{len(extra_bytes)} 字节")

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

        log(f"rows scanned={stats.rows_seen} rows changed={stats.rows_changed} "
            f"fields={stats.fields_changed} (inplace={stats.inplace} appended={stats.appended} "
            f"+{stats.bytes_appended}B) kana_skipped={stats.kana_skipped}"
            + (f" parse_failed={stats.parse_failed}" if stats.parse_failed else ""))
        log_glossary_hits()
        log(f"output: {dst} ({os.path.getsize(dst) / 1048576:.1f} MB)")
        return stats
    except BaseException:
        # 绝不留下半成品：删除临时文件与未完成的输出。
        if os.path.exists(work) and os.path.abspath(work) != os.path.abspath(src):
            os.remove(work)
        if not dry_run and stats.final_crc is None and os.path.exists(dst):
            os.remove(dst)
        raise
