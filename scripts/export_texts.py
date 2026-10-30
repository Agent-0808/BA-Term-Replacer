"""全量文本导出：把目标表的文本字段导出成可读 TSV（每表一个文件）。

用法（在仓库根目录）：
    uv run python scripts/export_texts.py work/db/ExcelDB.db
    uv run python scripts/export_texts.py work/db/ExcelDB.db --tables Localize   # 只导部分表
    uv run python scripts/export_texts.py work/db/ExcelDB.db --kana --ascii      # 连日文/拉丁字段一起导

格式：每表一个 <表名>.tsv（UTF-8 BOM，Excel 可直接打开），四列 rowid / key / slot / text，
每个文本字段一行。正文里的 Tab 与换行转义成字面 \\t / \\n，保证一行一条、可直接 grep。
rowid + slot 是改回数据库的锚点；key 列取表中第一个非 Bytes 列（列名不统一：Key/Id/StringId）。
默认只导中文字段（同打补丁的目标）；假名（日文死数据）与纯拉丁字段分别用 --kana / --ascii 开启。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tap import Positional, Tap  # noqa: E402

from batr import db as batr_db  # noqa: E402
from batr.config import DEFAULT_KEY, DEFAULT_OUT_DIR, DEFAULT_TABLE_PATTERN  # noqa: E402
from batr.flatbuf import has_cjk, has_kana, iter_string_fields  # noqa: E402


class ExportArgs(Tap):
    """把数据库文本导出成每表一个 TSV。"""

    db: Positional[Path]  # ExcelDB.db 路径
    out: Path = Path(DEFAULT_OUT_DIR) / "tables"  # 导出目录（每表一个 <表名>.tsv）
    tables: str = DEFAULT_TABLE_PATTERN  # 表名正则过滤
    kana: bool = False  # 连含假名字段一起导（默认跳过：日文列是 GL 死数据）
    ascii: bool = False  # 连纯拉丁字段一起导（资源路径等，量大且通常无用）


def _key_column(con, table: str) -> str | None:
    """表的键列名：第一个非 Bytes 列（Key/Id/StringId...），取不到返回 None。"""
    cols = con.execute(f"PRAGMA table_info([{table}])").fetchall()
    for _cid, name, *_rest in cols:
        if name.lower() != "bytes":
            return name
    return None


def _escape(text: str) -> str:
    """正文内联化：Tab / 换行转义成字面 \\t / \\n，保证一行一条。"""
    return text.replace("\t", "\\t").replace("\n", "\\n")


def export_table(con, table: str, out_path: Path, *, kana: bool, ascii_on: bool) -> int:
    """导出一张表，返回写出的字段数。"""
    keycol = _key_column(con, table)
    key_expr = f"[{keycol}]" if keycol else "''"
    key_header = keycol or "key"
    rows = con.execute(f"SELECT rowid, {key_expr}, Bytes FROM [{table}]").fetchall()
    written = 0
    with out_path.open("w", encoding="utf-8-sig", newline="\n") as f:
        f.write(f"rowid\t{key_header}\tslot\ttext\n")
        for rowid, key, blob in rows:
            if not isinstance(blob, (bytes, bytearray)) or len(blob) < 16:
                continue
            try:
                fields = list(iter_string_fields(bytes(blob), allow_ascii=ascii_on))
            except ValueError:
                continue
            for slot, _fpos, _spos, text in fields:
                if has_kana(text):
                    if not kana:
                        continue
                elif not has_cjk(text) and not ascii_on:
                    continue
                f.write(f"{rowid}\t{key}\t{slot}\t{_escape(text)}\n")
                written += 1
    return written


def main() -> None:
    args = ExportArgs().parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    con = batr_db.connect(str(args.db), DEFAULT_KEY)
    total_tables = total_fields = 0
    try:
        for table in batr_db.select_tables(con, args.tables):
            n = export_table(con, table, args.out / f"{table}.tsv",
                             kana=args.kana, ascii_on=args.ascii)
            total_tables += 1
            total_fields += n
            print(f"  {table}: {n}")
    finally:
        con.close()
    print(f"=== {total_tables} 张表，{total_fields} 个字段 → {args.out}/ ===")


if __name__ == "__main__":
    main()
