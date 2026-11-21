"""Probe: naming of per-group mpk for each Group.csv family + sample token streams."""
import re
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
TOKEN = re.compile(rb"[ -~]{4,}")

families = ["ScenarioDialog", "EventScenarioDialog", "AttractiveScenarioDialog",
            "SideStoryScenarioDialog", "SideStorySpotDialog", "AttractiveCounselDialog",
            "ArchiveProgressEvent", "ProgressEvent", "WaveData"]

for fam in families:
    csv_path = STATIC / f"{fam}.Group.csv"
    if not csv_path.exists():
        print(f"== {fam}: NO Group.csv")
        continue
    groups = [l.strip() for l in csv_path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    if groups and groups[0] in ("group_id", "event_id"):
        groups = groups[1:]
    # how are per-group mpk named? try <fam>Table.<g>.mpk and <fam>.<g>.mpk
    hits_a = sum((STATIC / f"{fam}Table.{g}.mpk").exists() for g in groups)
    hits_b = sum((STATIC / f"{fam}.{g}.mpk").exists() for g in groups)
    print(f"== {fam}: {len(groups)} groups; {fam}Table.<g>.mpk -> {hits_a}; {fam}.<g>.mpk -> {hits_b}")

print()
# sample token streams
for rel in ["ScenarioDialogTable.d_main_01_01_s.mpk",
            "SideStoryScenarioDialogTable.s001_01.mpk",
            "SideStorySpotDialogTable.s001_09_b1.mpk",
            "AttractiveCounselDialogTable.d_counseling_admi_01.mpk"]:
    p = STATIC / rel
    if not p.exists():
        # find any file starting with family
        fam = rel.split(".")[0]
        cands = sorted(STATIC.glob(fam + ".*.mpk"))
        print(f"!! {rel} missing; candidates: {[c.name for c in cands[:3]]}")
        p = cands[0] if cands else None
        if p is None:
            continue
    raw = p.read_bytes()
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]
    print(f"\n### {p.name}  size={len(raw)} tokens={len(toks)}")
    print(" | ".join(toks[:80]))
