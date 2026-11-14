"""Decrypt ShiftUp NKDB files (catalog.ndb / *.lsc / *.cat / *.db).

Header: "NKDB" | version(u32 BE) | aesKey(16B) | segmentSize(u32 BE) | segmentCount(u32 BE)
        then (segmentCount+1) big-endian offsets (4 or 5 bytes each)
Each segment: AES-128-OFB(key, iv=int32le(index)+int32le(offset)+8 zero) then zlib.
"""
import struct
import zlib
from pathlib import Path
from Crypto.Cipher import AES


def decrypt(path):
    data = Path(path).read_bytes()
    if data[:4] != b"NKDB":
        raise ValueError("not NKDB: " + repr(data[:8]))
    version = struct.unpack(">I", data[4:8])[0]
    key = data[8:24]
    seg_size, seg_count = struct.unpack(">II", data[24:32])
    nbytes = 5 if seg_size * seg_count > 0xFFFFFFFF else 4
    pos = 32
    offsets = []
    for _ in range(seg_count + 1):
        offsets.append(int.from_bytes(data[pos:pos + nbytes], "big"))
        pos += nbytes
    out = bytearray()
    ecb = AES.new(key, AES.MODE_ECB)
    for i in range(seg_count):
        off, length = offsets[i], offsets[i + 1] - offsets[i]
        seg = data[off:off + length]
        iv = struct.pack("<ii", i, off & 0xFFFFFFFF) + b"\x00" * 8
        ks = iv
        plain = bytearray()
        for j in range(0, len(seg), 16):
            ks = ecb.encrypt(ks)
            plain.extend(a ^ b for a, b in zip(seg[j:j + 16], ks))
        out.extend(zlib.decompress(bytes(plain)))
    return bytes(out), dict(version=version, seg_size=seg_size, seg_count=seg_count, first_offset=offsets[0])


if __name__ == "__main__":
    import sys
    p = sys.argv[1]
    d, info = decrypt(p)
    print(p, "->", len(d), "bytes", info)
    print("head:", repr(d[:160]))
    dest = Path(r"E:\test\nikke_extract\decrypted") / (Path(p).stem + ".dec")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(d)
    print("saved:", dest)
