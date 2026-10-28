"""patch.py 的测试：blob 字段级补丁 + 真实 SQLCipher 库端到端（含 CRC 对齐）。"""
import os
import tempfile

import sqlcipher3

from batr.utils import crc
from batr.config import DEFAULT_KEY
from batr.patch import patch_database
from test_flatbuf import build_blob


def test_patch_database_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "ExcelDB.db")
        dst = os.path.join(tmp, "ExcelDB.cn.db")
        _make_db(src)

        src_crc = crc.compute_crc32(src)
        stats = patch_database(src, dst, tables=r"LocalizeTest", verify=True, log=lambda *_: None)

        # CRC 与输入一致；输入未被修改；等长转换不膨胀（+4 是 CRC 修正字节）
        assert stats.final_crc == stats.target_crc == src_crc
        assert crc.compute_crc32(src) == src_crc
        assert os.path.getsize(dst) == os.path.getsize(src) + 4
        assert (stats.rows_changed, stats.fields_changed, stats.inplace) == (1, 1, 1)

        # 重新打开输出库，确认文本已转换、行数一致
        con = sqlcipher3.connect(dst)
        cur = con.cursor()
        cur.execute(f"PRAGMA key = \"x'{DEFAULT_KEY}'\"")
        assert cur.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        blob = cur.execute("SELECT Bytes FROM LocalizeTest WHERE Key=1").fetchone()[0]
        con.close()
        assert "学园的文件已经损毁".encode() in blob  # 默认 tw2sp：檔案->文件


def test_patch_database_extra_bytes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "ExcelDB.db")
        dst = os.path.join(tmp, "ExcelDB.extra.db")
        _make_db(src)

        src_crc = crc.compute_crc32(src)
        stats = patch_database(src, dst, tables=r"LocalizeTest", verify=True,
                               extra_bytes=b"\xde\xad\xbe\xef\x01", log=lambda *_: None)

        # 输出 = 库数据 + extra_bytes + 4 字节 CRC 修正，CRC 仍与输入一致
        assert stats.final_crc == src_crc
        assert os.path.getsize(dst) == os.path.getsize(src) + 5 + 4
        with open(dst, "rb") as f:
            f.seek(-9, os.SEEK_END)
            tail = f.read()
        assert tail[:-4] == b"\xde\xad\xbe\xef\x01"
        # 附加字节不影响 SQLite 读库（integrity_check 由 verify=True 已确认）


def test_patch_database_rejects_same_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "a.db")
        _make_db(src)
        try:
            patch_database(src, src, log=lambda *_: None)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


def _make_db(path: str) -> None:
    con = sqlcipher3.connect(path)
    cur = con.cursor()
    cur.execute(f"PRAGMA key = \"x'{DEFAULT_KEY}'\"")
    cur.execute("CREATE TABLE LocalizeTest (Key INTEGER, Bytes BLOB)")
    cur.execute("INSERT INTO LocalizeTest VALUES (1, ?)",
                (build_blob({0: "學園的檔案已經損毀"}),))
    con.commit()
    con.close()
