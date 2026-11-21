"""Task 4 probe 2: parse AlbumResourceTable rows + LiveWallpaperTable records."""
import re
from collections import Counter
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
TOKEN = re.compile(rb"[ -~]{4,}")

def toks(path):
    return [m.group().decode("ascii", "replace") for m in TOKEN.finditer(path.read_bytes())]

# ---- AlbumResourceTable: what group prefixes, and how many rows?
t = toks(STATIC / "AlbumResourceTable.mpk")
groups = [s for s in t if not s.startswith("Locale_")]
pref = Counter()
for g in groups:
    if g.startswith("d_main"):
        pref["d_main"] += 1
    elif g.startswith("d_nikke"):
        pref["d_nikke"] += 1
    elif g.startswith("event_"):
        pref["event_"] += 1
    elif g.startswith("s") and g[1:4].isdigit():
        pref["sidestory_sNNN"] += 1
    elif g.startswith("d_contents"):
        pref["d_contents"] += 1
    else:
        pref[g.split("_")[0] if "_" in g else g[:20]] += 1
print(f"AlbumResourceTable: tokens={len(t)}, non-locale tokens={len(groups)} (rows?), prefix dist:")
for k, v in pref.most_common():
    print(f"   {k:<24} {v}")
print("sample non-locale tokens:", groups[:5], "...", groups[-8:])

# rows = triples [Locale_XXX:key, Locale_XXX:key, group]? verify pattern
n = 0
i = 0
bad = 0
while i < len(t):
    if i + 2 < len(t) and t[i].startswith("Locale_") and t[i+1].startswith("Locale_") and not t[i+2].startswith("Locale_"):
        n += 1
        i += 3
    else:
        bad += 1
        i += 1
print(f"triple-pattern rows={n}, other tokens={bad}")

# ---- LiveWallpaperTable: parse records
t2 = toks(STATIC / "LiveWallpaperTable.mpk")
recs = []
cur = None
for s in t2:
    m = re.match(r"^Locale_LiveWallpaper:live_wallpaper_name_(\d+)$", s)
    if m:
        if cur:
            recs.append(cur)
        cur = {"id": int(m.group(1)), "name_key": s, "path": None, "variants": [], "bgm": None}
        continue
    if cur is None:
        continue
    if s.startswith("Locale_LiveWallpaper:live_wallpaper_description_"):
        cur["desc_key"] = s
    elif "EventScene_" in s:
        if s.startswith("livewallpaper/"):
            cur["path"] = s
        else:
            cur["variants"].append(s)
    elif s.startswith("bgm_"):
        cur["bgm"] = s
if cur:
    recs.append(cur)
print(f"\nLiveWallpaperTable: {len(recs)} records")
for r in recs[:5]:
    print("  ", r)
missing_path = [r for r in recs if not r["path"]]
print(f"records without livewallpaper path: {len(missing_path)}")
varcount = Counter(len(r["variants"]) for r in recs)
print("variants-per-record dist:", dict(varcount))
# distinct CG stems
stems = set()
for r in recs:
    if r["path"]:
        stems.add(r["path"].split("/")[-1])
    for v in r["variants"]:
        stems.add(re.sub(r"_(mi|si)$", "", v))
print(f"distinct CG stems from wallpaper gallery: {len(stems)}")
pref2 = Counter()
for s in stems:
    p = "_".join(s.split("_")[:2])
    pref2[p] += 1
print("stem prefix dist (top 30):", pref2.most_common(30))
