"""Dump every Image/RawImage node with its sprite name + world rect.

    python scripts/probe_ui_images.py --id 15257
"""
from __future__ import annotations

import io
import sqlite3
import sys

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2


def main() -> None:
    args = sys.argv[1:]
    fid = int(args[args.index("--id") + 1])
    pool = args[args.index("--pool") + 1] if "--pool" in args else "core"

    cat = sqlite3.connect(v2.manifest_path(pool))
    table = v2.cidx_map(pool)
    cdb = v2.ROOT / pool / "chunk" / "store.cdb"
    dec = zstd.ZstdDecompressor()
    bundle, parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb.stat().st_size)
    env = UnityPy.load(io.BytesIO(bundle))

    # map path_id -> object read data
    objs = {}
    for o in env.objects:
        try:
            objs[o.path_id] = (o.type.name, o.read())
        except Exception:
            objs[o.path_id] = (o.type.name, None)

    def sprite_name(pid):
        t, d = objs.get(pid, ("", None))
        if t != "Sprite" or d is None:
            return None
        tex = getattr(d, "m_Name", "")
        r = getattr(d, "m_Rect", None)
        rc = f"{r.width:.0f}x{r.height:.0f}" if r else ""
        return f"{tex} [{rc}]"

    rows = []
    for pid, (t, d) in objs.items():
        if t != "MonoBehaviour" or d is None:
            continue
        cls = type(d).__name__
        sp = getattr(d, "m_Sprite", None)
        if sp is None:
            continue
        sname = sprite_name(getattr(sp, "path_id", 0))
        if not sname:
            continue
        go = getattr(d, "m_GameObject", None)
        gname = ""
        if go is not None:
            tt, gd = objs.get(go.path_id, ("", None))
            if gd is not None:
                gname = getattr(gd, "m_Name", "")
        rows.append((gname, sname, cls))
    print(f"images: {len(rows)}")
    for g, s, c in sorted(rows):
        print(f"  {g:<34} {s:<46} {c}")


if __name__ == "__main__":
    main()
