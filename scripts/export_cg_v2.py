"""Correct, manifest-driven export of ALL NIKKE story CGs.

The earlier version guessed chunk order from physical proximity, which is
wrong for older assets (CBLB is a content-addressed, de-duplicated store).
This version uses the game's own manifest:

  <pool>/catalog.ndb  (NKDB-encrypted SQLite, decrypted with nkdb.py)
    files_chunktype : file_id -> bundle name
    chunk_file_map  : (chunk_id, file_id, file_offset)   <- authoritative order
    chunks          : (chunk_id, hash[16], original_size, compressed_size, pak_id, pak_offset)

  <pool>/chunk/store.cdb.idx (CIDX)
    28-byte records: [hash12][offset u32][segment u32][size u32][crc u32]
    catalog.hash[4:16] == CIDX hash12
    physical offset  = segment * 4 GiB + offset

  <pool>/chunk/store.cdb (CBLB)
    256-byte header, then tightly packed zstd frames; one frame per chunk.

For each CG bundle: look up its chunk list ordered by file_offset, read each
zstd frame, place decompressed bytes at file_offset, open with UnityPy and
export every EventScene_* Texture2D.
"""
import collections
import csv
import io
import pathlib
import re
import sqlite3
import struct
import sys
import time

import UnityPy
import zstandard as zstd
from PIL import Image, ImageFilter, ImageStat

import nkdb
from cg_paths import classify, MIN_CG_SIDE

import config

BASE = config.BASE
ROOT = config.GAME_PATCH
OUT = BASE / "CG"
LIST_DIR = OUT / "_清单"
POOLS = ("dp", "core")
GIB = 4294967296


def manifest_path(pool):
    dec = BASE / "catalogs" / f"{pool}_catalog.ndb.dec"
    if not dec.exists():
        dec.write_bytes(nkdb.decrypt(ROOT / pool / "catalog.ndb")[0])
    return dec


def cidx_map(pool):
    idx = (ROOT / pool / "chunk" / "store.cdb.idx").read_bytes()
    n = struct.unpack_from("<I", idx, 8)[0]
    table = {}
    for i in range(n):
        r = idx[16 + i * 28:16 + (i + 1) * 28]
        off, seg, size, crc = struct.unpack_from("<IIII", r, 12)
        table[r[:12]] = (seg * GIB + off, size)
    return table


def noise_score(img):
    """High = stripe/garbage. Normal illustrations are usually < 45."""
    g = img.convert("L").resize((128, 128))
    return round(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).mean[0], 1)


def cg_files(conn):
    """Yield (file_id, key), HD preferred over SD for the same CG."""
    rows = conn.execute(
        "select file_id,key from files_chunktype where lower(key) like '%eventscene%'"
    ).fetchall()
    def quality(key):
        return 0 if "(hd)" in key.lower() else 1
    rows.sort(key=lambda r: (quality(r[1]), r[0]))
    seen = set()
    for fid, key in rows:
        # dedupe by bundle identity ignoring the hd/sd tag and trailing hash
        m = re.search(r"assets_((?:eventscene_).+?)_[0-9a-f]{40}\.bundle", key, re.I)
        ident = m.group(1).lower() if m else key
        if ident in seen:
            continue
        seen.add(ident)
        yield fid, key


def rebuild(conn, table, cdb, dec, file_id, cdb_size):
    parts = conn.execute(
        """select m.file_offset, k.hash, k.original_size
           from chunk_file_map m join chunks k on k.chunk_id = m.chunk_id
           where m.file_id = ? order by m.file_offset""",
        (file_id,),
    ).fetchall()
    if not parts:
        return None, 0, 0
    buf = bytearray()
    missing = 0
    with cdb.open("rb") as fh:
        for foff, h, orig in parts:
            entry = table.get(h[4:16])
            if entry is None:
                missing += 1
                continue
            real, size = entry
            if size <= 0 or real + size > cdb_size:
                missing += 1
                continue
            fh.seek(real)
            data = dec.decompressobj().decompress(fh.read(size))
            if foff + len(data) > len(buf):
                buf.extend(b"\x00" * (foff + len(data) - len(buf)))
            buf[foff:foff + len(data)] = data
    return bytes(buf), len(parts), missing


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dec = zstd.ZstdDecompressor()
    report = []
    stats = collections.Counter()
    started = time.time()

    for pool in POOLS:
        cat = sqlite3.connect(manifest_path(pool))
        table = cidx_map(pool)
        cdb = ROOT / pool / "chunk" / "store.cdb"
        cdb_size = cdb.stat().st_size
        for fid, key in cg_files(cat):
            stats["bundles"] += 1
            bundle, nparts, missing = rebuild(cat, table, cdb, dec, fid, cdb_size)
            if missing or not bundle or not bundle.startswith(b"UnityFS"):
                stats["incomplete"] += 1
                continue
            try:
                env = UnityPy.load(io.BytesIO(bundle))
                objects = list(env.objects)
            except Exception:
                stats["unitypy_fail"] += 1
                continue
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
                    folder = OUT / classify(name)
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / (re.sub(r"[^\w.-]+", "_", name) + ".png")
                    if (folder / (dest.stem + ".spine.png")).exists():
                        # dynamic CG: keep the rendered illustration, don't overwrite with the sheet
                        stats["skipped_dynamic"] += 1
                        continue
                    img.save(dest)
                    sc = noise_score(img)
                    report.append((classify(name), name, img.size[0], img.size[1],
                                   dest.stat().st_size, sc, pool))
                    stats["exported"] += 1
                    if sc > 50:
                        stats["suspicious"] += 1
                except Exception:
                    stats["texture_fail"] += 1
            if stats["bundles"] % 300 == 0:
                print(f"  {stats['bundles']} bundles, {stats['exported']} CGs, "
                      f"{round(time.time()-started)}s", flush=True)
        cat.close()
        print(f"[{pool}] {dict(stats)}", flush=True)

    LIST_DIR.mkdir(exist_ok=True)
    with (LIST_DIR / "导出清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分类文件夹", "CG 名称", "宽度", "高度", "字节数", "噪声分", "资源池"])
        for row in sorted(set(report)):
            w.writerow(row)
    counts = collections.Counter(r[0] for r in set(report))
    with (LIST_DIR / "导出汇总.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分类文件夹", "CG 张数"])
        for k, v in sorted(counts.items()):
            w.writerow([k, v])
        w.writerow(["合计", sum(counts.values())])

    print("\nstats", dict(stats))
    print("elapsed", round(time.time() - started, 1), "s")
    scores = [r[5] for r in report]
    if scores:
        print("noise min/median/max", min(scores),
              sorted(scores)[len(scores) // 2], max(scores))
        print("suspicious (>50):", [r[1] for r in report if r[5] > 50][:20])


if __name__ == "__main__":
    main()
