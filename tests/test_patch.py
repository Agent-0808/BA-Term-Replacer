"""patch.py 的测试：blob 等长替换 + 真实 SQLCipher 库端到端（含 CRC 对齐）。"""
import binascii
import os
import tempfile

import sqlcipher3

from batr.utils import crc
from batr.config import DEFAULT_KEY
from batr.convert import Converter
from batr.patch import convert_blob, patch_database


def test_convert_blob_equal_length() -> None:
    conv = Converter("t2s")
    blob = b"\x00" * 8 + "學園的檔案".encode() + b"\xff" * 4
    new, nchars = convert_blob(blob, conv)
    assert new is not None and len(new) == len(blob)
    assert "学园的档案".encode() in new
    assert nchars == 3  # 學→学、園→园、檔→档；「的/案」繁简同形不计


def test_convert_blob_non_cjk_untouched() -> None:
    conv = Converter("t2s")
    blob = b"\x00" * 8 + b"plain ascii only"
    assert convert_blob(blob, conv) == (None, 0)


def test_convert_blob_length_changing_falls_back_per_char() -> None:
    conv = Converter("tw2sp")
    blob = "軟體".encode()  # TWPhrasesRev: 軟體->软件（等长），保证不崩即可
    new, _ = convert_blob(blob, conv)
    assert new is not None and len(new) == len(blob)


def _make_db(path: str) -> None:
    con = sqlcipher3.connect(path)
    cur = con.cursor()
    cur.execute(f"PRAGMA key = \"x'{DEFAULT_KEY}'\"")
    cur.execute("CREATE TABLE LocalizeTest (Key INTEGER, Bytes BLOB)")
    blob = b"\x00" * 8 + "學園的檔案已經損毀".encode() + b"\xff" * 4
    cur.execute("INSERT INTO LocalizeTest VALUES (1, ?)", (blob,))
    con.commit()
    con.close()


def test_patch_database_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "ExcelDB.db")
        dst = os.path.join(tmp, "ExcelDB.cn.db")
        _make_db(src)

        src_crc = crc.compute_crc32(src)
        stats = patch_database(src, dst, tables=r"LocalizeTest", verify=True, log=lambda *_: None)

        # CRC 与输入一致；输入未被修改
        assert stats.final_crc == stats.target_crc == src_crc
        assert crc.compute_crc32(src) == src_crc
        assert os.path.getsize(dst) == os.path.getsize(src) + 4

        # 重新打开输出库，确认文本已转换、行数一致
        con = sqlcipher3.connect(dst)
        cur = con.cursor()
        cur.execute(f"PRAGMA key = \"x'{DEFAULT_KEY}'\"")
        assert cur.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        blob = cur.execute("SELECT Bytes FROM LocalizeTest WHERE Key=1").fetchone()[0]
        con.close()
        assert "学园的文件已经损毁".encode() in blob  # 默认 tw2sp：檔案->文件


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
