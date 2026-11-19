"""Compare today's catalog against the previous snapshot -> list newly added .bundle.

Run after a game update:
    python scripts/find_new_bundles.py            # decrypt + diff all pools
    python scripts/find_new_bundles.py --pool dp  # single pool
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import config
import nkdb

POOLS = ["core", "dp", "en", "ja", "ko", "fd", "saus"]
PAT = re.compile(rb"[ -~]{6,}")
SUFFIX = (b".bundle", b".prefab", b".png", b".webp", b".asset")


def names_of(blob: bytes) -> set[bytes]:
    out = set()
    for m in PAT.findall(blob):
        if m.endswith(SUFFIX):
            out.add(m)
    return out


def main() -> None:
    only = None
    if "--pool" in sys.argv:
        only = sys.argv[sys.argv.index("--pool") + 1]
    config.CATALOGS.mkdir(parents=True, exist_ok=True)
    outdir = config.BASE / "_update_check"
    outdir.mkdir(exist_ok=True)
    all_lines = []
    for pool in POOLS:
        if only and pool != only:
            continue
        src = config.GAME_PATCH / pool / "catalog.ndb"
        if not src.exists():
            print(f"[{pool}] no catalog.ndb, skip")
            continue
        newdec = config.CATALOGS / f"{pool}_catalog_new.dec"
        if not newdec.exists() or newdec.stat().st_mtime < src.stat().st_mtime:
            data, info = nkdb.decrypt(src)
            newdec.write_bytes(data)
            print(f"[{pool}] decrypted {len(data):,} bytes {info}", flush=True)
        newblob = newdec.read_bytes()
        olddec = config.CATALOGS / f"{pool}_catalog.ndb.dec"
        newnames = names_of(newblob)
        if olddec.exists():
            oldnames = names_of(olddec.read_bytes())
            added = sorted(newnames - oldnames)
            removed = len(oldnames - newnames)
        else:
            added = sorted(newnames)
            removed = -1
        print(f"[{pool}] total={len(newnames)} added={len(added)} removed={removed}")
        all_lines.append(f"### {pool}  added={len(added)} total={len(newnames)}")
        for a in added:
            all_lines.append("+" + a.decode("ascii", "replace"))
        all_lines.append("")
    dest = outdir / "added_bundles.txt"
    dest.write_text("\n".join(all_lines), encoding="utf-8")
    print("wrote", dest)


if __name__ == "__main__":
    main()
