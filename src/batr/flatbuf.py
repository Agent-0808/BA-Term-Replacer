"""FlatBuffer 字符串字段的解析与写回（patch / preview 共用的唯一实现）。

原理：每行 `Bytes` 是一个完整 FlatBuffer，根是一张表。字符串字段是一个
uoffset32（相对字段位置），指向 `[u32 长度][UTF-8][0x00]`。

只要**不移动任何已有字节**，所有旧偏移仍然有效，因此变长替换的做法是：
等长 → 原地写字节（零膨胀）；变长 → 把新字符串追加到 blob 末尾（4 字节对齐），
再把字段的 uoffset32 改成指向新位置。可行性实测见设计文档 §4.6
（54,075 个字段与官方 FlatBuffers runtime 交叉解析，0 处不匹配）。
"""
from __future__ import annotations

import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass

# §4.3：字符串长度上限，防止把二进制巧合当成字符串。
MAX_STRING_LEN = 1 << 20  # 1 MiB


def _is_cjk(ch: str) -> bool:
    """是否 CJK 表意文字（基本区 + 扩展 A + 兼容区 + 扩展 B 及以上）。"""
    cp = ord(ch)
    return (0x3400 <= cp <= 0x9FFF
            or 0xF900 <= cp <= 0xFAFF
            or 0x20000 <= cp <= 0x2FA1F)


def has_kana(text: str) -> bool:
    """文本是否含平/片假名（U+3040–U+30FF）——是则视为日文字段，整体跳过（§6 方案 B）。"""
    return any(0x3040 <= ord(ch) <= 0x30FF for ch in text)


def has_cjk(text: str) -> bool:
    """文本是否含 CJK 表意文字（与 `_is_cjk` 同义，供补丁链判断字段是否为目标语种）。"""
    return any(_is_cjk(ch) for ch in text)


def read_string(b: bytes | bytearray, spos: int, *, require_cjk: bool = True) -> str | None:
    """按 §4.3 六条硬校验读取 spos 处的字符串；任一条不满足返回 None。

    校验是安全边界：字段 uoffset 可能实际指向标量/向量，误判会改坏数据。
    require_cjk=False 时放行纯拉丁字段（如角色名的拉丁写法 "Kei"），只应配合 exact 匹配使用。
    """
    n = len(b)
    # 1. 位置落在数据区（0 处是 root uoffset，排除；至少要放得下长度前缀 + 1 字节）
    if not (4 <= spos <= n - 5):
        return None
    ln = int.from_bytes(b[spos:spos + 4], "little")
    # 2. 长度上限
    if ln > MAX_STRING_LEN:
        return None
    end = spos + 4 + ln
    # 3. 字符串必须以 0x00 结尾
    if end >= n or b[end] != 0x00:
        return None
    # 4. 严格 UTF-8 解码
    try:
        text = bytes(b[spos + 4:end]).decode("utf-8")
    except UnicodeDecodeError:
        return None
    # 5. 至少含一个 CJK 字符（日文假名/韩文/泰文/英文都不是目标）
    if require_cjk and not has_cjk(text):
        return None
    # 6. 除 \n 外不含控制字符
    if any(ord(ch) < 32 and ch != "\n" for ch in text):
        return None
    return text


def iter_string_fields(
    blob: bytes, *, allow_ascii: bool = False
) -> Iterator[tuple[int, int, int, str]]:
    """逐个产出表对象里的字符串字段 `(slot, fpos, spos, text)`。

    slot   : vtable 槽位序号（0 起）
    fpos   : 字段在 blob 内的绝对位置
    spos   : 字符串长度前缀的绝对位置
    allow_ascii: 同时产出不含 CJK 的字段（角色名的拉丁写法、资源路径等）
    结构不合法（root/vtable 越界等）抛 ValueError，由调用方决定保留原样。
    """
    n = len(blob)
    if n < 16:
        raise ValueError("blob too small")
    root = int.from_bytes(blob[0:4], "little")
    if not (4 <= root <= n - 4):
        raise ValueError("root out of range")
    # 表对象首字节是到 vtable 的 soffset（有符号）
    vt = root - int.from_bytes(blob[root:root + 4], "little", signed=True)
    if not (0 <= vt <= n - 4):
        raise ValueError("vtable out of range")
    vt_len = int.from_bytes(blob[vt:vt + 2], "little")
    if vt_len < 4 or vt_len % 2 != 0 or vt + vt_len > n:
        raise ValueError("bad vtable length")
    # u16 序号 0/1 是 vtable_len / object_len，字段偏移从序号 2 开始；
    # 偏移为 0 表示该字段使用默认值（字符串默认 null），跳过。
    for k in range(2, vt_len // 2):
        off = int.from_bytes(blob[vt + 2 * k:vt + 2 * k + 2], "little")
        if off == 0:
            continue
        fpos = root + off
        if fpos + 4 > n:
            continue  # 越界字段当不存在
        spos = fpos + int.from_bytes(blob[fpos:fpos + 4], "little")
        text = read_string(blob, spos, require_cjk=not allow_ascii)
        if text is not None:
            yield k - 2, fpos, spos, text


@dataclass
class BlobStats:
    """单个 blob 的补丁统计。"""
    inplace: int = 0         # 等长原地写字段数
    appended: int = 0        # 变长追加字段数
    bytes_appended: int = 0  # 追加带来的字节数（含对齐填充）
    kana_skipped: int = 0    # 因含假名跳过的字段数


def patch_blob(
    blob: bytes,
    transform: Callable[[str], str | None],
    *,
    skip_kana: bool = True,
    ascii_transform: Callable[[str], str | None] | None = None,
) -> tuple[bytes | None, BlobStats]:
    """对单个 FlatBuffer blob 做字段级文本补丁（§4.2 算法）。

    transform(text) 返回 None 或与原文相同表示不修改。
    ascii_transform: 不含 CJK 的字段（如角色名的拉丁写法 "Kei"）专用的变换；None 表示不处理这类字段。
        调用方应只做整字段（exact）匹配，不做子串，避免误伤资源路径与内部标识符。
    返回 (新 blob 或 None, 统计)；结构不合法抛 ValueError（调用方保留原 blob）。
    """
    b = bytearray(blob)
    stats = BlobStats()
    appended: dict[int, int] = {}  # spos -> 追加后的新 spos（共享字符串只追加一次）
    changed = False
    for _slot, fpos, spos, text in iter_string_fields(b, allow_ascii=ascii_transform is not None):
        if skip_kana and has_kana(text):
            stats.kana_skipped += 1
            continue
        fn = transform if has_cjk(text) else ascii_transform
        if fn is None:
            continue
        new_text = fn(text)
        if new_text is None or new_text == text:
            continue
        new_bytes = new_text.encode("utf-8")
        if len(new_bytes) == len(text.encode("utf-8")):
            # 等长：原地写，结构零风险。共享同一字符串的其他字段会一并生效（语义相同）。
            b[spos + 4:spos + 4 + len(new_bytes)] = new_bytes
            stats.inplace += 1
        else:
            # 变长：不移动已有字节，追加到末尾（4 字节对齐）+ 回填 uoffset。
            if spos in appended:  # 同一字符串被多个字段共享
                struct.pack_into("<I", b, fpos, appended[spos] - fpos)
                continue
            pad = (-len(b)) % 4
            b += b"\x00" * pad
            spos_new = len(b)
            b += struct.pack("<I", len(new_bytes)) + new_bytes + b"\x00"
            struct.pack_into("<I", b, fpos, spos_new - fpos)
            appended[spos] = spos_new
            stats.appended += 1
            stats.bytes_appended += pad + 4 + len(new_bytes) + 1
        changed = True
    return (bytes(b) if changed else None, stats)
