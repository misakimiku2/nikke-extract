"""Probe: token context around EventScene hits in non-dialog families."""
import json
import re
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
AUD = Path("E:/test/nikke_extract/_cg_audit")
TOKEN = re.compile(rb"[ -~]{4,}")

hits = json.loads((AUD / "_cache_cg_hits.json").read_text(encoding="utf-8"))

targets = ["LiveWallpaperTable.mpk", "ScenarioCharacterSettingTable.mpk",
           "ScenarioChoiceAlbumTable.mpk", "ScenarioCameraSettingTable.mpk",
           "ScenarioPositionSettingTable.mpk", "EventDiceResourceTable.mpk",
           "SideStoryRecommendationTable.mpk", "TrailMarkerEventTable.mpk",
           "EventTextAdventureEventPageTable.mpk", "EventTextAdvPlusEventPageTable.mpk",
           "EventTextAdventureFirstSelectTable.mpk", "EventBBQTycoonCartoonCutSceneTable.mpk",
           "EventDatingSimPhotoAlbumTable.mpk", "EventDatingSimDialogEventTable.mpk"]

for t in targets:
    p = STATIC / t
    if not p.exists():
        print(f"!! missing {t}")
        continue
    raw = p.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    ms = hits.get(t, [])
    print(f"\n===== {t}  size={len(raw)} tokens={len(toks)} cg_hits={len(ms)}")
    # show token windows around first 3 CG hits
    shown = 0
    for off, cg in ms:
        win = [s for o, s in toks if off - 260 <= o <= off + 260]
        print(f"  -- around {cg}:")
        print("     " + " | ".join(win))
        shown += 1
        if shown >= 3:
            break
