"""Unpack data_raw/StaticData.zip into staticdata/ (no game client needed).

The zip is produced by decrypt.py from the client's StaticData.pack. Keeping it
means this step can be re-run even if the game is uninstalled or updated.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ZIP = BASE / "data_raw" / "StaticData.zip"
OUT = BASE / "staticdata"


def main() -> None:
    if not ZIP.exists():
        print("missing", ZIP)
        raise SystemExit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()
        for n in names:
            dest = OUT / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(n))
    print(f"unpacked {len(names)} files -> {OUT}")
    if "--list" in sys.argv:
        for n in names[:20]:
            print("  ", n)


if __name__ == "__main__":
    main()
