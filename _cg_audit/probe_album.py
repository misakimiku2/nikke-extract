"""Task 4 probe: dump token streams of Album* tables + search other CG naming schemes."""
import json
import re
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
AUD = Path("E:/test/nikke_extract/_cg_audit")
TOKEN = re.compile(rb"[ -~]{4,}")

for t in ["AlbumCategoryTable.mpk", "AlbumInfoTable.mpk", "AlbumResourceTable.mpk"]:
    raw = (STATIC / t).read_bytes()
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]
    print(f"\n===== {t}  size={len(raw)} tokens={len(toks)}")
    print(" | ".join(toks[:150]))

# Does AlbumResource use a different CG name scheme? check for common CG-ish tokens
print("\n===== search Album tables for asset-ish tokens")
for t in ["AlbumCategoryTable.mpk", "AlbumInfoTable.mpk", "AlbumResourceTable.mpk"]:
    raw = (STATIC / t).read_bytes()
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]
    interesting = [s for s in toks if re.search(r"(scene|Scene|cg|CG|illustr|Image|Texture|spine)", s)]
    print(f"\n-- {t}: {len(interesting)} asset-ish tokens")
    for s in interesting[:60]:
        print("   ", s)
