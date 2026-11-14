"""DEPRECATED — DO NOT USE. Produces stripe-corrupted images.

Superseded by `export_cg_v2.py`, which uses the game's own catalog.ndb
manifest. This old version guessed chunk order from physical proximity in
store.cdb; CBLB is a content-addressed / de-duplicated store, so neighbouring
chunks often belong to DIFFERENT bundles. Only the newest assets (e.g. the
Marian event) happened to be stored contiguously and exported correctly.
Kept only as a record of the failed approach.

Original description follows:

Export ALL NIKKE story CGs from the local patch pool, sorted into folders.

Method (validated against the Marian event, 49/49 correct):
  * `cg_probe/*.bin` caches every decompressed chunk containing "EventScene".
    Those starting with UnityFS are the FIRST chunk of a CG AssetBundle.
  * A single AssetBundle spans dozens of ~64 KiB zstd chunks. Starting at the
    first chunk's physical position, walk the sorted CIDX records in physical
    order and append decompressed chunks until the UnityFS header's declared
    `fileSize` is reached.
  * Open the reassembled bundle with UnityPy and export every EventScene_*
    Texture2D as PNG, sorted into category folders.

Folder layout under OUT:
  01_活动剧情CG/<活动代号>/
  02_主线剧情CG/第NN章/
  03_支线剧情CG/
  04_角色过场/
  99_其他/
Plus 分类清单.csv / 分类汇总.csv.

Prerequisite: `python cg_scan.py dp` (populates cg_probe/).
"""
import collections
import csv
import io
import pathlib
import re
import struct
import sys
import time

import UnityPy
import zstandard as zstd
from PIL import Image

BASE = pathlib.Path(__file__).resolve().parents[2]
PROBE = BASE / "cg_probe"
OUT = BASE / "CG" / "全量分类"
POOL = pathlib.Path(r"F:\NIKKE\Unity\com_proximabeta_NIKKE\com.shiftup.patch\dp\chunk")
GIB = 4294967296
MIN_CG_SIDE = 512


def unityfs_size(data):
    if not data.startswith(b"UnityFS"):
        return None
    p = 12
    try:
        for _ in range(2):
            p = data.index(0, p) + 1
        return struct.unpack_from(">Q", data, p)[0]
    except Exception:
        return None


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


def classify(name):
    """Map an EventScene_* asset name to a folder path."""
    tail = name[len("EventScene_"):]
    parts = tail.split("_")
    head = parts[0]
    low = head.lower()

    if low == "chap":
        ch = next((p for p in parts[1:] if p.isdigit()), None)
        return f"02_主线剧情CG/第{int(ch):02d}章" if ch else "02_主线剧情CG/其他章节"
    if low == "side":
        return "03_支线剧情CG"
    if re.fullmatch(r"(c|ce)\d*", low):
        return "04_角色过场"
    if low in ("main", "event"):
        return "02_主线剧情CG/其他章节"
    if low in ("si", "mi", "ps", "at", "as"):
        return "99_其他"

    # numbered parts of one event (twoxtwolove1/2 -> TwoXTwoLove)
    merged = re.sub(r"\d+$", "", head) if len(head) >= 5 and not low.startswith("ce") else head
    if merged and len(merged) >= 4:
        head = merged
    return "01_活动剧情CG/" + head


def export_bundle(bundle, seen, counts, report, stats):
    if b"EventScene_" not in bundle:
        return
    try:
        env = UnityPy.load(io.BytesIO(bundle))
        objects = list(env.objects)
    except Exception:
        stats["unitypy_fail"] += 1
        return
    for obj in objects:
        if obj.type.name != "Texture2D":
            continue
        try:
            tex = obj.read()
            name = str(getattr(tex, "m_Name", "") or "")
            if not name.startswith("EventScene_"):
                continue
            img = tex.image
            if not isinstance(img, Image.Image):
                img = img.convert("RGBA")
            if min(img.size) < MIN_CG_SIDE:
                continue
            key = (name, img.size)
            if key in seen:
                stats["duplicate"] += 1
                continue
            seen.add(key)
            folder = classify(name)
            dest_dir = OUT / folder
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / (re.sub(r"[^\w.-]+", "_", name) + ".png")
            img.save(dest)
            counts[folder] += 1
            report.append((folder, name, img.size[0], img.size[1], dest.stat().st_size))
            stats["exported"] += 1
        except Exception:
            stats["texture_fail"] += 1


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = []
    for f in sorted(PROBE.glob("*.bin")):
        data = f.read_bytes()
        if not data.startswith(b"UnityFS") or b"EventScene_" not in data:
            continue
        total = unityfs_size(data)
        if not total or total <= len(data) or total > 512 * 1024 * 1024:
            continue
        try:
            idx = int(f.name.split("_")[1])
        except Exception:
            continue
        targets.append((idx, total, data))
    print(f"CG bundle first-chunks: {len(targets)}", flush=True)

    recs, pos_of = build_index()
    dec = zstd.ZstdDecompressor()
    cdb_size = (POOL / "store.cdb").stat().st_size
    seen, counts, report = set(), collections.Counter(), []
    stats = collections.Counter()
    started = time.time()

    with (POOL / "store.cdb").open("rb") as fh:
        for done, (idx, total, head) in enumerate(targets, 1):
            pos = pos_of.get(idx)
            if pos is None:
                stats["no_position"] += 1
                continue
            buf = bytearray(head)
            for j in range(pos + 1, len(recs)):
                real, _, size = recs[j]
                if size <= 0 or real + size > cdb_size:
                    continue
                fh.seek(real)
                chunk = decompress(dec, fh.read(size))
                if chunk is None:
                    continue
                buf.extend(chunk)
                if len(buf) >= total:
                    break
            if len(buf) < total:
                stats["incomplete"] += 1
                continue
            stats["reassembled"] += 1
            export_bundle(bytes(buf[:total]), seen, counts, report, stats)
            if done % 250 == 0:
                print(f"  {done}/{len(targets)} bundles, {stats['exported']} CGs, "
                      f"{round(time.time()-started)}s", flush=True)

    csv_path = OUT / "分类清单.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分类文件夹", "CG 名称", "宽度", "高度", "字节数"])
        for row in sorted(report):
            w.writerow(row)
    with (OUT / "分类汇总.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分类文件夹", "CG 张数"])
        for folder, n in sorted(counts.items()):
            w.writerow([folder, n])
        w.writerow(["合计", sum(counts.values())])

    print("\nstats:", dict(stats))
    print(f"exported {sum(counts.values())} CGs into {len(counts)} folders -> {OUT}")
    print(f"elapsed {round(time.time() - started, 1)} s")
    for folder, n in sorted(counts.items()):
        print(f"  {n:>4}  {folder}")


if __name__ == "__main__":
    main()
