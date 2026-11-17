import json
import pathlib
import struct

STATIC = pathlib.Path(r"E:\test\nikke_extract\staticdata")
b = (STATIC / "EquipmentOptionTable.mpk").read_bytes()
n = struct.unpack_from("<I", b, 0)[0]

off = 4
rows = []
while off < len(b) and len(rows) < n:
    if b[off] != 0x07:
        print("stop", off, hex(b[off]))
        break
    oid = struct.unpack_from("<I", b, off + 1)[0]
    off += 5
    # 字符串（description）
    desc = ""
    while off + 4 <= len(b):
        tag = struct.unpack_from("<i", b, off)[0]
        if tag >= 0:
            break
        off += 4
        ln = struct.unpack_from("<I", b, off)[0]
        off += 4
        s = b[off:off + ln].decode("utf-8", "replace")
        off += ln
        if tag == -45:
            desc = s
            break
    # 头数值：100, 2, 1000
    head = list(struct.unpack_from("<3i", b, off))
    off += 12
    cnt = struct.unpack_from("<i", b, off)[0]
    off += 4
    pairs = []
    for _ in range(cnt):
        if b[off] != 0x02:
            break
        gid, lv = struct.unpack_from("<2i", b, off + 1)
        pairs.append((gid, lv))
        off += 9
    tail = struct.unpack_from("<i", b, off)[0]
    off += 4
    rows.append({"id": oid, "desc": desc, "head": head, "tail": tail, "pairs": pairs})

print("parsed", len(rows), "of", n)
for r in rows:
    print(f"id={r['id']:3d} head={r['head']} tail={r['tail']} pairs={r['pairs']}")
    print(f"     {r['desc'][:60]}")
pathlib.Path(r"E:\test\nikke_extract\staging\equip_options_raw.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
