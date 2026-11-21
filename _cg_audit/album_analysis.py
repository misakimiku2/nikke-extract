"""Task 4: parse Album*/LiveWallpaper tables and emit album_list.json + album_notes.md.

Conclusions encoded here (verified by probes):
  * AlbumCategoryTable: archive category tabs  [name_key, desc_key, tab_asset]
  * AlbumInfoTable:    chapter/building info   [locale_table, title_key, img_album_*]
  * AlbumResourceTable: story-replay archive   [desc_key_1, desc_key_2, dialog_group]
  * LiveWallpaperTable: the CG gallery (动态壁纸) [name_key, desc_key, path, _mi, _si, bgm]
"""
import json
import re
from collections import Counter
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
OUT = Path("E:/test/nikke_extract/_cg_audit")
TOKEN = re.compile(rb"[ -~]{4,}")


def toks(name: str) -> list[str]:
    return [m.group().decode("ascii", "replace") for m in TOKEN.finditer((STATIC / name).read_bytes())]


def unpadded(g: str) -> str:
    return re.sub(r"_0*(\d+)", lambda m: "_" + str(int(m.group(1))), g)


# ---------------- AlbumCategoryTable ----------------
cat_rows, i = [], 0
t = toks("AlbumCategoryTable.mpk")
while i + 2 < len(t):
    if t[i].startswith("Locale_System:ALBUM_CATEGORY_NAME_"):
        cat_rows.append({"name_key": t[i], "desc_key": t[i + 1], "asset": t[i + 2]})
        i += 3
    else:
        i += 1
print(f"AlbumCategoryTable: {len(cat_rows)} categories: "
      f"{Counter(c['name_key'].split('_')[-1] for c in cat_rows)}")

# ---------------- AlbumInfoTable ----------------
info_rows, i = [], 0
t = toks("AlbumInfoTable.mpk")
while i + 2 < len(t):
    if t[i].startswith("Locale_") and t[i + 1].startswith("Locale_") and t[i + 2].startswith("img_album"):
        info_rows.append({"locale_table": t[i], "title_key": t[i + 1], "image": t[i + 2]})
        i += 3
    else:
        i += 1
print(f"AlbumInfoTable: {len(info_rows)} info entries "
      f"(chapters {sum(1 for r in info_rows if 'chapter' in r['image'])}, "
      f"structures {sum(1 for r in info_rows if 'structure' in r['image'])})")

# ---------------- AlbumResourceTable ----------------
t = toks("AlbumResourceTable.mpk")
res_rows, i = [], 0
while i + 2 < len(t):
    if t[i].startswith("Locale_") and t[i + 1].startswith("Locale_") and not t[i + 2].startswith("Locale_"):
        res_rows.append({"desc_key_1": t[i], "desc_key_2": t[i + 1], "group": t[i + 2]})
        i += 3
    else:
        i += 1
pref = Counter()
for r in res_rows:
    g = r["group"]
    if g.startswith("d_main"):
        pref["d_main*"] += 1
    elif g.startswith("d_nikke"):
        pref["d_nikke*"] += 1
    elif g.startswith("d_contents"):
        pref["d_contents*"] += 1
    elif g.startswith("event_"):
        pref["event_*"] += 1
    elif re.match(r"^s\d{3}_", g):
        pref["sidestory sNNN_*"] += 1
    else:
        pref[g.split("_")[0]] += 1
print(f"AlbumResourceTable: {len(res_rows)} rows; group prefixes: {pref.most_common()}")

# how many archive groups exist in dialog Group.csv lists?
dialog_groups = set()
for base in ["ScenarioDialog", "EventScenarioDialog", "AttractiveScenarioDialog",
             "SideStoryScenarioDialog", "SideStorySpotDialog", "AttractiveCounselDialog"]:
    p = STATIC / f"{base}.Group.csv"
    if p.exists():
        rows = [l.strip() for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        if rows and rows[0] in ("group_id", "event_id"):
            rows = rows[1:]
        dialog_groups.update(rows)
in_csv = sum(1 for r in res_rows
             if (r["group"] in dialog_groups
                 or unpadded(r["group"]) in dialog_groups
                 or r["group"][:-1] in dialog_groups
                 or unpadded(r["group"][:-1]) in dialog_groups))
unmatched = sorted({r["group"] for r in res_rows
                    if not (r["group"] in dialog_groups
                            or unpadded(r["group"]) in dialog_groups
                            or r["group"][:-1] in dialog_groups
                            or unpadded(r["group"][:-1]) in dialog_groups)})
print(f"archive groups found in dialog Group.csv lists (glue-char tolerated): "
      f"{in_csv}/{len(res_rows)}; unmatched {len(unmatched)}: {unmatched[:8]} ...")

# ---------------- LiveWallpaperTable ----------------
t = toks("LiveWallpaperTable.mpk")
wp, cur = [], None
for s in t:
    m = re.match(r"^Locale_LiveWallpaper:live_wallpaper_name_(\d+)$", s)
    if m:
        if cur:
            wp.append(cur)
        cur = {"id": int(m.group(1)), "name_key": s, "desc_key": "", "path": "",
               "cg": "", "variants": [], "bgm": ""}
        continue
    if cur is None:
        continue
    if s.startswith("Locale_LiveWallpaper:live_wallpaper_description_"):
        cur["desc_key"] = s
    elif "EventScene_" in s:
        if s.startswith("livewallpaper/"):
            cur["path"] = s
            cur["cg"] = s.split("/")[-1]
        else:
            cur["variants"].append(s)
    elif s.startswith("bgm_"):
        cur["bgm"] = s
if cur:
    wp.append(cur)
no_path = [r for r in wp if not r["path"]]
stems = sorted({r["cg"] for r in wp if r["cg"]})
print(f"LiveWallpaperTable: {len(wp)} records, {len(stems)} distinct CG stems, "
      f"{len(no_path)} without path")
for r in no_path[:5]:
    print("   no-path record:", r)

# wallpaper stems vs dialog-referenced CG names
refs = json.loads((OUT / "story_refs.json").read_text(encoding="utf-8"))
nd = json.loads((OUT / "non_dialog_refs.json").read_text(encoding="utf-8"))
referenced = {c for r in refs for c in r["cg"]} | {r["cg"] for r in nd}
wp_in_refs = sum(1 for s in stems if s in referenced)
print(f"gallery CG stems also referenced in story/config tables: {wp_in_refs}/{len(stems)}")

# ---------------- outputs ----------------
album_list = {
    "album_category_table": {
        "file": "AlbumCategoryTable.mpk",
        "record_shape": "[Locale_System:ALBUM_CATEGORY_NAME_x, Locale_System:ALBUM_CATEGORY_DESC_x, 资源名]",
        "categories": cat_rows,
    },
    "album_info_table": {
        "file": "AlbumInfoTable.mpk",
        "record_shape": "[Locale表名, 标题key, img_album_*]",
        "entries": info_rows,
    },
    "album_resource_table": {
        "file": "AlbumResourceTable.mpk",
        "record_shape": "[Locale key 1, Locale key 2, 对话组ID]",
        "row_count": len(res_rows),
        "group_prefixes": dict(pref),
        "groups_in_dialog_group_csv": in_csv,
        "note": "组ID尾部常粘连1个杂字符（与mpk同源的字节粘连现象）；比对时已容忍",
        "unmatched_groups_sample": unmatched[:30],
        "groups": [r["group"] for r in res_rows],
    },
    "live_wallpaper_table": {
        "file": "LiveWallpaperTable.mpk",
        "record_shape": "[name_N, description_N, livewallpaper/<CG>, <CG>_mi, <CG>_si, bgm_*]",
        "record_count": len(wp),
        "distinct_cg_stems": len(stems),
        "records_without_path": len(no_path),
        "gallery_cg": stems,
        "records": wp,
    },
}
(OUT / "album_list.json").write_text(json.dumps(album_list, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
print("written album_list.json")
