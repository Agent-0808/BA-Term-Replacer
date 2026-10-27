"""batr.utils.crc（原样取自 BAMT）的已知向量与自校验测试。"""
import binascii
import os
import tempfile

from batr.utils.crc import (
    apply_crc_fix,
    check_crc_match,
    compute_crc32,
    manipulate_file_crc,
)


def test_known_vector() -> None:
    assert binascii.crc32(b"123456789") == 0xCBF43926
    assert compute_crc32(b"123456789") == 0xCBF43926


def test_apply_crc_fix_roundtrip() -> None:
    data = b"hello, blue archive" * 37
    target = 0xDEADBEEF
    out = apply_crc_fix(data, target)
    assert out is not None
    assert binascii.crc32(out) == target
    assert out[:-4] == data  # 原内容不动，只追加 4 字节


def test_apply_crc_fix_identity_target() -> None:
    # 目标 = 原数据自身 CRC 时同样可解
    data = os.urandom(1000)
    out = apply_crc_fix(data, compute_crc32(data))
    assert out is not None and compute_crc32(out) == compute_crc32(data)


def test_manipulate_file_crc_appends_exactly_four_bytes() -> None:
    data = os.urandom(65536)
    target = 0x12345678
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        path = f.name
    try:
        assert manipulate_file_crc(path, target) is True
        assert os.path.getsize(path) == len(data) + 4
        assert compute_crc32(path) == target
        with open(path, "rb") as f:
            assert f.read(len(data)) == data
    finally:
        os.remove(path)


def test_check_crc_match() -> None:
    ok, c1, c2 = check_crc_match(b"abc", b"abc")
    assert ok and c1 == c2 == 891568578
    ok, _, _ = check_crc_match(b"abc", b"abd")
    assert not ok
