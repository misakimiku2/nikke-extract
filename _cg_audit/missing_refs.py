"""Task 5: check every referenced CG name against the exported CG/ library.

Rule (same as build_cg_index.resolve_cg): exact name (case-insensitive), else
strip trailing _N segments one at a time until a base matches, else missing.

Output: _cg_audit/missing_refs.csv
  CG名, 引用它的族, 次数, 缺失类型, 近似解析到, 近似资源类型, 是否Dialog引用
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path("E:/test/nikke_extract")
OUT = Path("E:/test/nikke_extract/_cg_audit")

# exported library
static_cg = {}
for f in (BASE / "CG").rglob("*.png"):
    if f.name.endswith(".spine.png"):
        continue
    static_cg.setdefault(f.stem.lower(), f)
dynamic_cg = {}
for a in (BASE / "CG").rglob("*.atlas"):
    dynamic_cg.setdefault(a.stem.lower(), a.parent)
print(f"exported: {len(static_cg)} static png, {len(dynamic_cg)} dynamic atlas")

DIALOG_FAMILIES = {"ScenarioDialogTable", "EventScenarioDialogTable",
                   "AttractiveScenarioDialogTable", "SideStoryScenarioDialogTable",
                   "SideStorySpotDialogTable", "AttractiveCounselDialogTable"}

refs = defaultdict(Counter)  # cg -> family -> count
dialog_names = set()
for r in json.loads((OUT / "story_refs.json").read_text(encoding="utf-8")):
    for cg in r["cg"]:
        refs[cg][r["family"]] += 1
        dialog_names.add(cg)
nondialog_names = set()
for r in json.loads((OUT / "non_dialog_refs.json").read_text(encoding="utf-8")):
    refs[r["cg"]][r["family"]] += 1
    nondialog_names.add(r["cg"])
print(f"distinct referenced names: dialog={len(dialog_names)} "
      f"non-dialog={len(nondialog_names)} union={len(refs)}")


def resolve(name: str):
    low = name.lower()
    if low in static_cg or low in dynamic_cg:
        kind = "静态" if low in static_cg else "动态"
        return name, "精确", kind
    cand, cur = [], low
    while True:
        m = re.match(r"^(.*)_\d+$", cur)
        if not m:
            break
        cur = m.group(1)
        cand.append(cur)
    for c in cand:
        if c in static_cg or c in dynamic_cg:
            kind = "静态" if c in static_cg else "动态"
            return c, "近似", kind
    return None, "精确缺", ""


rows = []
stats = Counter()
for cg, famc in refs.items():
    resolved, kind, res_kind = resolve(cg)
    stats[(kind, res_kind)] += 1
    fam_str = "; ".join(f"{f}:{n}" for f, n in sorted(famc.items()))
    total = sum(famc.values())
    rows.append({
        "CG名": cg,
        "引用它的族": fam_str,
        "次数": total,
        "缺失类型": kind,
        "近似解析到": resolved or "",
        "近似资源类型": res_kind,
        "是否Dialog引用": "是" if cg in dialog_names else "否",
    })

order = {"近似": 0, "精确缺": 1, "精确": 2}
rows.sort(key=lambda r: (-order[r["缺失类型"]], 0 if r["是否Dialog引用"] == "是" else 1,
                         -r["次数"], r["CG名"]))
with (OUT / "missing_refs.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["CG名", "引用它的族", "次数", "缺失类型",
                                       "近似解析到", "近似资源类型", "是否Dialog引用"])
    w.writeheader()
    w.writerows(rows)

print("match stats (kind, resource):", dict(stats))
missing_exact = [r for r in rows if r["缺失类型"] == "精确缺"]
approx = [r for r in rows if r["缺失类型"] == "近似"]
print(f"近似 rows: {len(approx)}, 精确缺 rows: {len(missing_exact)}")
dm = [r for r in missing_exact if r["是否Dialog引用"] == "是"]
print(f"dialog-only 精确缺: {len(dm)}")
for r in dm[:20]:
    print("   ", r["CG名"], r["引用它的族"], r["次数"])
print("written", OUT / "missing_refs.csv")
