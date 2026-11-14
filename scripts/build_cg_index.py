"""Build a story-text <-> CG cross-reference index for NIKKE.

Source of truth (all local):
  * ScenarioDialog.Group.csv / EventScenarioDialog.Group.csv /
    AttractiveScenarioDialog.Group.csv      -> ordered scenario groups
  * <Prefix>Table.<group>.mpk              -> per-line records; a record may carry
                                              `EventScene_*` tokens = the illustration
                                              shown on that line
  * Locale_MainScenario (zh-CN)            -> dialogue text + per-group title
  * CG/全量分类/**/*.png                   -> exported static CG files
  * 动态CG/模型/*                          -> exported Spine dynamic CG models

Outputs (CG索引/):
  * 剧情CG对照索引.csv
  * 剧情CG对照索引.json
  * 统计.txt
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
OUT = BASE / "CG索引"
LOCALE_MAIN = BASE / "decrypted" / "4f4bdc30e957b0f8157a2ec7b399f545.dec"
LOCALE_CHAR = BASE / "decrypted" / "e6059faf00471aa305c16cabe88871bb.dec"
LOCALE_STAGE = BASE / "decrypted" / "2f3134ea528251fb735273e764276059.dec"

TOKEN = re.compile(rb"[ -~]{4,}")
CG_TOKEN = re.compile(r"^EventScene_[A-Za-z0-9_]+$")
VALID_CG = re.compile(r"^EventScene_[A-Za-z0-9_]+$")

GROUP_SETS = [
    ("主线", "ScenarioDialog.Group.csv", "ScenarioDialogTable.{}.mpk"),
    ("活动", "EventScenarioDialog.Group.csv", "EventScenarioDialogTable.{}.mpk"),
    ("妮姬个人", "AttractiveScenarioDialog.Group.csv", "AttractiveScenarioDialogTable.{}.mpk"),
]


# --------------------------------------------------------------------------- #
# reference data
# --------------------------------------------------------------------------- #
def load_names() -> dict[str, str]:
    toks = [m.group().decode("ascii", "replace")
            for m in TOKEN.finditer((STATIC / "ScenarioCharacterSettingTable.mpk").read_bytes())]
    pairs = {}
    for i, s in enumerate(toks):
        m = re.match(r"^Locale_Character:([A-Za-z0-9_]+)_name", s)
        if m and i > 0:
            pairs[toks[i - 1]] = m.group(1)
    conn = sqlite3.connect(LOCALE_CHAR)
    names = {}
    for rid, key in pairs.items():
        row = conn.execute('SELECT "zh-CN" FROM "Locale_Character" WHERE "Key"=?',
                           (key + "_name",)).fetchone()
        names[rid] = row[0] if row and row[0] else rid
    conn.close()
    return names


def load_locale() -> dict[str, str]:
    conn = sqlite3.connect(f"file:{LOCALE_MAIN}?mode=ro", uri=True)
    d = {k: v for k, v in conn.execute('SELECT "Key","zh-CN" FROM Locale_MainScenario')}
    conn.close()
    return d


def load_cg_files() -> tuple[dict[str, Path], dict[str, Path]]:
    """name(lower) -> png path, name(lower) -> spine model dir"""
    static = {}
    for f in (BASE / "CG").rglob("*.png"):
        if f.name.endswith(".spine.png"):
            continue
        static.setdefault(f.stem.lower(), f)
    dynamic = {}
    for a in (BASE / "CG").rglob("*.atlas"):
        dynamic[a.stem.lower()] = a.parent
    return static, dynamic


def speaker_name(pre: list[str], names: dict[str, str]) -> str | None:
    chars = [s for s in pre if s in names]
    last = pre[-1] if pre else None
    if last in ("Self", "Choice"):
        return "指挥官"
    if len(chars) >= 2:
        return names.get(chars[-1])
    return None


# --------------------------------------------------------------------------- #
# grouping helpers
# --------------------------------------------------------------------------- #
def activity_of(group: str) -> tuple[str, str]:
    """(activity key, display name stem)"""
    if group.startswith("d_main_"):
        m = re.match(r"d_main_(\d+)", group)
        return f"d_main_{m.group(1)}", f"第{int(m.group(1)):02d}章"
    if group.startswith("event_"):
        m = re.match(r"(event_[a-z0-9]+?)(?:_|$)", group)
        return (m.group(1) if m else group), (m.group(1) if m else group)
    if group.startswith("d_nikke_"):
        m = re.match(r"(d_nikke_[a-z0-9_]+?)_\d+$", group)
        return (m.group(1) if m else group), (m.group(1) if m else group)
    if group.startswith("d_contents_"):
        m = re.match(r"(d_contents_[a-z0-9_]+?)(?:_\d+|_prologue|_mini.*)?$", group)
        return (m.group(1) if m else group), (m.group(1) if m else group)
    if group.startswith("d_side"):
        return "d_side", "支线"
    return group, group


def section_title(group: str, locale: dict[str, str]) -> str:
    return (locale.get(f"{group}_title") or "").strip()


def activity_title(key: str, locale: dict[str, str], chapter_titles: dict[int, str]) -> str:
    if key.startswith("d_main_"):
        n = int(key.split("_")[2])
        t = chapter_titles.get(n) or ""
        return f"第{n:02d}章" + (f" · {t}" if t else "")
    for suffix in ("_prologue_title", "_title"):
        v = locale.get(key + suffix)
        if v:
            return v.strip()
    # no official umbrella title -> use the internal code, prettified
    code = key[len("event_"):] if key.startswith("event_") else key
    code = re.sub(r"(\d+)$", r" \1", code).replace("_", " ").strip()
    return code.upper()


def chapter_titles() -> dict[int, str]:
    conn = sqlite3.connect(f"file:{LOCALE_STAGE}?mode=ro", uri=True)
    d = dict(conn.execute('SELECT "Key","zh-CN" FROM Locale_Stage'))
    conn.close()
    return {n: (d.get(f"chapter_name_{n-1:02d}") or "") for n in range(1, 51)}


def resolve_cg(name: str, static: dict[str, Path], dynamic: dict[str, Path]):
    """Exact match, else trim trailing _N segments (differential variants)."""
    low = name.lower()
    if low in static or low in dynamic:
        return static.get(low), dynamic.get(low), "精确"
    cand, cur = [low], low
    while True:
        m = re.match(r"^(.*)_\d+$", cur)
        if not m:
            break
        cur = m.group(1)
        cand.append(cur)
    for c in cand[1:]:
        if c in static or c in dynamic:
            return static.get(c), dynamic.get(c), "近似"
    return None, None, "缺失"


# --------------------------------------------------------------------------- #
def parse_group(group: str, path: Path, names, locale):
    """Return list of (line_no, key, speaker, cg_names) for lines that carry a CG."""
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    id_re = re.compile(re.escape(group) + r"_(\d+)$")
    anchors = [(o, int(id_re.match(s).group(1))) for o, s in toks if id_re.fullmatch(s)]
    out = []
    prev: tuple[str, ...] | None = None
    for k, (start, n) in enumerate(anchors):
        end = anchors[k + 1][0] if k + 1 < len(anchors) else len(raw)
        seg = [s for o, s in toks if start <= o < end]
        cgs = tuple(dict.fromkeys(s for s in seg if VALID_CG.match(s)))
        if not cgs:
            # no CG field on this line: the previous CG is still on screen
            continue
        if cgs == prev:
            continue
        prev = cgs
        lk = next((i for i, s in enumerate(seg) if s.startswith("Locale_MainScenario:")), None)
        if lk is None:
            continue
        key = seg[lk][len("Locale_MainScenario:"):]
        out.append((n, key, speaker_name(seg[2:lk], names), cgs))
    return out


def main() -> None:
    stats_only = "--stats" in sys.argv

    names = load_names()
    locale = load_locale()
    chapter_names = chapter_titles()
    static_cg, dynamic_cg = load_cg_files()

    rows = []
    missing_files = Counter()
    cg_seen = Counter()
    per_category = Counter()
    match_kind = Counter()
    groups_scanned = 0
    groups_with_cg = 0

    for category, csv_name, table_tpl in GROUP_SETS:
        csv_path = STATIC / csv_name
        groups = [l.strip() for l in csv_path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        if groups and groups[0] == "group_id":
            groups = groups[1:]
        for g in groups:
            table = STATIC / table_tpl.format(g)
            if not table.exists():
                continue
            groups_scanned += 1
            hits = parse_group(g, table, names, locale)
            if hits:
                groups_with_cg += 1
            act_key, _ = activity_of(g)
            act_name = activity_title(act_key, locale, chapter_names)
            for n, key, speaker, cgs in hits:
                text = (locale.get(key) or "").replace("{AccountData.NickName}", "指挥官")
                text = re.sub(r"\s+", " ", text).strip()
                for cg in cgs:
                    cg_seen[cg] += 1
                    sfile, dmodel, match = resolve_cg(cg, static_cg, dynamic_cg)
                    if sfile is None and dmodel is None:
                        missing_files[cg] += 1
                    match_kind[match] += 1
                    rows.append({
                        "分类": category,
                        "活动/章节": act_name or act_key,
                        "活动键": act_key,
                        "小节": g,
                        "小节标题": section_title(g, locale),
                        "行号": n,
                        "台词ID": key,
                        "说话人": speaker or "",
                        "台词": text[:160],
                        "CG名": cg,
                        "静态图": str(sfile.relative_to(BASE)) if sfile else "",
                        "动态CG": str(dmodel.relative_to(BASE)) if dmodel else "",
                        "匹配": match,
                    })
                per_category[category] += len(cgs)

    # different asset names can resolve to the same picture (differential variants):
    # keep the first occurrence per (section, resolved image) so the gallery has no
    # visually duplicated cards. The timeline MD keeps the true A->B->A sequence.
    first_seen, deduped = set(), []
    for r in rows:
        key = (r["小节"], r["静态图"] or r["CG名"])
        if key in first_seen:
            continue
        first_seen.add(key)
        deduped.append(r)
    rows = deduped
    match_kind = Counter(r["匹配"] for r in rows)

    print(f"groups scanned {groups_scanned}, with CG {groups_with_cg}")
    print(f"rows {len(rows)}, distinct CG {len(cg_seen)}")
    print("rows by category", dict(per_category))
    print("match quality", dict(match_kind))
    print(f"CG refs without exported file: {len(missing_files)} distinct / {sum(missing_files.values())} refs")
    for k, v in missing_files.most_common(12):
        print("   ", k, v)
    no_index = [n for n in static_cg if n not in {c.lower() for c in cg_seen}]
    print(f"exported static CG not referenced by any dialog: {len(no_index)}")

    if stats_only:
        return

    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["分类", "活动/章节", "活动键", "小节", "小节标题", "行号", "台词ID",
            "说话人", "台词", "CG名", "静态图", "动态CG", "匹配"]
    with (OUT / "剧情CG对照索引.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    (OUT / "剧情CG对照索引.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    unref = sorted(n for n in static_cg if n not in {c.lower() for c in cg_seen})
    with (OUT / "统计.txt").open("w", encoding="utf-8") as fh:
        fh.write(f"扫描剧本组 {groups_scanned}，含 CG 的组 {groups_with_cg}\n")
        fh.write(f"索引条目 {len(rows)}，涉及 CG {len(cg_seen)}\n")
        fh.write(f"分类分布 {dict(per_category)}\n")
        fh.write(f"引用但无导出文件的 CG：{len(missing_files)} 个\n")
        for k, v in missing_files.most_common():
            fh.write(f"  {k}\t{v}\n")
        fh.write(f"\n已导出但剧情中未引用的静态 CG：{len(unref)} 个\n")
        for n in unref:
            fh.write(f"  {n}\n")
    print("written", OUT / "剧情CG对照索引.csv")


if __name__ == "__main__":
    main()
