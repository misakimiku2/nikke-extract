"""Task 3b: non-dialog family CG references at (file, CG) granularity.

For every family that is NOT one of the 6 Dialog families, record each
EventScene_* occurrence with its containing ASCII run (context), so path-like
references (livewallpaper/EventScene_xxx), spine variants (_mi/_si) and
fx_EventScene_* overlays stay distinguishable.

Output: _cg_audit/non_dialog_refs.json  (array of {family, file, offset, cg, context})
"""
import json
import re
from collections import Counter
from pathlib import Path

OUT = Path("E:/test/nikke_extract/_cg_audit")
STATIC = Path("E:/test/nikke_extract/staticdata")
TOKEN = re.compile(rb"[ -~]{4,}")

DIALOG_FAMILIES = {"ScenarioDialogTable", "EventScenarioDialogTable",
                   "AttractiveScenarioDialogTable", "SideStoryScenarioDialogTable",
                   "SideStorySpotDialogTable", "AttractiveCounselDialogTable"}

hits = json.loads((OUT / "_cache_cg_hits.json").read_text(encoding="utf-8"))

out = []
fam_stat = Counter()
for fname, ms in hits.items():
    fam = fname.split(".")[0]
    if fam in DIALOG_FAMILIES:
        continue
    fam_stat[fam] += len(ms)
    runs = {(m.start(), m.group().decode("ascii", "replace"))
            for m in TOKEN.finditer((STATIC / fname).read_bytes())}
    # map offset -> containing run
    spans = sorted(runs)
    for off, cg in ms:
        ctx = ""
        for so, s in spans:
            if so <= off < so + len(s):
                ctx = s
                break
        out.append({"family": fam, "file": fname, "offset": off,
                    "cg": cg, "context": ctx})

out.sort(key=lambda r: (r["family"], r["file"], r["offset"]))
(OUT / "non_dialog_refs.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"non_dialog_refs.json: {len(out)} occurrences in {len(fam_stat)} families")
for fam, n in fam_stat.most_common():
    print(f"  {fam:<42} {n}")
# context shapes
ctx_kinds = Counter()
for r in out:
    c = r["context"]
    if c == r["cg"]:
        ctx_kinds["standalone"] += 1
    elif c.startswith("livewallpaper/"):
        ctx_kinds["livewallpaper_path"] += 1
    elif c.startswith("spine/"):
        ctx_kinds["spine_path"] += 1
    elif c.startswith("fx_EventScene"):
        ctx_kinds["fx_EventScene_*"] += 1
    elif c.startswith("EventScene") and c != r["cg"]:
        ctx_kinds["compound_token"] += 1
    elif "Locale_" in c:
        ctx_kinds["inside_locale_key"] += 1
    else:
        ctx_kinds["other"] += 1
print("context kinds:", dict(ctx_kinds))
