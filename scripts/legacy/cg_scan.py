"""Probe NIKKE CBLB chunk pools for story-CG AssetBundles.

CBLB layout (reverse engineered):
  store.cdb     : 256-byte header, then tightly packed zstd frames
  store.cdb.idx : "CIDX" | version(1) | count | crc, then count * 28-byte records
                  [12B hash][4B offset][4B flag][4B size][4B crc], + 12B trailer

Each zstd frame decompresses to one raw resource (often a complete UnityFS
AssetBundle). This script scans a pool and reports what kind of payloads it holds.
"""
import collections
import pathlib
import struct
import sys
import time

import zstandard as zstd

ROOT = pathlib.Path(r"F:\NIKKE\Unity\com_proximabeta_NIKKE\com.shiftup.patch")
OUT = pathlib.Path(__file__).resolve().parents[2] / "cg_probe"
KEYWORDS = (b"marian", b"eventscene", b"scenariobackground")


def records(sub):
    idx = (ROOT / sub / "chunk" / "store.cdb.idx").read_bytes()
    n = struct.unpack_from("<I", idx, 8)[0]
    for i in range(n):
        off, flag, size, crc = struct.unpack_from("<IIII", idx, 16 + i * 28 + 12)
        yield i, off, flag, size, idx[16 + i * 28:16 + i * 28 + 12]


def main(sub="dp", limit=0):
    dec = zstd.ZstdDecompressor()
    stats = collections.Counter()
    magic = collections.Counter()
    hits = []
    started = time.time()
    OUT.mkdir(exist_ok=True)
    cdb = ROOT / sub / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    with cdb.open("rb") as fh:
        for i, off, flag, size, key in records(sub):
            if limit and i >= limit:
                break
            stats["records"] += 1
            # CIDX offset is a uint32; the high 2 bits of the 64-bit file
            # position live in the flag field (one 4 GiB segment per flag).
            real = flag * 4294967296 + off
            if size <= 0 or real + size > cdb_size:
                stats["bad_range"] += 1
                continue
            fh.seek(real)
            comp = fh.read(size)
            magic[comp[:4].hex()] += 1
            try:
                try:
                    data = dec.decompressobj().decompress(comp)
                except zstd.ZstdError:
                    data = dec.decompress(comp, max_output_size=256 * 1024 * 1024)
            except Exception:
                stats["zstd_fail"] += 1
                continue
            stats["bytes_out"] += len(data)
            if data.startswith(b"UnityFS"):
                stats["unityfs_start"] += 1
            p = data.find(b"UnityFS")
            if p >= 0:
                stats["unityfs_any"] += 1
                stats["unityfs_at_%d" % (0 if p == 0 else 1)] += 1
            low = data.lower()
            if any(k in low for k in KEYWORDS):
                stats["keyword_hits"] += 1
                dest = OUT / f"{sub}_{i:07d}_{key.hex()}.bin"
                dest.write_bytes(data)
                hits.append((i, off, size, len(data), dest.name,
                             [k.decode() for k in KEYWORDS if k in low]))
    print("pool", sub, "elapsed", round(time.time() - started, 1), "s")
    for k, v in stats.most_common():
        print("  ", k, v)
    print("  magic top:", magic.most_common(6))
    print("  keyword hits:", len(hits))
    for h in hits[:40]:
        print("   ", h)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dp",
         int(sys.argv[2]) if len(sys.argv) > 2 else 0)
