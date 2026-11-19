"""Inspect / dump any bundle from a pool by file_id or key substring.

    python scripts/probe_bundle.py --pool core --list skyontherock
    python scripts/probe_bundle.py --pool core --id 15257 --dump-textures out_dir
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2


def main() -> None:
    args = sys.argv[1:]
    pool = "core"
    if "--pool" in args:
        pool = args[args.index("--pool") + 1]
    needle = None
    fid = None
    if "--list" in args:
        needle = args[args.index("--list") + 1]
    if "--id" in args:
        fid = int(args[args.index("--id") + 1])
    dump = None
    if "--dump-textures" in args:
        dump = Path(args[args.index("--dump-textures") + 1])

    cat = sqlite3.connect(v2.manifest_path(pool))
    table = v2.cidx_map(pool)
    cdb = v2.ROOT / pool / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    dec = zstd.ZstdDecompressor()

    if needle:
        rows = cat.execute(
            "select file_id,key from files_chunktype where lower(key) like ?",
            (f"%{needle.lower()}%",),
        ).fetchall()
        for f, k in rows:
            print(f"  {f:>7}  {k}")
        if not fid:
            return
    if fid is None:
        return

    bundle, parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
    print(f"bundle={len(bundle) if bundle else 0:,} parts={parts} missing={missing}")
    if not bundle or not bundle.startswith(b"UnityFS"):
        print("not a UnityFS:", repr(bundle[:32]) if bundle else None)
        return
    env = UnityPy.load(io.BytesIO(bundle))
    counts = {}
    for o in env.objects:
        try:
            d = o.read()
            name = str(getattr(d, "m_Name", "") or "")
        except Exception as e:
            name = f"<err {type(e).__name__}>"
            d = None
        counts[o.type.name] = counts.get(o.type.name, 0) + 1
        size = ""
        if o.type.name == "Texture2D" and d is not None:
            size = f" {d.m_Width}x{d.m_Height}"
        print(f"  [{o.type.name}]{size}  {name}")
        if dump and o.type.name == "Texture2D" and d is not None:
            dump.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w.-]+", "_", name) or f"tex_{o.path_id}"
            d.image.save(dump / f"{safe}.png")
    print("counts", counts)


if __name__ == "__main__":
    main()
