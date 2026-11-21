"""Task 2: HD/SD overwrite verification + identity->texture mapping scan.

A) Pick 8 CG identities that exist in CG/, rebuild their HD bundle, read the
   real Texture2D dimensions, compare with the on-disk PNG dimensions, and try
   the SD twin to see how much of it the local store can even supply.
B) Rebuild ONE representative bundle for every distinct identity head and
   record the actual texture names, to verify the mapping
   texture_name == 'EventScene_' + bundle_identity (case-insensitive).

Outputs: _cg_audit/hdsd_check.json, _cg_audit/mapping_scan.json
"""
import collections
import io
import json
import pathlib
import sys

import UnityPy
from PIL import Image

sys.path.insert(0, r"E:/test/nikke_extract/_cg_audit")
import common  # noqa: E402

CG = common.BASE / "CG"


def disk_index():
    """stem(lower, without .spine.png) -> path, and all spine png stems."""
    il, sp = {}, set()
    for p in CG.rglob("*.png"):
        if p.name.endswith(".spine.png"):
            sp.add(p.stem[:-len(".spine")].lower() if p.stem.endswith(".spine")
                   else p.name[:-len(".spine.png")].lower())
            continue
        il.setdefault(p.stem.lower(), p)
    return il, sp


def tex_list(bundle):
    out = []
    env = UnityPy.load(io.BytesIO(bundle))
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        try:
            t = o.read()
            out.append({"name": str(t.m_Name), "w": t.m_Width, "h": t.m_Height})
        except Exception as e:
            out.append({"name": "<read fail>", "error": str(e)})
    return out


def rebuild_tex(store, fid):
    bundle, n, miss = store.rebuild(fid)
    if not bundle or not bundle.startswith(b"UnityFS"):
        return None, n, miss
    return tex_list(bundle), n, miss


def find_sources(inv, ident_low):
    return inv["union"]["entries"].get(ident_low, {}).get("sources", [])


def main():
    inv = json.load((common.AUDIT / "inventory.json").open(encoding="utf-8"))
    il, sp = disk_index()

    samples = ["absolute_02_1", "beautyfullshot_01", "bluewaterisland_02",
               "bowwowparadise_01_2", "cherryblossom_01_2", "acpufreeze_01_bg",
               "voltroad_sd_01_01", "chap_02_after_01"]
    stores = {}
    report = []
    for ident in samples:
        srcs = find_sources(inv, ident)
        row = {"identity": ident, "disk_file": None, "disk_dims": None,
               "hd": None, "sd": None}
        # on-disk file: EventScene_<identity>.png
        want = ("EventScene_" + ident).lower()
        p = il.get(want)
        if p:
            row["disk_file"] = str(p)
            with Image.open(p) as im:
                row["disk_dims"] = list(im.size)
        for s in srcs:
            pool = s["pool"]
            if pool not in stores:
                stores[pool] = common.PoolStore(pool)
            res, n, miss = rebuild_tex(stores[pool], s["file_id"])
            entry = {"pool": pool, "quality": s["quality"] or "none",
                     "chunks": n, "chunks_present_in_cidx": n - miss,
                     "rebuild_ok": res is not None,
                     "textures": res or []}
            if s["group"] == "scenariobackground" or s["group"] == "spineeventgame-voltroad":
                key = "hd" if s["quality"] == "hd" else ("sd" if s["quality"] == "sd" else "none")
                row[key] = entry
            else:
                row.setdefault("other_sources", []).append(entry)
        report.append(row)
        print(json.dumps(row, ensure_ascii=False))

    (common.AUDIT / "hdsd_check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- mapping scan: one bundle per identity head ----
    heads = collections.defaultdict(list)
    for k, e in inv["union"]["entries"].items():
        head = e["identity"].split("_")[0].lower()
        # prefer scenariobackground hd source, else any source
        pref = [s for s in e["sources"] if s["group"] == "scenariobackground" and s["quality"] == "hd"]
        pick = pref or e["sources"]
        heads[head].append((k, pick[0]))
    scan = []
    for head, items in sorted(heads.items()):
        ident, s = items[0]
        pool = s["pool"]
        if pool not in stores:
            stores[pool] = common.PoolStore(pool)
        res, n, miss = rebuild_tex(stores[pool], s["file_id"])
        expected = "eventscene_" + ident
        got = [t["name"] for t in (res or [])]
        es = [g for g in got if g.lower().startswith("eventscene_")]
        match = bool(es) and any(g.lower() == expected for g in es)
        scan.append({
            "head": head, "identity": ident, "pool": pool, "group": s["group"],
            "quality": s["quality"], "rebuild_ok": res is not None,
            "missing_chunks": miss, "texture_names": got,
            "expected": expected, "mapping_match": match,
        })
        flag = "OK " if match else "!! "
        print(f"{flag}{head:24s} {ident[:40]:40s} -> {got}")
    (common.AUDIT / "mapping_scan.json").write_text(
        json.dumps(scan, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [s for s in scan if not s["mapping_match"]]
    print(f"\nheads={len(scan)} mapping_match={len(scan)-len(bad)} mismatch={len(bad)}")
    for st in stores.values():
        st.close()


if __name__ == "__main__":
    main()
