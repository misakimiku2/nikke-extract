"""Render high-resolution standing character art from the game's Spine models.

Source (dp pool):
  spinestandingcharactergroup(hd)_assets_spine/standing/c010/00_hd_*.bundle
    TextAsset  c010_00.atlas / c010_00.skel
    Texture2D  c010_00       2048² atlas sheet

Rendering one frame gives the 2048² standing illustration (what the lobby uses) —
much sharper than the 1024² card icons in `icons-char-full(hd)`.

  python scripts/export_char_standing.py --limit 4
  python scripts/export_char_standing.py

Output: staging/spine_stand/<name>/
        staging/char_render/<name>.png     (rendered 2048 still)
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import sqlite3
import subprocess
import time

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2

BASE = pathlib.Path(__file__).resolve().parents[1]
STAGING = BASE / "staging" / "spine_stand"
RENDER = BASE / "staging" / "char_render"
RUNTIME = BASE / "动态CG" / "runtime"
SIZE = 2048


def text_bytes(obj):
    s = obj.read().m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    return bytes(s or b"")


def bundles(cat):
    rows = cat.execute(
        "select file_id, key from files_chunktype"
        " where key like 'spinestandingcharactergroup(hd)%'"
    ).fetchall()
    # 同一角色皮肤可能有多个 bundle，按 key 排序保证稳定
    rows.sort(key=lambda r: r[1])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    STAGING.mkdir(parents=True, exist_ok=True)
    RENDER.mkdir(parents=True, exist_ok=True)

    cat = sqlite3.connect(v2.manifest_path("dp"))
    table = v2.cidx_map("dp")
    cdb = v2.ROOT / "dp" / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    dec = zstd.ZstdDecompressor()

    rows = bundles(cat)
    if args.limit:
        rows = rows[:args.limit]
    print(f"standing bundles: {len(rows)}", flush=True)

    stats = {"ok": 0, "rendered": 0, "fail": 0, "no_atlas": 0, "no_skel": 0, "incomplete": 0}
    started = time.time()
    for n, (fid, key) in enumerate(rows, 1):
        bundle, _p, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
        if missing or not bundle or not bundle.startswith(b"UnityFS"):
            stats["incomplete"] += 1
            continue
        try:
            env = UnityPy.load(io.BytesIO(bundle))
            objects = list(env.objects)
        except Exception:
            stats["fail"] += 1
            continue

        assets, textures = {}, []
        for o in objects:
            try:
                name = str(getattr(o.read(), "m_Name", "") or "")
            except Exception:
                continue
            if o.type.name == "TextAsset" and name.endswith((".atlas", ".skel")):
                assets[name] = o
            elif o.type.name == "Texture2D":
                textures.append((name, o))

        atlases = [k for k in assets if k.endswith(".atlas")]
        if not atlases:
            stats["no_atlas"] += 1
            continue
        base = atlases[0][:-len(".atlas")]
        if base + ".skel" not in assets:
            stats["no_skel"] += 1
            continue

        folder = STAGING / re.sub(r"[^\w.-]+", "_", base)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (base + ".atlas")).write_bytes(text_bytes(assets[base + ".atlas"]))
        (folder / (base + ".skel")).write_bytes(text_bytes(assets[base + ".skel"]))

        pick = next((o for nm, o in textures if nm == base), None)
        if pick is None and textures:
            pick = max(textures, key=lambda t: t[1].read().m_Width * t[1].read().m_Height)[1]
        if pick is None:
            stats["fail"] += 1
            continue
        pick.read().image.save(folder / (base + ".png"))
        stats["ok"] += 1

        out = RENDER / f"{base}.png"
        if out.exists():
            stats["rendered"] += 1
            continue
        p = subprocess.run(
            ["node", "render_static.mjs", str(folder), base, str(out), str(SIZE), "1.0"],
            cwd=str(RUNTIME), capture_output=True, text=True, timeout=180,
        )
        if p.returncode != 0 or not out.exists():
            stats["fail"] += 1
            print("  RENDER FAIL", base, p.stderr.strip()[:160], flush=True)
        else:
            stats["rendered"] += 1

        if n % 25 == 0:
            print(f"  {n}/{len(rows)} {stats} {round(time.time()-started)}s", flush=True)

    print("done", json.dumps(stats, ensure_ascii=False), f"{round(time.time()-started)}s")


if __name__ == "__main__":
    main()
