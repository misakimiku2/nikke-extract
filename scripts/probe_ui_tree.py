"""Dump the GameObject/RectTransform hierarchy of a UI bundle, with sprite refs.

    python scripts/probe_ui_tree.py --id 15257 [--max 400]
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
    limit = int(args[args.index("--max") + 1]) if "--max" in args else 500

    cat = sqlite3.connect(v2.manifest_path(pool))
    table = v2.cidx_map(pool)
    cdb = v2.ROOT / pool / "chunk" / "store.cdb"
    dec = zstd.ZstdDecompressor()
    bundle, parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb.stat().st_size)
    print(f"bundle {len(bundle):,} parts={parts} missing={missing}")
    env = UnityPy.load(io.BytesIO(bundle))

    # index objects
    go, tr = {}, {}
    for o in env.objects:
        if o.type.name == "GameObject":
            go[o.path_id] = o
        elif o.type.name in ("RectTransform", "Transform"):
            tr[o.path_id] = o

    def name_of(pid):
        o = go.get(pid)
        if not o:
            return "?"
        try:
            return str(o.read().m_Name)
        except Exception:
            return "?"

    # children map: transform -> list of transform path_id
    children = {}
    parent = {}
    for pid, o in tr.items():
        try:
            d = o.read()
        except Exception:
            continue
        p = getattr(d, "m_Father", None)
        pfid = getattr(p, "path_id", 0) if p else 0
        parent[pid] = pfid
        children.setdefault(pfid, []).append(pid)

    roots = [pid for pid in tr if parent.get(pid, 0) == 0]

    out = []

    def walk(pid, depth):
        if len(out) > limit:
            return
        o = tr[pid]
        try:
            d = o.read()
        except Exception:
            return
        gname = name_of(getattr(d, "m_GameObject", None).path_id if getattr(d, "m_GameObject", None) else 0)
        pos = ""
        if o.type.name == "RectTransform":
            ap = getattr(d, "m_AnchoredPosition", None)
            sd = getattr(d, "m_SizeDelta", None)
            sc = getattr(d, "m_LocalScale", None)
            if ap is not None:
                pos = f" pos=({ap.x:.1f},{ap.y:.1f}) size=({sd.x:.1f},{sd.y:.1f})"
            if sc is not None and (abs(sc.x - 1) > 0.001 or abs(sc.y - 1) > 0.001):
                pos += f" scale=({sc.x:.2f},{sc.y:.2f})"
        active = ""
        g = go.get(getattr(d, "m_GameObject", None).path_id if getattr(d, "m_GameObject", None) else 0)
        if g is not None:
            try:
                if not g.read().m_IsActive:
                    active = " [inactive]"
            except Exception:
                pass
        out.append("  " * depth + f"- {gname}{pos}{active}")
        for c in children.get(pid, []):
            walk(c, depth + 1)

    for r in roots:
        walk(r, 0)
    print("\n".join(out))


if __name__ == "__main__":
    main()
