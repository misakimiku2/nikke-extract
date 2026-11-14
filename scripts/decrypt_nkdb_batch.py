"""Batch-decrypt every NKDB file found in the game patch into decrypted/.

Used after a game update: locale / catalog databases are refreshed in place,
keeping the same md5-style filenames, so downstream exports pick them up.

    python scripts/decrypt_nkdb_batch.py --dry-run
    python scripts/decrypt_nkdb_batch.py
    python scripts/decrypt_nkdb_batch.py --force
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import config
import nkdb

SUFFIXES = {".lsc", ".db", ".cat", ".ndb", ".dat"}


def candidates() -> list[Path]:
    out = []
    if not config.GAME_PATCH.exists():
        return out
    for raw in config.GAME_PATCH.glob("*/raw"):
        if not raw.is_dir():
            continue
        for p in raw.iterdir():
            if not p.is_file() or p.suffix.lower() not in SUFFIXES:
                continue
            try:
                with p.open("rb") as fh:
                    if fh.read(4) != b"NKDB":
                        continue
            except OSError:
                continue
            out.append(p)
    return sorted(out)


def main() -> None:
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    files = candidates()
    print(f"NKDB files: {len(files)}  (patch: {config.GAME_PATCH})")
    if not files:
        return
    config.DECRYPTED.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0
    started = time.time()
    for p in files:
        dest = config.DECRYPTED / (p.stem + ".dec")
        if dest.exists() and not force and dest.stat().st_mtime >= p.stat().st_mtime:
            skipped += 1
            continue
        if dry:
            print(f"  would decrypt {p.parent.parent.name}/{p.name} -> {dest.name}")
            continue
        try:
            data, info = nkdb.decrypt(p)
            dest.write_bytes(data)
            done += 1
            if done % 20 == 0:
                print(f"  {done} decrypted, {round(time.time()-started)}s", flush=True)
        except Exception as e:
            failed += 1
            print(f"  FAIL {p.name}: {type(e).__name__} {str(e)[:80]}")
    if dry:
        print("dry run only")
    else:
        print(f"decrypted {done}, skipped {skipped}, failed {failed} -> {config.DECRYPTED}")


if __name__ == "__main__":
    main()
