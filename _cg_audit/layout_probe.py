"""Task 6: probe layout stability of CG tokens vs line anchors & locale keys.

Dumps full token streams of representative groups and computes global position
statistics over all CG-bearing lines; also aggregates bgm_/sfx_/fx_/movie tokens.

Outputs: _cg_audit/_cache_layout_probe.json (stats for layout_notes.md)
"""
import json
import re
from collections import Counter
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
OUT = Path("E:/test/nikke_extract/_cg_audit")
TOKEN = re.compile(rb"[ -~]{4,}")
CG_FULL = re.compile(r"^EventScene_[A-Za-z0-9_]+$")


def _unpad(g: str) -> str:
    return re.sub(r"_0*(\d+)", lambda m: "_" + str(int(m.group(1))), g)


def segments(group: str, path: Path):
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    prefixes = [group] + ([_unpad(group)] if _unpad(group) != group else [])
    for pref in prefixes:
        id_re = re.compile(re.escape(pref) + r"_(\d+).?")
        anchors = [(o, int(id_re.fullmatch(s).group(1))) for o, s in toks if id_re.fullmatch(s)]
        if anchors:
            break
    segs = []
    for k, (start, n) in enumerate(anchors):
        end = anchors[k + 1][0] if k + 1 < len(anchors) else len(raw)
        segs.append((n, [s for o, s in toks if start <= o < end]))
    return segs


# ---- representative groups ----
samples = [
    ("主线", "ScenarioDialogTable.d_main_01_01_s.mpk"),
    ("主线(无填充锚点)", "ScenarioDialogTable.d_main_26_04.mpk"),
    ("活动(粘连锚点)", "EventScenarioDialogTable.event_bluewaterisland1_04_e.mpk"),
    ("活动(CG在第1行)", "EventScenarioDialogTable.event_seayouagain2_05_s.mpk"),
    ("支线", "SideStoryScenarioDialogTable.s001_01.mpk"),
    ("咨询(无CG)", "AttractiveCounselDialogTable.d_counseling_admi_01.mpk"),
    ("个人(spine事件)", "AttractiveScenarioDialogTable.d_nikke_Mary_BayGoddess_01.mpk"),
]
dump = {}
for label, fname in samples:
    p = STATIC / fname
    if not p.exists():
        print("missing sample", fname)
        continue
    group = fname.split(".")[1]
    segs = segments(group, p)
    dump[label] = {"file": fname, "segments": segs}
    print(f"## {label} {fname}: {len(segs)} segments")
    for n, seg in segs[:14]:
        print(f"  L{n}: " + " | ".join(seg))

# ---- global position stats over all CG lines ----
refs = json.loads((OUT / "story_refs.json").read_text(encoding="utf-8"))
pos = Counter()          # cg_index - locale_index sign
cg_at_end = Counter()
line_no_monotonic = Counter()  # per-group CG line numbers increasing?
per_group_last = {}
locale_prefix = Counter()
for r in refs:
    # rebuild positions cheaply from stored fields is not possible; re-parse a subset:
    pass

# precise position stats need segments; reparse only CG-bearing files (406 files)
cg_files = sorted({r["file"] for r in refs})
after_locale = before_locale = both = 0
persist = 0
for fname in cg_files:
    fam = fname.split(".")[0]
    group = fname[len(fam) + 1:-4]
    segs = segments(group, STATIC / fname)
    seen_cg = False
    prev = None
    last_n = -1
    mono = True
    for n, seg in segs:
        idx_cg = [i for i, s in enumerate(seg) if CG_FULL.match(s)]
        idx_lk = [i for i, s in enumerate(seg) if s.startswith("Locale_")]
        if idx_cg:
            if idx_lk:
                a, b = idx_cg[0], idx_lk[0]
                if a > b:
                    after_locale += 1
                elif a < b:
                    before_locale += 1
                else:
                    both += 1
            if prev is not None and tuple(idx_cg) == prev:
                persist += 1
            prev = tuple(idx_cg)
            if n < last_n:
                mono = False
            last_n = n
    line_no_monotonic[mono] += 1

print("\nCG position vs locale key: after", after_locale, "before", before_locale,
      "same-index", both)
print("CG line numbers monotonic per group:", dict(line_no_monotonic))

# ---- bgm / sfx / fx / background vocab over the 6 dialog families ----
bgm = Counter()
sfx = Counter()
fx = Counter()
bg_candidates = Counter()
MOVIE = re.compile(r"movie|mp4|webm|Video", re.I)
movie_toks = Counter()
movie_files = Counter()
for fam in ["ScenarioDialogTable", "EventScenarioDialogTable", "AttractiveScenarioDialogTable",
            "SideStoryScenarioDialogTable", "SideStorySpotDialogTable",
            "AttractiveCounselDialogTable"]:
    for p in STATIC.glob(fam + ".*.mpk"):
        g = p.name[len(fam) + 1:-4]
        if not g:
            continue
        for n, seg in segments(g, p):
            for i, s in enumerate(seg):
                ls = s.lower()
                if ls.startswith("bgm_"):
                    bgm[s] += 1
                elif ls.startswith("sfx_"):
                    sfx[s] += 1
                elif ls.startswith("fx_") and not ls.startswith("fx_vn"):
                    pass
                if MOVIE.search(s):
                    movie_toks[s] += 1
                    movie_files[p.name] += 1
            # background candidates: standalone Capitalized tokens in 2nd half of segment
            # (after locale key), not CG/fx/bgm/sfx/speaker(lowercase)
            for i, s in enumerate(seg):
                if (re.match(r"^[A-Z][A-Za-z0-9_]*(_\d+)?$", s)
                        and not s.startswith(("EventScene", "Locale_", "Fx", "FX"))
                        and "_" not in s[:1]):
                    bg_candidates[s] += 1

print("\ntop bgm tokens:", bgm.most_common(8))
print("distinct bgm:", len(bgm), "distinct sfx:", len(sfx))
print("movie-ish tokens in dialog families:", movie_toks.most_common(12))
print("movie files:", len(movie_files), movie_files.most_common(6))
top_bg = [s for s, c in bg_candidates.most_common(40)]
print("bg candidates top40:", top_bg)

json.dump({"cg_pos_after_locale": after_locale, "cg_pos_before_locale": before_locale,
           "cg_pos_same": both, "monotonic_groups": dict(line_no_monotonic),
           "distinct_bgm": len(bgm), "distinct_sfx": len(sfx),
           "movie_tokens": dict(movie_toks), "movie_files": dict(movie_files)},
          (OUT / "_cache_layout_probe.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written _cache_layout_probe.json")
