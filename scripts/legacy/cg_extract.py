"""Extract NIKKE story CGs from the local patch resource pools.

Pipeline:
  CIDX index -> CBLB zstd chunk -> UnityFS AssetBundle -> UnityPy -> PNG

Usage:
  python cg_extract.py probe           # survey all pools, list AssetBundle names
  python cg_extract.py marian          # export CGs whose asset name contains "marian"
  python cg_extract.py EventScene_     # any other keyword
"""
import collections
import io
import pathlib
import re
import struct
import sys
import time

import UnityPy
import zstandard as zstd
from PIL import Image

ROOT = pathlib.Path(r"F:\NIKKE\Unity\com_proximabeta_NIKKE\com.shiftup.patch")
OUT = pathlib.Path(__file__).resolve().parents[2] / "CG"
POOLS = ("dp", "core", "fd", "ja", "saus")


def records(sub):
    idx = (ROOT / sub / "chunk" / "store.cdb.idx").read_bytes()
    n = struct.unpack_from("<I", idx, 8)[0]
    for i in range(n):
        off, flag, size, crc = struct.unpack_from("<IIII", idx, 16 + i * 28 + 12)
        yield i, off, flag, size, idx[16 + i * 28:16 + i * 28 + 12]


def decompress(dec, comp):
    try:
        return dec.decompressobj().decompress(comp)
    except zstd.ZstdError:
        try:
            return dec.decompress(comp, max_output_size=256 * 1024 * 1024)
        except Exception:
            return None


def asset_names(data):
    """Return all readable asset names inside a UnityFS bundle."""
    names = []
    try:
        env = UnityPy.load(io.BytesIO(data))
        for obj in env.objects:
            try:
                if obj.type.name in ("Texture2D", "Sprite", "AssetBundle",
                                    "TextAsset", "MonoBehaviour"):
                    d = obj.read()
                    n = getattr(d, "m_Name", None) or getattr(d, "name", None)
                    if n:
                        names.append((obj.type.name, str(n)))
            except Exception:
                continue
    except Exception:
        return None
    return names


def save_textures(data, stem, outdir):
    saved = []
    try:
        env = UnityPy.load(io.BytesIO(data))
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            try:
                d = obj.read()
                name = getattr(d, "m_Name", "tex") or "tex"
                img = d.image
                if not isinstance(img, Image.Image):
                    img = img.convert("RGBA")
                safe = re.sub(r"[^\w.-]+", "_", name)
                dest = outdir / f"{stem}__{safe}.png"
                img.save(dest)
                saved.append((dest.name, img.size))
            except Exception as e:
                print("    texture fail", type(e).__name__, str(e)[:90])
    except Exception as e:
        print("    bundle fail", type(e).__name__, str(e)[:90])
    return saved


def main(keyword, probe=False):
    dec = zstd.ZstdDecompressor()
    outdir = OUT / re.sub(r"[^\w.-]+", "_", keyword)
    if not probe:
        outdir.mkdir(parents=True, exist_ok=True)
    allnames = collections.Counter()
    started = time.time()
    for sub in POOLS:
        cdb = ROOT / sub / "chunk" / "store.cdb"
        cdb_size = cdb.stat().st_size
        stats = collections.Counter()
        matched = []
        with cdb.open("rb") as fh:
            for i, off, flag, size, key in records(sub):
                stats["records"] += 1
                # uint32 offset + 4 GiB segment index carried in `flag`
                real = flag * 4294967296 + off
                if size <= 0 or real + size > cdb_size:
                    stats["bad"] += 1
                    continue
                fh.seek(real)
                comp = fh.read(size)
                data = decompress(dec, comp)
                if data is None:
                    stats["encrypted_or_unknown"] += 1
                    continue
                stats["zstd_ok"] += 1
                if not data.startswith(b"UnityFS"):
                    stats["not_unityfs"] += 1
                    continue
                stats["unityfs"] += 1
                names = asset_names(data)
                if names is None:
                    stats["unitypy_fail"] += 1
                    continue
                for typ, n in names:
                    allnames[n] += 1
                    if keyword.lower() in n.lower() and typ in ("Texture2D", "Sprite", "AssetBundle"):
                        matched.append((n, data, i, key.hex()))
        if probe:
            print(f"[{sub}] " + "  ".join(f"{k}={v}" for k, v in stats.most_common()))
        seen = set()
        for n, data, i, key in matched:
            if n in seen:
                continue
            seen.add(n)
            print(f"  HIT {sub}#{i} {n} key={key} bytes={len(data)}")
            if not probe:
                for fn, dim in save_textures(data, f"{sub}_{i:07d}_{re.sub(r'[^0-9A-Za-z_.-]+','_',n)[:60]}", outdir):
                    print("    ->", fn, dim)
        stats["hits"] = len(seen)
        if not probe:
            print(f"[{sub}] {dict(stats)}")
    print("elapsed", round(time.time() - started, 1), "s")
    print("distinct asset names seen:", len(allnames))
    if probe:
        print("sample names:")
        for n in list(allnames)[:40]:
            print("  ", n)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "marian"
    main(arg, probe=(arg == "probe"))
