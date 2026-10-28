"""flatbuf.py 的测试：手工构造最小 FlatBuffer，验证字段级解析与等长/变长补丁。"""
import struct

import pytest

from batr.flatbuf import BlobStats, iter_string_fields, patch_blob, read_string


def build_blob(fields: dict[int, str | int]) -> bytes:
    """构造最小 FlatBuffer（root 表 + vtable），fields: {slot: 字符串或整数标量}。

    布局（自前向后手工排布，偏移自洽即可）：
      0        : root uoffset -> 表对象
      4        : vtable（u16 vtable_len, u16 object_len, 每 slot 一个 u16 字段偏移）
      4+vt_len : 表对象（u32 soffset 指回 vtable；每 slot 一个 4 字节字段）
      其后     : 字符串数据（u32 长度 + UTF-8 + 0x00）
    """
    if not fields:
        raise ValueError("至少要有一个字段")
    max_slot = max(fields)
    vt_len = 4 + 2 * (max_slot + 1)
    vt_off = 4
    t_off = vt_off + vt_len
    obj_len = 4 + 4 * (max_slot + 1)

    parts = bytearray()
    parts += struct.pack("<I", t_off)              # root uoffset
    parts += struct.pack("<HH", vt_len, obj_len)   # vtable 头
    for slot in range(max_slot + 1):
        parts += struct.pack("<H", 4 + 4 * slot if slot in fields else 0)
    parts += struct.pack("<i", t_off - vt_off)     # 表对象 soffset -> vtable
    parts += b"\x00" * (obj_len - 4)               # 各字段的占位（随后回填）

    for slot, val in fields.items():
        fpos = t_off + 4 + 4 * slot
        if isinstance(val, str):
            data = val.encode("utf-8")
            spos = len(parts)
            parts += struct.pack("<I", len(data)) + data + b"\x00"
            struct.pack_into("<I", parts, fpos, spos - fpos)  # uoffset -> 字符串
        else:
            struct.pack_into("<I", parts, fpos, val)          # 标量字段
    return bytes(parts)


def texts_of(blob: bytes) -> list[str]:
    return [text for _, _, _, text in iter_string_fields(blob)]


def test_iter_string_fields_basic() -> None:
    blob = build_blob({0: "學園的檔案", 2: "平衡", 3: 0xDEADBEEF})
    # 标量槽位（slot 3 的值不指向合法字符串）不该被当成字符串产出
    fields = list(iter_string_fields(blob))
    assert [(slot, text) for slot, _, _, text in fields] == [(0, "學園的檔案"), (2, "平衡")]


def test_read_string_rejects_bad_targets() -> None:
    blob = build_blob({0: "學園", 1: 0x7FFFFFFF})  # slot1 标量指向 blob 之外
    (_, _, spos, _) = next(iter(iter_string_fields(blob)))
    assert read_string(blob, spos) == "學園"
    assert read_string(blob, 0) is None          # root uoffset 位置
    assert read_string(blob, len(blob)) is None  # 越界
    assert read_string(blob, 1 << 20) is None    # 越界
    # 不含 CJK 的字符串不产出（§4.3 条件 5）
    assert texts_of(build_blob({0: "plain ascii text!"})) == []


def test_patch_blob_equal_length_inplace() -> None:
    blob = build_blob({0: "學園的檔案"})
    root = blob[:4]
    new, stats = patch_blob(blob, lambda t: t.replace("學", "学"))
    assert new is not None and len(new) == len(blob)  # 等长 -> 不膨胀
    assert stats == BlobStats(inplace=1)
    assert texts_of(new) == ["学園的檔案"]
    assert new[:4] == root  # root uoffset 不动


def test_patch_blob_variable_length_appends() -> None:
    blob = build_blob({0: "星野", 1: "平衡"})
    (_, fpos0, _, _) = next(iter(iter_string_fields(blob)))
    root = blob[:4]

    def bump(text: str) -> str | None:
        return text + "记录" if text == "星野" else None  # 6B -> 12B，强制变长

    new, stats = patch_blob(blob, bump)
    # 对齐填充 2B + (4B 长度 + 12B 数据 + 1B NUL) = 19B
    assert stats == BlobStats(appended=1, bytes_appended=19)
    assert len(new) == len(blob) + stats.bytes_appended
    assert texts_of(new) == ["星野记录", "平衡"]
    # root 不动；回填后的 uoffset 指向末尾新串，且新串 4 字节对齐
    assert new[:4] == root
    new_spos = fpos0 + int.from_bytes(new[fpos0:fpos0 + 4], "little")
    assert new_spos > fpos0 and new_spos % 4 == 0
    # 旧字符串数据区逐字节未动（槽位 1 的目标串）
    old_spos1 = 20 + int.from_bytes(blob[20:24], "little")
    assert new[old_spos1:old_spos1 + 11] == blob[old_spos1:old_spos1 + 11]


def test_patch_blob_shared_string_appended_once() -> None:
    blob = bytearray(build_blob({0: "星野", 1: "平衡"}))
    (_, fpos0, spos0, _), (_, fpos1, _, _) = iter_string_fields(bytes(blob))
    struct.pack_into("<I", blob, fpos1, spos0 - fpos1)  # slot1 也指向 slot0 的字符串
    blob = bytes(blob)
    assert texts_of(blob) == ["星野", "星野"]

    new, stats = patch_blob(blob, lambda t: t + "記錄")
    assert stats.appended == 1  # 共享字符串只追加一次
    assert texts_of(new) == ["星野記錄", "星野記錄"]


def test_patch_blob_kana_skipped() -> None:
    blob = build_blob({0: "武器テスト", 1: "學園"})  # 槽位 0 含片假名
    new, stats = patch_blob(blob, lambda t: t + "!")
    assert stats.kana_skipped == 1
    # 含假名字段保持原样，另一个字段正常变长替换
    assert texts_of(new) == ["武器テスト", "學園!"]


def test_patch_blob_no_change_returns_none() -> None:
    blob = build_blob({0: "平衡"})
    assert patch_blob(blob, lambda t: None) == (None, BlobStats())
    assert patch_blob(blob, lambda t: t) == (None, BlobStats())


def test_patch_blob_invalid_structure_raises() -> None:
    with pytest.raises(ValueError):
        patch_blob(b"\x00" * 8 + "學園".encode() + b"\xff" * 4, lambda t: t)
    with pytest.raises(ValueError):
        patch_blob(b"", lambda t: t)
