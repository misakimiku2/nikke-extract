"""Export every NIKKE Spine "dynamic CG" as an atlas PNG + .atlas + .skel triple.

Source: core/catalog.ndb (NKDB-encrypted SQLite), spineeventscenesgroup bundles,
reassembled through the authoritative chunk_file_map (see export_cg_v2.py).

Each bundle contains:
  Texture2D  <name>.png          atlas image
  TextAsset  <name>.atlas        region definitions
  TextAsset  <name>.skel         binary skeleton (Spine 4.1.x)
"""
import collections
import csv
import io
import pathlib
import re
import sqlite3
import sys
import time

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2

OUT = v2.BASE / "staging" / "spine"
CAT = v2.BASE / "catalogs" / "core_catalog.ndb.dec"
CD = v2.ROOT / "core" / "chunk" / "store.cdb"


def text_bytes(obj):
    """UnityPy may expose TextAsset.m_Script as str (surrogate-escaped) or bytes."""
    s = obj.read().m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    return bytes(s or b"")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cat = sqlite3.connect(CAT)
    table = v2.cidx_map("core")
    dec = zstd.ZstdDecompressor()
    cdb_size = CD.stat().st_size
    rows = cat.execute(
        "select file_id,key from files_chunktype where lower(key) like '%spineeventscenesgroup%'"
    ).fetchall()
    print("spine bundles:", len(rows), flush=True)

    report = []
    stats = collections.Counter()
    started = time.time()
    with CD.open("rb") as cdb_fh:
        for n, (fid, key) in enumerate(rows, 1):
            bundle, parts, missing = v2.rebuild(cat, table, CD, dec, fid, cdb_size)
            if missing or not bundle or not bundle.startswith(b"UnityFS"):
                stats["incomplete"] += 1
                continue
            try:
                env = UnityPy.load(io.BytesIO(bundle))
                objects = list(env.objects)
            except Exception:
                stats["unitypy_fail"] += 1
                continue

            assets = {}
            textures = []
            for o in objects:
                try:
                    name = str(getattr(o.read(), "m_Name", "") or "")
                except Exception:
                    continue
                if o.type.name == "TextAsset" and name.endswith((".atlas", ".skel", ".json")):
                    assets[name] = ("text", o)
                elif o.type.name == "Texture2D":
                    textures.append((name, o))

            atlases = [k for k in assets if k.endswith(".atlas")]
            if not atlases:
                stats["no_atlas"] += 1
                continue
            atlas_name = atlases[0]
            base = atlas_name[:-len(".atlas")]
            skel_name = base + ".skel"
            png_name = base + ".png"

            if skel_name not in assets:
                stats["no_skel"] += 1
                continue
            folder = OUT / re.sub(r"[^\w.-]+", "_", base)
            folder.mkdir(parents=True, exist_ok=True)

            (folder / atlas_name).write_bytes(text_bytes(assets[atlas_name][1]))
            (folder / skel_name).write_bytes(text_bytes(assets[skel_name][1]))

            # UnityPy drops the file extension from Texture2D.m_Name, so match
            # on the bare stem first, then fall back to the largest texture.
            want = png_name[:-4]
            pick = next((o for n, o in textures if n in (png_name, want)), None)
            if pick is None and len(textures) == 1:
                pick = textures[0][1]
            if pick is None and textures:
                pick = max(textures, key=lambda t: t[1].read().m_Width * t[1].read().m_Height)[1]
            if pick is not None:
                pick.read().image.save(folder / png_name)
                stats["with_atlas_png"] += 1
            else:
                stats["png_missing"] += 1

            skel = (folder / skel_name).read_bytes()
            m = re.search(rb"(\d+\.\d+\.\d+)", skel[:64])
            version = m.group(1).decode() if m else ""
            report.append((base, version, len(skel), (folder / png_name).stat().st_size
                           if (folder / png_name).exists() else 0, key))
            stats["exported"] += 1
            if n % 25 == 0:
                print(f"  {n}/{len(rows)} exported={stats['exported']} "
                      f"{round(time.time()-started)}s", flush=True)
    cat.close()

    with (OUT.parent / "模型清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["模型名", "Spine版本", "skel字节", "图集字节", "源bundle"])
        for r in sorted(report):
            w.writerow(r)
    print("\nstats", dict(stats))
    print("elapsed", round(time.time() - started, 1), "s ->", OUT)


if __name__ == "__main__":
    main()
