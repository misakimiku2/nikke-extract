"""Task 3: missing-CG list by comparing catalog identities with CG/ contents.

Mapping bundle identity -> texture name is verified by audit2's per-head scan
(mapping_scan.json): every rebuildable scenariobackground(hd) and
spineeventgame-voltroad(hd) bundle holds exactly one EventScene_* texture
named EventScene_<identity> (case-insensitive). Livewallpaper bundles hold no
EventScene_* textures at all; spine group is checked for presence only.

Outputs:
  _cg_audit/missing_cgs.csv      (CG名, 池, bundle key, 画质, 分类文件夹)
  _cg_audit/missing_spine.csv    (spine 动态 CG 覆盖缺口, 单独报告)
  _cg_audit/missing_stats.json   (stats used by the pool report)
"""
import csv
import json
import sys

from pathlib import Path

sys.path.insert(0, r"E:/test/nikke_extract/_cg_audit")
import common  # noqa: E402
from cg_paths import classify  # noqa: E402

CG = common.BASE / "CG"


def existing_stems():
    """All non-spine png stems under CG/ (lowercased) -> path."""
    out = {}
    for p in CG.rglob("*.png"):
        if p.name.endswith(".spine.png"):
            continue
        out.setdefault(p.stem.lower(), p)
    return out


def spine_png_stems():
    out = set()
    for p in CG.rglob("*.spine.png"):
        out.add(p.stem[:-len(".spine")].lower())
    # dynamic CG pipeline outputs (动态CG/模型/<name>/)
    dyn = common.BASE / "动态CG" / "模型"
    if dyn.is_dir():
        for d in dyn.iterdir():
            if d.is_dir():
                out.add(d.name.lower())
    return out


def main():
    inv = json.load((common.AUDIT / "inventory.json").open(encoding="utf-8"))
    have = existing_stems()
    spine_have = spine_png_stems()
    print("existing non-spine png stems:", len(have))
    print("existing spine stems (CG + 动态CG/模型):", len(spine_have))

    missing = []
    present = 0
    per_folder = {}
    # If audit4 already ran, missing_cgs.csv documents the gap AS DISCOVERED
    # (pre-export), reconstructed deterministically from full_hd_scan.json.
    scan_file = common.AUDIT / "full_hd_scan.json"
    pre_export = scan_file.exists()
    scan_absent = set()
    if pre_export:
        scan = json.load(scan_file.open(encoding="utf-8"))
        for r in scan["results"]:
            for t in r.get("textures", []):
                if not t.get("present") and not t.get("too_small"):
                    scan_absent.add(t["name"].lower())
    for k, e in inv["union"]["entries"].items():
        # export candidates: rebuildable hd scenariobackground / voltroad
        cands = [s for s in e["sources"]
                 if s["rebuildable"] and s["group"] in
                 ("scenariobackground", "spineeventgame-voltroad")
                 and s["quality"] == "hd"]
        for s in cands:
            name = "EventScene_" + e["identity"]
            was_missing = pre_export and name.lower() in scan_absent
            is_present = name.lower() in have
            if is_present and not was_missing:
                present += 1
                continue
            # gap: either still missing now, or was the discovered gap that
            # audit4 exported afterwards (kept for the record)
            folder = classify(name)
            missing.append({
                "CG名": name, "池": s["pool"], "bundle key": s["key"],
                "画质": "hd", "分类文件夹": folder,
                "identity": e["identity"], "group": s["group"],
            })
            per_folder[folder] = per_folder.get(folder, 0) + 1

    # spine dynamic CG coverage (record only, never exported here)
    spine_missing = []
    spine_seen = set()
    spine_covered = 0
    for k, e in inv["union"]["entries"].items():
        srcs = [s for s in e["sources"] if s["group"] == "spineeventscenesgroup"]
        if not srcs:
            continue
        if k in spine_seen:
            continue
        spine_seen.add(k)
        name = "EventScene_" + e["identity"]
        if name.lower() in have or name.lower() in spine_have:
            spine_covered += 1
        else:
            spine_missing.append({"CG名": name, "identity": e["identity"],
                                  "bundle key": srcs[0]["key"]})

    # livewallpaper-only identities (no EventScene textures at all)
    lw_idents = [k for k, e in inv["union"]["entries"].items()
                 if all(s["group"] == "livewallpaperprefabs" for s in e["sources"])]

    out = common.AUDIT / "missing_cgs.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["CG名", "池", "bundle key", "画质", "分类文件夹"])
        for m in sorted(missing, key=lambda r: (r["分类文件夹"], r["CG名"])):
            w.writerow([m["CG名"], m["池"], m["bundle key"], m["画质"], m["分类文件夹"]])

    sp_out = common.AUDIT / "missing_spine.csv"
    with sp_out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["CG名", "identity", "bundle key"])
        for m in sorted(spine_missing, key=lambda r: r["CG名"]):
            w.writerow([m["CG名"], m["identity"], m["bundle key"]])

    stats = {
        "candidates_total": present + len(missing),
        "already_in_cg": present,
        "missing_total": len(missing),
        "missing_by_folder": per_folder,
        "missing_voltroad": sum(1 for m in missing if m["group"] == "spineeventgame-voltroad"),
        "spine_identities": len(spine_seen),
        "spine_covered": spine_covered,
        "spine_missing": len(spine_missing),
        "livewallpaper_only_identities": len(lw_idents),
    }
    (common.AUDIT / "missing_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    for m in missing[:15]:
        print("  MISS", m["CG名"], "|", m["分类文件夹"])


if __name__ == "__main__":
    main()
