"""Tasks 2+3: Dialog-family group census + per-line CG mapping.

Outputs:
  _cg_audit/dialog_families.csv   (族名, Group.csv, 组数, 含CG组数, CG引用数, 是否被现有索引覆盖, mpk文件数, Group.csv外mpk数, 备注)
  _cg_audit/story_refs.json       per-line records for the 6 Dialog families (CG-bearing lines)
  _cg_audit/_cache_dialog_stats.json  per-family per-group hit counts (for dialog_families.csv)

Token model (verified on samples):
  record anchored by token == f"{group}_{n}" (fullmatch), fields are plain ASCII tokens;
  trailing "next line id" pointers create phantom anchors whose segments carry no CG and
  are skipped naturally.
"""
import csv
import json
import re
from pathlib import Path

STATIC = Path("E:/test/nikke_extract/staticdata")
OUT = Path("E:/test/nikke_extract/_cg_audit")

TOKEN = re.compile(rb"[ -~]{4,}")
CG_FULL = re.compile(r"^EventScene_[A-Za-z0-9_]+$")

# family, Group.csv base, covered by existing build_cg_index GROUP_SETS
DIALOG_FAMILIES = [
    ("ScenarioDialogTable", "ScenarioDialog", True),
    ("EventScenarioDialogTable", "EventScenarioDialog", True),
    ("AttractiveScenarioDialogTable", "AttractiveScenarioDialog", True),
    ("SideStoryScenarioDialogTable", "SideStoryScenarioDialog", False),
    ("SideStorySpotDialogTable", "SideStorySpotDialog", False),
    ("AttractiveCounselDialogTable", "AttractiveCounselDialog", False),
]

NON_DIALOG_GROUP_FAMILIES = [
    ("ArchiveProgressEventTable", "ArchiveProgressEvent",
     "非Dialog：活动进度表；GroupDict.csv=id→event_id 映射(4455行)"),
    ("ProgressEventTable", "ProgressEvent",
     "非Dialog：当前活动进度表；GroupDict.csv=id→event_id 映射(7745行)"),
    ("WaveDataTable", "WaveData",
     "非Dialog：波次数据；GroupDict.csv=stage_id→group_id 映射(17801行)"),
]


def read_groups(base: str) -> list[str]:
    p = STATIC / f"{base}.Group.csv"
    if not p.exists():
        return []
    rows = [l.strip() for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    if rows and rows[0] in ("group_id", "event_id"):
        rows = rows[1:]
    return rows


def _unpad(group: str) -> str:
    """d_main_26_04 -> d_main_26_4 (some tables anchor lines without zero padding)."""
    return re.sub(r"_0*(\d+)", lambda m: "_" + str(int(m.group(1))), group)


def parse_group(group: str, path: Path) -> tuple[list[dict], int]:
    """CG-bearing lines of one dialog mpk, plus count of CG occurrences
    that fell outside any record segment (pre-first-anchor region).

    Anchor tokens: f"{prefix}_{n}" optionally followed by ONE glued printable char
    (mpk glues a stray byte to the ASCII run; verified: 840 EventScenarioDialogTable
    files use anchors like `event_xxx_1T`).  Prefix is the group name as-is, or the
    zero-padding-stripped form (ScenarioDialogTable chapter-26 files anchor
    `d_main_26_4_1` for group `d_main_26_04`).  Strict `_{n}$` would miss those files.
    """
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    prefixes = [group]
    unp = _unpad(group)
    if unp != group:
        prefixes.append(unp)
    anchors = []
    used_prefix = None
    for pref in prefixes:
        id_re = re.compile(re.escape(pref) + r"_(\d+).?")
        cand = [(o, int(id_re.fullmatch(s).group(1))) for o, s in toks if id_re.fullmatch(s)]
        if cand:
            anchors = cand
            used_prefix = pref
            break
    out = []
    for k, (start, n) in enumerate(anchors):
        end = anchors[k + 1][0] if k + 1 < len(anchors) else len(raw)
        seg = [s for o, s in toks if start <= o < end]
        if not seg:
            continue
        cgs = [s for s in seg if CG_FULL.match(s)]
        if not cgs:
            continue
        locale_toks = [s for s in seg if s.startswith("Locale_")]
        # text key = Locale_XXX:<group>_<digits> preferred, else last Locale token
        text_key = None
        for pref in prefixes:
            pat = re.compile(r"^Locale_[A-Za-z]+:" + re.escape(pref) + r"_(\d+)$")
            text_key = next((s for s in locale_toks if pat.match(s)), None)
            if text_key:
                break
        if text_key is None and locale_toks:
            text_key = locale_toks[-1]
        # speaker: first token between anchor and text key that is not the group name
        speaker = ""
        if text_key is not None:
            ki = seg.index(text_key)
            pre = [s for s in seg[1:ki] if s != group]
            speaker = pre[0] if pre else ""
        other = [s for s in seg if not CG_FULL.match(s) and not s.startswith("Locale_")][1:]
        # first element of `other` is the anchor itself; drop it
        raw_only = [s for s in re.findall(r"EventScene_[A-Za-z0-9_]+", " ".join(seg))
                    if not CG_FULL.match(s)]
        out.append({
            "family": path.name.split(".")[0],
            "group": group,
            "file": path.name,
            "line_no": n,
            "locale_key": text_key or "",
            "speaker_token": speaker,
            "cg": list(dict.fromkeys(cgs)),
            "cg_raw_count": len(cgs),
            "cg_in_compound_tokens": raw_only,
            "other_tokens": other,
            "anchor_prefix": used_prefix or "",
        })
    # coverage check: CG occurrences before the first anchor are outside all segments
    first_anchor_off = anchors[0][0] if anchors else None
    orphan = sum(1 for o, s in toks
                 if CG_FULL.match(s)
                 and (first_anchor_off is None or o < first_anchor_off))
    return out, orphan


def main() -> None:
    stats = {}   # family -> {groups_in_csv, mpk_files, groups_with_cg, refs, orphan_files}
    all_refs = []

    for fam, base, covered in DIALOG_FAMILIES:
        groups = read_groups(base)
        gset = set(groups)
        mpks = sorted(STATIC.glob(f"{fam}.*.mpk"))
        fam_stats = {"groups_in_csv": len(groups), "mpk_files": len(mpks),
                     "groups_with_cg": 0, "refs": 0, "orphan_mpks": 0,
                     "orphan_with_cg": 0, "cg_outside_segments": 0,
                     "files_with_orphan_cg": 0}
        for p in mpks:
            g = p.name[len(fam) + 1:-len(".mpk")]
            if not g:
                continue  # family base table
            if g not in gset:
                fam_stats["orphan_mpks"] += 1
            recs, orphan_cg = parse_group(g, p)
            if orphan_cg:
                fam_stats["cg_outside_segments"] += orphan_cg
                fam_stats["files_with_orphan_cg"] += 1
                print(f"  !! {p.name}: {orphan_cg} CG occurrences before first anchor")
            if recs:
                fam_stats["groups_with_cg"] += 1
                if g not in gset:
                    fam_stats["orphan_with_cg"] += 1
                fam_stats["refs"] += sum(len(r["cg"]) for r in recs)
                for r in recs:
                    r["group_in_group_csv"] = g in gset
                all_refs.extend(recs)
        stats[fam] = fam_stats
        print(f"{fam}: groups {fam_stats['groups_in_csv']}, mpk {fam_stats['mpk_files']} "
              f"(orphans {fam_stats['orphan_mpks']}), withCG {fam_stats['groups_with_cg']}, "
              f"refs {fam_stats['refs']}")

    (OUT / "story_refs.json").write_text(
        json.dumps(all_refs, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "_cache_dialog_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"story_refs.json: {len(all_refs)} CG-bearing lines")

    # ---------------- dialog_families.csv ----------------
    # other dialog-ish single-table families (no Group.csv)
    other_dialog_fams = ["BalloonDialogTable", "DialogThemeTable", "EchoDialogTable",
                         "EchoDialogNPCTable", "EchoDialogFieldTriggerTable",
                         "FieldTalkDialogTable", "MessengerDialogTable",
                         "EventNKSDialogTable", "EventPirateCafeDialogTable",
                         "EventPirateCafeDialogGroupTable",
                         "EventRebuildEdenDialogTable", "EventTowerDefenseBurstDialogTable",
                         "EventDatingSimDialogConditionTable",
                         "EventDatingSimDialogEventTable",
                         "EventDatingSimDialogScheduleTable",
                         "SimulationRoomDialogueBattleTable",
                         "SimulationRoomDialogueLocationTable"]
    hits = json.loads((OUT / "_cache_cg_hits.json").read_text(encoding="utf-8"))

    def fam_cg_stats(fam: str) -> tuple[int, int]:
        n_files, n_refs = 0, 0
        for fname, ms in hits.items():
            if fname.split(".")[0] == fam:
                n_files += 1
                n_refs += len(ms)
        return n_files, n_refs

    covered_set = {"ScenarioDialogTable", "EventScenarioDialogTable",
                   "AttractiveScenarioDialogTable"}
    rows = []
    for fam, base, covered in DIALOG_FAMILIES:
        st = stats[fam]
        note = ""
        if st["orphan_mpks"]:
            note = (f"有 {st['orphan_mpks']} 个 mpk 不在 Group.csv 中"
                    f"（其中 {st['orphan_with_cg']} 个含 CG 引用）")
        if st["cg_outside_segments"]:
            note += f"；{st['files_with_orphan_cg']} 个文件有首锚点前 CG token"
        rows.append({
            "族名": fam,
            "Group.csv": f"{base}.Group.csv",
            "组数": st["groups_in_csv"],
            "含CG组数": st["groups_with_cg"],
            "CG引用数": st["refs"],
            "是否被现有索引覆盖": "是" if covered else "否",
            "mpk文件数": st["mpk_files"],
            "Group.csv外mpk数": st["orphan_mpks"],
            "备注": note,
        })
    for fam, base, note in NON_DIALOG_GROUP_FAMILIES:
        groups = read_groups(base)
        mpks = len(list(STATIC.glob(f"{fam}.*.mpk")))
        n_files, n_refs = fam_cg_stats(fam)
        rows.append({
            "族名": fam, "Group.csv": f"{base}.Group.csv", "组数": len(groups),
            "含CG组数": n_files, "CG引用数": n_refs, "是否被现有索引覆盖": "否（非Dialog族）",
            "mpk文件数": mpks, "Group.csv外mpk数": max(0, mpks - len(groups)),
            "备注": note,
        })
    for fam in other_dialog_fams:
        n_files, n_refs = fam_cg_stats(fam)
        rows.append({
            "族名": fam, "Group.csv": "（无）", "组数": 0,
            "含CG组数": n_files, "CG引用数": n_refs,
            "是否被现有索引覆盖": "否", "mpk文件数": len(list(STATIC.glob(f"{fam}*.mpk"))),
            "Group.csv外mpk数": "", "备注": "单表族，无 Group.csv",
        })
    with (OUT / "dialog_families.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["族名", "Group.csv", "组数", "含CG组数",
                                           "CG引用数", "是否被现有索引覆盖",
                                           "mpk文件数", "Group.csv外mpk数", "备注"])
        w.writeheader()
        w.writerows(rows)
    print("written dialog_families.csv")


if __name__ == "__main__":
    main()
