"""Task 1: scan ALL staticdata files for EventScene_* references, aggregate by family.

Family = part of filename before the first '.'.
Outputs:
  _cg_audit/story_refs_by_family.csv   (family, files_with_refs, files_total, distinct_cg, total_refs)
  _cg_audit/_cache_cg_hits.json        ({filename: [[offset, cg_token], ...]}) for later tasks
  _cg_audit/_cache_family_files.json   ({family: [filenames]})
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
OUT = Path("E:/test/nikke_extract/_cg_audit")

CG_RAW = re.compile(rb"EventScene_[A-Za-z0-9_]+")

family_files = defaultdict(list)
hits = {}          # filename -> list of [offset, token]
family_stats = {}  # family -> [files_with_refs, distinct_set, total_refs]

files = sorted(STATIC.iterdir())
print(f"scanning {len(files)} files ...")

for i, f in enumerate(files):
    if not f.is_file():
        continue
    fam = f.name.split(".")[0]
    family_files[fam].append(f.name)
    data = f.read_bytes()
    ms = [(m.start(), m.group().decode("ascii", "replace")) for m in CG_RAW.finditer(data)]
    if ms:
        hits[f.name] = ms

for fname, ms in hits.items():
    fam = fname.split(".")[0]
    st = family_stats.setdefault(fam, [0, set(), 0])
    st[0] += 1
    st[1].update(t for _, t in ms)
    st[2] += len(ms)

rows = []
for fam, (nfiles, distinct, total) in family_stats.items():
    rows.append({
        "family": fam,
        "files_total": len(family_files[fam]),
        "files_with_refs": nfiles,
        "distinct_cg": len(distinct),
        "total_refs": total,
    })
rows.sort(key=lambda r: (-r["total_refs"], r["family"]))

with (OUT / "story_refs_by_family.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["family", "files_total", "files_with_refs",
                                       "distinct_cg", "total_refs"])
    w.writeheader()
    w.writerows(rows)

(OUT / "_cache_cg_hits.json").write_text(
    json.dumps(hits, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(OUT / "_cache_family_files.json").write_text(
    json.dumps({k: v for k, v in family_files.items()}, ensure_ascii=False), encoding="utf-8")

print(f"families scanned: {len(family_files)}, families with refs: {len(family_stats)}")
print(f"total refs {sum(r['total_refs'] for r in rows)}, "
      f"distinct overall names: {len({t for ms in hits.values() for _, t in ms})}")
for r in rows[:40]:
    print(f"  {r['family']:<42} files {r['files_with_refs']:>4}/{r['files_total']:<4} "
          f"distinct {r['distinct_cg']:>5} refs {r['total_refs']:>6}")
print("written", OUT / "story_refs_by_family.csv")
