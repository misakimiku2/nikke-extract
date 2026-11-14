"""Export NIKKE story CGs from the local patch resource pool to PNG.

CBLB (store.cdb) stores every resource split into ~64 KiB zstd chunks. A
UnityFS AssetBundle therefore spans many chunks. This script reassembles the
bundles that start with a probed "EventScene_*" chunk and exports their
Texture2D objects.

Prerequisites: run `python cg_scan.py dp` once to populate cg_probe/.
"""
import io
import pathlib
import re
import struct
import sys

import UnityPy
import zstandard as zstd
from PIL import Image

BASE = pathlib.Path(__file__).resolve().parents[2]
PROBE = BASE / "cg_probe"
OUT = BASE / "CG"
POOL = pathlib.Path(r"F:\NIKKE\Unity\com_proximabeta_NIKKE\com.shiftup.patch\dp\chunk")
GIB = 4294967296


def unityfs_size(data):
    """Read the declared total bundle size from a UnityFS header."""
    if not data.startswith(b"UnityFS"):
        return None
    p = 12  # magic + version
    for _ in range(2):  # unity version string, runtime version string
        end = data.index(0, p)
        p = end + 1
    return struct.unpack_from(">Q", data, p)[0]


def build_index():
    idx = (POOL / "store.cdb.idx").read_bytes()
    n = struct.unpack_from("<I", idx, 8)[0]
    recs = []
    for i in range(n):
        off, flag, size, crc = struct.unpack_from("<IIII", idx, 16 + i * 28 + 12)
        recs.append((flag * GIB + off, i, size))
    recs.sort()
    return recs, {i: pos for pos, (_, i, _) in enumerate(recs)}


def decompress(dec, comp):
    try:
        return dec.decompressobj().decompress(comp)
    except zstd.ZstdError:
        try:
            return dec.decompress(comp, max_output_size=256 * 1024 * 1024)
        except Exception:
            return None


def main(pattern="Marian", outdir_name=None):
    outdir = OUT / (outdir_name or pattern)
    outdir.mkdir(parents=True, exist_ok=True)
    pat = re.compile(("EventScene_" + pattern + r"_[0-9_]+").encode(), re.I)

    targets = []
    for f in sorted(PROBE.glob("*.bin")):
        data = f.read_bytes()
        m = pat.search(data)
        if not m or not data.startswith(b"UnityFS"):
            continue
        total = unityfs_size(data)
        idx = int(f.name.split("_")[1])
        if total and total > len(data):
            targets.append((m.group().decode(), idx, total, data))
    print(f"found {len(targets)} CG bundles for pattern {pattern!r}")

    recs, pos_of = build_index()
    dec = zstd.ZstdDecompressor()
    cdb_size = (POOL / "store.cdb").stat().st_size
    written = []
    with (POOL / "store.cdb").open("rb") as fh:
        for name, idx, total, head in targets:
            pos = pos_of.get(idx)
            if pos is None:
                print("  no index position for", name, idx)
                continue
            buf = bytearray(head)
            used = 0
            for j in range(pos + 1, len(recs)):
                real, _, size = recs[j]
                if size <= 0 or real + size > cdb_size:
                    continue
                fh.seek(real)
                chunk = decompress(dec, fh.read(size))
                if chunk is None:
                    continue
                buf.extend(chunk)
                used += 1
                if len(buf) >= total:
                    break
            bundle = bytes(buf[:total])
            try:
                env = UnityPy.load(io.BytesIO(bundle))
                saved = 0
                for obj in env.objects:
                    if obj.type.name != "Texture2D":
                        continue
                    tex = obj.read()
                    img = tex.image
                    if not isinstance(img, Image.Image):
                        img = img.convert("RGBA")
                    dest = outdir / (re.sub(r"[^\w.-]+", "_", str(tex.m_Name)) + ".png")
                    img.save(dest)
                    written.append((str(tex.m_Name), img.size, dest.stat().st_size, dest.name))
                    saved += 1
                print(f"  {name:<32} {len(bundle):>9} B / {used:>3} chunks -> {saved} texture(s)")
            except Exception as e:
                print("  FAIL", name, type(e).__name__, str(e)[:120])

    print(f"\nexported {len(written)} PNGs -> {outdir}")
    for n, dim, sz, fn in written:
        print(f"  {n:<34} {dim[0]}x{dim[1]:<5} {sz/1024:8.1f} KB  {fn}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Marian",
         sys.argv[2] if len(sys.argv) > 2 else None)
