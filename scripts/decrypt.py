"""Decrypt NIKKE StaticData.pack (local cache only).

Pipeline (matches NikkeTools/StaticData):
  1. key1/key2 = PBKDF2-HMAC-SHA256(fixed password, salt1/salt2, 10000, 32)
  2. AES-128-CBC(key2[:16], iv=key2[16:32], no padding) -> outer ZIP
  3. outer ZIP contains one entry named "data"
  4. AES-CTR(key1[:16], counter starts at key1[16:32], big-endian increment) -> StaticData.zip
  5. unpack all JSON tables
"""
import base64
import hashlib
import io
import pathlib
import zipfile
from Crypto.Cipher import AES

import config

BASE = config.BASE
RAW = config.DATA_RAW
PACK = config.STATIC_PACK
OUT = config.STATIC
PASSWORD = base64.b64decode(
    "y8Icb/P1B/UFusrUmCiEH/DROMdh39bmZJqFEz4aagxoDivE33L4xlXkexQ2GDun0SCBItGpGIRlEwvtowDl2Q=="
)


def keys_from_salts():
    d = RAW if (RAW / "_salt1.bin").exists() else BASE
    s1 = (d / "_salt1.bin").read_bytes()
    s2 = (d / "_salt2.bin").read_bytes()
    k1 = hashlib.pbkdf2_hmac("sha256", PASSWORD, s1, 10000, 32)
    k2 = hashlib.pbkdf2_hmac("sha256", PASSWORD, s2, 10000, 32)
    return k1, k2


def decrypt_ctr(data, key):
    ecb = AES.new(key[:16], AES.MODE_ECB)
    counter = bytearray(key[16:32])
    out = bytearray()
    for off in range(0, len(data), 16):
        ks = ecb.encrypt(bytes(counter))
        chunk = data[off:off + 16]
        out.extend(a ^ b for a, b in zip(chunk, ks))
        for i in range(15, -1, -1):
            counter[i] = (counter[i] + 1) & 0xFF
            if counter[i]:
                break
    return bytes(out)


def main():
    k1, k2 = keys_from_salts()
    raw = PACK.read_bytes()
    print(f"pack: {len(raw)} bytes")
    assert len(raw) % 16 == 0

    part1 = AES.new(k2[:16], AES.MODE_CBC, iv=k2[16:32]).decrypt(raw)
    print("layer1 head:", repr(part1[:32]))

    outer = zipfile.ZipFile(io.BytesIO(part1))
    names = outer.namelist()
    print("outer entries:", names[:10], "count", len(names))
    entry = next((n for n in names if pathlib.PurePosixPath(n).name == "data"), names[0])
    inner = outer.read(entry)
    print(f"inner entry: {entry} ({len(inner)} bytes)")

    final = decrypt_ctr(inner, k1)
    print("layer2 head:", repr(final[:32]))
    RAW.mkdir(exist_ok=True)
    (RAW / "StaticData.zip").write_bytes(final)

    z = zipfile.ZipFile(io.BytesIO(final))
    tables = z.namelist()
    print(f"StaticData.zip contains {len(tables)} files")
    OUT.mkdir(parents=True, exist_ok=True)
    for n in tables:
        dest = OUT / n
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(n))
    print("unpacked ->", OUT)
    for n in tables[:20]:
        print("  ", n)


if __name__ == "__main__":
    main()
