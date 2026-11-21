"""Task 4: full HD rebuild pass -> dims audit + export of truly missing CGs.

Rebuilds every rebuildable hd bundle (scenariobackground + spineeventgame-
voltroad), lists the EventScene_* Texture2D actually inside, compares with
CG/ files (stem match, case-insensitive) including on-disk dimensions, and
exports ONLY textures that are absent from CG/ (>=512px, never overwrite).
Also verifies the identity->texture-name mapping for the whole rebuildable
set (audit2 verified it per-head; this makes it exhaustive).

Outputs:
  _cg_audit/full_hd_scan.json   per-bundle results (dims audit evidence)
  _cg_audit/extraction_log.md   human-readable log with noise scores
"""
import collections
import csv
import io
import json
import sys
import time
import traceback

import UnityPy
import zstandard as zstd
from PIL import Image, ImageFilter, ImageStat

sys.path.insert(0, r"E:/test/nikke_extract/_cg_audit")
import common  # noqa: E402
from cg_paths import classify, MIN_CG_SIDE  # noqa: E402

CG = common.BASE / "CG"


def noise_score(img):
    g = img.convert("L").resize((128, 128))
    return round(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).mean[0], 1)


def safe_name(name):
    return common.safe_name(name)


def disk_png_index():
    idx = {}
    for p in CG.rglob("*.png"):
        if p.name.endswith(".spine.png"):
            continue
        idx.setdefault(p.stem.lower(), p)
    return idx


def png_dims(p):
    with Image.open(p) as im:
        return [im.size[0], im.size[1]]


def main():
    inv = json.load((common.AUDIT / "inventory.json").open(encoding="utf-8"))
    have = disk_png_index()
    dec = zstd.ZstdDecompressor()

    jobs = []  # (pool, source_dict, identity)
    for k, e in inv["union"]["entries"].items():
        for s in e["sources"]:
            if s["rebuildable"] and s["quality"] == "hd" and s["group"] in (
                    "scenariobackground", "spineeventgame-voltroad"):
                jobs.append((s["pool"], s, e["identity"]))
    print("rebuildable hd jobs:", len(jobs))

    stores = {p: common.PoolStore(p) for p in {j[0] for j in jobs}}
    results = []
    stats = collections.Counter()
    exported = []
    t0 = time.time()

    for i, (pool, s, ident) in enumerate(jobs, 1):
        st = stores[pool]
        rec = {"identity": ident, "pool": pool, "group": s["group"],
               "key": s["key"], "status": "ok", "textures": [], "notes": []}
        try:
            bundle, n, miss = st.rebuild(s["file_id"])
            if miss or not bundle or not bundle.startswith(b"UnityFS"):
                rec["status"] = "rebuild_incomplete"
                rec["notes"].append(f"chunks={n} missing={miss}")
                stats["rebuild_incomplete"] += 1
                results.append(rec)
                continue
            env = UnityPy.load(io.BytesIO(bundle))
            texs = []
            for o in env.objects:
                if o.type.name != "Texture2D":
                    continue
                try:
                    t = o.read()
                    texs.append({"name": str(t.m_Name),
                                 "w": t.m_Width, "h": t.m_Height,
                                 "obj": t})
                except Exception as e:
                    rec["notes"].append(f"texread fail: {e}")
                    stats["texture_fail"] += 1
            rec["all_texture_names"] = [t["name"] for t in texs]
            es = [t for t in texs if t["name"].startswith("EventScene_")]
            expected = "EventScene_" + ident
            exact = any(t["name"].lower() == expected.lower() for t in es)
            rec["mapping_match"] = exact
            if not exact:
                rec["notes"].append(f"mapping mismatch: expected {expected}, got {[t['name'] for t in es]}")
                stats["mapping_mismatch"] += 1
            for t in es:
                entry = {"name": t["name"], "tex_dims": [t["w"], t["h"]]}
                disk = have.get(t["name"].lower())
                if disk:
                    entry["disk_file"] = str(disk)
                    try:
                        entry["disk_dims"] = png_dims(disk)
                    except Exception as e:
                        entry["disk_dims_error"] = str(e)
                    entry["present"] = True
                    stats["already_present"] += 1
                else:
                    entry["present"] = False
                if min(t["w"], t["h"]) < MIN_CG_SIDE:
                    entry["too_small"] = True
                    stats["too_small"] += 1
                    rec["textures"].append(entry)
                    continue
                if disk:
                    rec["textures"].append(entry)
                    continue
                # missing -> export (never overwrite; re-check right before save)
                try:
                    folder = CG / classify(t["name"])
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / (safe_name(t["name"]) + ".png")
                    stem_exists = dest.exists() or (t["name"].lower() in have)
                    if stem_exists:
                        entry["skipped"] = "exists (race/other folder)"
                        stats["skipped_exists"] += 1
                        rec["textures"].append(entry)
                        continue
                    im = t["obj"].image
                    if not isinstance(im, Image.Image):
                        im = im.convert("RGBA")
                    im.save(dest)
                    sc = noise_score(im)
                    entry["exported_to"] = str(dest)
                    entry["export_dims"] = [im.size[0], im.size[1]]
                    entry["bytes"] = dest.stat().st_size
                    entry["noise"] = sc
                    entry["suspicious"] = bool(sc > 50)
                    have[t["name"].lower()] = dest
                    exported.append({**entry, "identity": ident,
                                     "group": s["group"], "pool": pool,
                                     "folder": str(folder.relative_to(CG))})
                    stats["exported"] += 1
                    if sc > 50:
                        stats["suspicious"] += 1
                except Exception as e:
                    entry["export_error"] = f"{type(e).__name__}: {e}"
                    stats["export_fail"] += 1
                rec["textures"].append(entry)
            stats["bundles_ok"] += 1
        except Exception as e:
            rec["status"] = "error"
            rec["notes"].append(f"{type(e).__name__}: {e}")
            rec["trace"] = traceback.format_exc(limit=3)
            stats["bundle_error"] += 1
        results.append(rec)
        if i % 100 == 0:
            print(f"  {i}/{len(jobs)}  ok={stats['bundles_ok']} "
                  f"exported={stats['exported']}  {round(time.time()-t0)}s",
                  flush=True)

    for st in stores.values():
        st.close()

    (common.AUDIT / "full_hd_scan.json").write_text(
        json.dumps({"stats": dict(stats), "results": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- extraction log ----
    lines = ["# 提取日志 (audit4)", "",
             f"- 运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 可重建 HD bundle 总数: {len(jobs)} (scenariobackground(hd) 1237 + spineeventgame-voltroad(hd) 8)",
             f"- 统计: `{dict(stats)}`", ""]
    lines += ["## 映射全量验证", ""]
    mism = [r for r in results if r.get("status") == "ok" and not r.get("mapping_match")]
    lines.append(f"- 全量重建后逐 bundle 校验 `EventScene_<identity>` 命名: "
                 f"{'全部一致' if not mism else f'{len(mism)} 个不一致'}")
    for r in mism[:20]:
        lines.append(f"  - {r['identity']}: {r['notes']}")
    lines += ["", "## 导出明细", ""]
    if exported:
        lines += ["| CG 名 | 分类文件夹 | 尺寸 | 字节 | 噪声分 | 来源组 | 池 |",
                  "|---|---|---|---|---|---|---|"]
        for e in sorted(exported, key=lambda x: x["folder"]):
            lines.append(f"| {e['name']} | {e['folder']} | {e['export_dims'][0]}x{e['export_dims'][1]} "
                         f"| {e['bytes']} | {e['noise']} | {e['group']} | {e['pool']} |")
    else:
        lines.append("（无需导出的缺失 CG）")
    lines += ["", "## 过小/跳过/失败", ""]
    smalls = [t for r in results for t in r.get("textures", []) if t.get("too_small")]
    if smalls:
        lines.append("小于 512px 的 EventScene_* 纹理（不导出）:")
        for t in smalls:
            lines.append(f"- {t['name']} {t['tex_dims'][0]}x{t['tex_dims'][1]}")
    fails = [r for r in results if r["status"] != "ok"]
    if fails:
        lines.append("")
        lines.append("失败 bundle:")
        for r in fails:
            lines.append(f"- {r['identity']} ({r['pool']}): {r['status']} — "
                         f"{'; '.join(r.get('notes', []))}")
    spine_missing = list(csv.DictReader(
        (common.AUDIT / "missing_spine.csv").open(encoding="utf-8-sig")))
    lines += ["", "## spine 动态 CG 缺口（只报告，不在此处理）", ""]
    if spine_missing:
        for m in spine_missing:
            lines.append(f"- {m['CG名']} — bundle `{m['bundle key']}`")
    else:
        lines.append("无缺口。")
    (common.AUDIT / "extraction_log.md").write_text("\n".join(lines) + "\n",
                                                    encoding="utf-8")
    print("\nstats:", dict(stats))
    print("exported:", [e["name"] for e in exported])


if __name__ == "__main__":
    main()
