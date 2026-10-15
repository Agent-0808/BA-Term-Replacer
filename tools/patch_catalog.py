"""Locate and rewrite the CRC32 of the ``ExcelDB.db`` entry inside ``TableCatalog.bytes``.

Why this is needed
------------------
The client verifies each resource file against the CRC32 recorded in the local
``TableCatalog.bytes``.  We changed the database, so its CRC32 changed; unless we also
update the catalog the client treats the file as corrupt and re-downloads it.

Entry layout
------------
    i32 keylen + key string      ("ExcelDB.db")
    i8, i32
    i32 namelen + name string
    i64 crc32                    <-- this is what we rewrite (upper 4 bytes are 0)
    bool
    i32 includes                 (-1 == none)

Note: the **Global** catalog stores only a CRC (no file size).  The Japanese catalog has
an extra size field — do not reuse a JP parser here.

Provenance
----------
The field layout above was derived from `assistance/patch_table_catalog.py` in
asfu222/BlueArchiveLocalizationTools (MIT License, Copyright (c) 2025 anon).
This file is an independent implementation: it locates the entry by searching for the
key string and validating the offset, instead of parsing the whole catalog sequentially.
See THIRD_PARTY.md.
"""
import argparse
import binascii
import struct


def crc32_file(path):
    crc = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            crc = binascii.crc32(b, crc)
    return crc & 0xFFFFFFFF


def find_entries(data, needle=b"ExcelDB.db"):
    out = []
    idx = 0
    while True:
        i = data.find(needle, idx)
        if i < 0:
            break
        idx = i + 1
        if i < 4:
            continue
        keylen = struct.unpack("<i", data[i - 4:i])[0]
        if keylen != len(needle):
            continue
        p = i + len(needle)
        # i8, i32
        p += 1 + 4
        if p + 4 > len(data):
            continue
        namelen = struct.unpack("<i", data[p:p + 4])[0]
        if namelen < 0 or namelen > 200 or p + 4 + namelen + 16 > len(data):
            continue
        p += 4
        name = data[p:p + namelen].decode("utf-8", "replace")
        p += namelen
        # 国际服(GL) 只有 CRC，没有 size 字段
        crc_pos = p
        crc = struct.unpack("<q", data[p:p + 8])[0]
        out.append(dict(key_pos=i - 4, name=name, crc=crc & 0xFFFFFFFF,
                        crc_pos=crc_pos))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect-crc", default="", help="原库的 CRC32（十六进制，用来确认定位正确）")
    ap.add_argument("--expect-crc-db", default="", help="直接给原库文件，自动算 CRC32 来定位")
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args()
    if args.expect_crc_db:
        args.expect_crc = f"{crc32_file(args.expect_crc_db):08X}"

    data = bytearray(open(args.catalog, "rb").read())
    print(f"catalog {len(data)} 字节")
    ents = find_entries(data)
    print(f"找到 {len(ents)} 个候选条目:")
    expect = int(args.expect_crc, 16) if args.expect_crc else None
    for e in ents:
        mark = "   <<== 就是这条（CRC 与原库一致）" if (expect is not None and e["crc"] == expect) else ""
        print(f"   name={e['name']!r} crc=0x{e['crc']:08X} @crc_pos={e['crc_pos']}{mark}")

    if args.list_only:
        return

    newcrc = crc32_file(args.db)
    print(f"\n新库 {args.db}: crc32=0x{newcrc:08X}")

    target = None
    for e in ents:
        if expect is not None and e["crc"] == expect:
            target = e
            break
    if target is None and ents:
        target = ents[0]
    if target is None:
        print("!! 没定位到条目")
        return

    # CRC 存在 8 字节里，高 4 字节保持 0
    struct.pack_into("<q", data, target["crc_pos"], newcrc)
    open(args.out, "wb").write(bytes(data))
    print(f"已写出 {args.out}")

    chk = find_entries(bytearray(open(args.out, "rb").read()))
    for e in chk:
        if e["crc_pos"] == target["crc_pos"]:
            print(f"复核: crc=0x{e['crc']:08X}  (期望 0x{newcrc:08X})")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
