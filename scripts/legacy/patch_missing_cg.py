"""Top up CGs whose asset name only appears in a non-first chunk.

Some AssetBundles do not expose their EventScene_* name in the first zstd
chunk, so cg_scan.py cached a middle chunk instead. For each of those, walk
backwards in physical order to the nearest UnityFS start, reassemble the whole
bundle, and export any EventScene Texture2D not already on disk.

Also keeps alternate sizes of a same-named texture (suffix __WxH.png).
"""
import csv
import io
import pathlib
import re
import struct
import time

import UnityPy
import zstandard as zstd
from PIL import Image

import export_all_cg as core

BASE = pathlib.Path(r"E:\test\nikke_extract")
PROBE = BASE / "cg_probe"
OUT = BASE / "CG" / "全量分类"


def existing():
    found = set()
    for f in OUT.rglob("*.png"):
        try:
            with Image.open(f) as im:
                # strip the __WxH suffix when comparing asset names
                stem = re.sub(r"__\d+x\d+$", "", f.stem)
                found.add((stem, im.size))
        except Exception:
            continue
    return found


def find_first_chunk(fh, recs, pos, dec, cdb_size):
    """Walk backwards to the nearest chunk whose payload starts with UnityFS."""
    for j in range(pos - 1, max(-1, pos - 400), -1):
        real, _, size = recs[j]
        if size <= 0 or real + size > cdb_size:
            continue
        fh.seek(real)
        data = core.decompress(dec, fh.read(size))
        if data and data.startswith(b"UnityFS"):
            total = core.unityfs_size(data)
            if total and 0 < total <= 512 * 1024 * 1024:
                return j, data, total
    return None


def main():
    recs, pos_of = core.build_index()
    dec = zstd.ZstdDecompressor()
    cdb_size = (core.POOL / "store.cdb").stat().st_size
    have = existing()
    new = []
    started = time.time()
    candidates = []
    for f in sorted(PROBE.glob("*.bin")):
        data = f.read_bytes()
        if b"EventScene_" in data and not data.startswith(b"UnityFS"):
            try:
                candidates.append(int(f.name.split("_")[1]))
            except Exception:
                pass
    print("non-first probe chunks:", len(candidates), flush=True)

    with (core.POOL / "store.cdb").open("rb") as fh:
        for k, idx in enumerate(candidates, 1):
            pos = pos_of.get(idx)
            if pos is None:
                continue
            hit = find_first_chunk(fh, recs, pos, dec, cdb_size)
            if not hit:
                continue
            start, head, total = hit
            buf = bytearray(head)
            for j in range(start + 1, len(recs)):
                real, _, size = recs[j]
                if size <= 0 or real + size > cdb_size:
                    continue
                fh.seek(real)
                chunk = core.decompress(dec, fh.read(size))
                if chunk is None:
                    continue
                buf.extend(chunk)
                if len(buf) >= total:
                    break
            if len(buf) < total:
                continue
            try:
                env = UnityPy.load(io.BytesIO(bytes(buf[:total])))
                objects = list(env.objects)
            except Exception:
                continue
            for obj in objects:
                if obj.type.name != "Texture2D":
                    continue
                try:
                    tex = obj.read()
                    name = str(getattr(tex, "m_Name", "") or "")
                    if not name.startswith("EventScene_") or min(tex.image.size) < core.MIN_CG_SIDE:
                        continue
                    img = tex.image
                    if not isinstance(img, Image.Image):
                        img = img.convert("RGBA")
                    if (name, img.size) in have:
                        continue
                    have.add((name, img.size))
                    folder = core.classify(name)
                    d = OUT / folder
                    d.mkdir(parents=True, exist_ok=True)
                    # same name, different size -> keep both, suffix the new one
                    plain = OUT / folder / (re.sub(r"[^\w.-]+", "_", name) + ".png")
                    suffix = "" if not plain.exists() else f"__{img.size[0]}x{img.size[1]}"
                    dest = OUT / folder / (re.sub(r"[^\w.-]+", "_", name) + suffix + ".png")
                    img.save(dest)
                    new.append((folder, name, img.size[0], img.size[1],
                                dest.stat().st_size, dest.name))
                except Exception:
                    continue
            if k % 20 == 0:
                print(f"  {k}/{len(candidates)} +{len(new)}", flush=True)

    if new:
        with (OUT / "补全清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["分类文件夹", "CG 名称", "宽度", "高度", "字节数", "文件名"])
            for row in sorted(new):
                w.writerow(row)
    print(f"added {len(new)} PNGs in {round(time.time()-started,1)}s")
    for row in sorted(new):
        print("  ", row)


if __name__ == "__main__":
    main()
