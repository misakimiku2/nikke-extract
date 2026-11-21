"""Task 1: full inventory of every bundle key containing 'eventscene'.

Scans dp+core catalogs, parses CG identity / quality / group per bundle,
checks per-bundle chunk availability against the local CIDX, merges both
pools into a union keyed by CG identity, and explains prefix anomalies.
Output: _cg_audit/inventory.json
"""
import collections
import datetime
import json
import sys

sys.path.insert(0, r"E:/test/nikke_extract/_cg_audit")
import common  # noqa: E402


def scan_pool(pool):
    st = common.PoolStore(pool)
    keys = common.eventscene_keys(st.conn)
    bundles = []
    unparsed = []
    for fid, key in keys:
        parsed = common.parse_key(key)
        if parsed is None:
            unparsed.append({"file_id": fid, "key": key})
            continue
        group, ident, qual = parsed
        chunks = st.chunks_of(fid)
        in_idx = sum(1 for _, h, _ in chunks if h[4:16] in st.table)
        bundles.append({
            "file_id": fid,
            "key": key,
            "group": group,
            "identity": ident,
            "quality": qual,
            "chunks": len(chunks),
            "chunks_in_cidx": in_idx,
            "rebuildable": bool(chunks) and in_idx == len(chunks),
        })
    st.close()
    return bundles, unparsed


def main():
    inv = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "pools": {},
        "union": {},
        "anomalies": {},
    }
    for pool in common.POOLS:
        bundles, unparsed = scan_pool(pool)
        by_group = collections.Counter((b["group"], b["quality"]) for b in bundles)
        groups = collections.defaultdict(dict)
        for (g, q), n in by_group.items():
            groups[g][q or "none"] = n
        rebuildable = sum(1 for b in bundles if b["rebuildable"])
        inv["pools"][pool] = {
            "eventscene_bundles": len(bundles),
            "unparsed": unparsed,
            "by_group": dict(groups),
            "rebuildable_now": rebuildable,
            "bundles": bundles,
        }
        print(f"[{pool}] bundles={len(bundles)} rebuildable={rebuildable} "
              f"unparsed={len(unparsed)}")
        for g, qs in sorted(groups.items()):
            print("   ", g, dict(qs))

    # ---- union across pools, keyed by CG identity (lowercased) ----
    union = {}
    for pool, pdata in inv["pools"].items():
        for b in pdata["bundles"]:
            k = b["identity"].lower()
            e = union.setdefault(k, {
                "identity": b["identity"],
                "sources": [],
                "qualities": [],
            })
            e["sources"].append({
                "pool": pool,
                "group": b["group"],
                "quality": b["quality"],
                "file_id": b["file_id"],
                "key": b["key"],
                "chunks": b["chunks"],
                "chunks_in_cidx": b["chunks_in_cidx"],
                "rebuildable": b["rebuildable"],
            })
            if b["quality"] and b["quality"] not in e["qualities"]:
                e["qualities"].append(b["quality"])
    inv["union"] = {
        "identities": len(union),
        "with_hd_and_sd": sum(1 for e in union.values()
                              if "hd" in e["qualities"] and "sd" in e["qualities"]),
        "hd_only": sum(1 for e in union.values() if e["qualities"] == ["hd"]),
        "sd_only": sum(1 for e in union.values() if e["qualities"] == ["sd"]),
        "no_quality_tag": sum(1 for e in union.values() if not e["qualities"]),
        "entries": union,
    }
    print("union identities:", len(union),
          "hd+sd:", inv["union"]["with_hd_and_sd"])

    # ---- anomaly report: the 16 non-scenariobackground dp keys ----
    dp_groups = inv["pools"]["dp"]["by_group"]
    extra = {g: q for g, q in dp_groups.items() if g != "scenariobackground"}
    inv["anomalies"]["dp_non_scenariobackground"] = {
        "groups": extra,
        "explanation": (
            "spineeventgame-voltroad(hd/sd): 8+8 spine minigame CG bundles for "
            "the VOLTROAD event, keys look like "
            "spineeventgame-voltroad(hd)_assets_eventscene_voltroad_sd_01_01_<32hex>.bundle"
        ),
    }
    liv = [e for e in union.values()
           if any(s["group"] == "livewallpaperprefabs" for s in e["sources"])]
    spi = [e for e in union.values()
           if any(s["group"] == "spineeventscenesgroup" for s in e["sources"])]
    both = [e["identity"] for e in liv
            if any(s["group"] == "spineeventscenesgroup" for s in e["sources"])]
    inv["anomalies"]["core_groups"] = {
        "livewallpaperprefabs_identities": len(liv),
        "spineeventscenesgroup_identities": len(spi),
        "identities_in_both": len(both),
        "note": "livewallpaper bundles carry fx_* textures only (no EventScene_*); "
                "spine bundles carry the EventScene_* atlas texture + .atlas/.skel",
    }

    with (common.AUDIT / "inventory.json").open("w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)
    print("wrote inventory.json")


if __name__ == "__main__":
    main()
