"""Render a '图文版' story markdown: dialogue with its CG inlined at the exact line.

Usage:
  python build_cg_story_md.py d_main_50            # one chapter (all d_main_50_* groups)
  python build_cg_story_md.py event_goddessfall1   # one event
  python build_cg_story_md.py --all-main           # every main chapter
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from build_cg_index import (BASE, STATIC, TOKEN, VALID_CG, activity_title, chapter_titles,
                            load_locale, load_names, resolve_cg, load_cg_files,
                            section_title, speaker_name)

OUT = BASE / "CG索引" / "图文版"
LOCALE = None
NAMES = None
STATIC_CG = DYN_CG = None


def group_file(group: str) -> Path | None:
    for tpl in ("ScenarioDialogTable.{}.mpk", "EventScenarioDialogTable.{}.mpk",
                "AttractiveScenarioDialogTable.{}.mpk"):
        p = STATIC / tpl.format(group)
        if p.exists():
            return p
    return None


def parse_lines(group: str, path: Path):
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    id_re = re.compile(re.escape(group) + r"_(\d+)$")
    anchors = [(o, int(id_re.match(s).group(1))) for o, s in toks if id_re.fullmatch(s)]
    prev: tuple[str, ...] = ()
    out = []
    for k, (start, n) in enumerate(anchors):
        end = anchors[k + 1][0] if k + 1 < len(anchors) else len(raw)
        seg = [s for o, s in toks if start <= o < end]
        lk = next((i for i, s in enumerate(seg) if s.startswith("Locale_MainScenario:")), None)
        if lk is None:
            continue
        key = seg[lk][len("Locale_MainScenario:"):]
        cgs = tuple(dict.fromkeys(s for s in seg if VALID_CG.match(s)))
        new_cgs = tuple(c for c in cgs if c not in prev)
        if cgs:
            prev = cgs
        text = (LOCALE.get(key) or "").replace("{AccountData.NickName}", "指挥官").strip()
        if not text:
            continue
        out.append({
            "n": n, "key": key,
            "who": speaker_name(seg[2:lk], NAMES),
            "text": text,
            "cg": new_cgs,
        })
    return out


def render_group(group: str) -> list[str]:
    path = group_file(group)
    if not path:
        return []
    lines = parse_lines(group, path)
    if not lines:
        return []
    title = section_title(group, LOCALE)
    md = [f"## {group}" + (f" · {title}" if title else ""), "", f"<!-- group: {group} -->", ""]
    for l in lines:
        for cg in l["cg"]:
            sfile, dyn, match = resolve_cg(cg, STATIC_CG, DYN_CG)
            thumb = BASE / "CG索引" / "缩略图" / (cg + ".webp")
            rel = f"../缩略图/{cg}.webp" if thumb.exists() else (
                "../../" + str(sfile.relative_to(BASE)).replace("\\", "/") if sfile else "")
            if rel:
                cap = f"*▲ {cg}*" + ("（近似匹配）" if match == "近似" else "")
                if dyn:
                    cap += " · 动态版在 `动态CG/模型/`"
                md += [f"![{cg}]({rel})", "", cap, ""]
        if l["who"]:
            md.append(f"**{l['who']}**：{l['text']}")
        else:
            md.append(l["text"])
        md.append("")
    return md


def groups_for(prefix: str) -> list[str]:
    out = []
    for csv_name in ("ScenarioDialog.Group.csv", "EventScenarioDialog.Group.csv",
                     "AttractiveScenarioDialog.Group.csv"):
        p = STATIC / csv_name
        if not p.exists():
            continue
        for g in p.read_text(encoding="utf-8-sig").splitlines():
            g = g.strip()
            if g and g != "group_id" and g.startswith(prefix):
                out.append(g)
    return out


def main():
    global LOCALE, NAMES, STATIC_CG, DYN_CG
    LOCALE = load_locale()
    NAMES = load_names()
    STATIC_CG, DYN_CG = load_cg_files()
    ch_titles = chapter_titles()

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    OUT.mkdir(parents=True, exist_ok=True)

    if args[0] == "--all-main":
        prefixes = [f"d_main_{n:02d}" for n in range(1, 51)]
    else:
        prefixes = args

    for pref in prefixes:
        groups = groups_for(pref)
        if not groups:
            print("no groups for", pref)
            continue
        act = activity_title(pref if pref.startswith(("d_main_", "event_")) else pref, LOCALE, ch_titles)
        md = [f"# {act}", "", "> 图文版：剧情文本 + 对应 CG，按台词行号插入。", ""]
        n_cg = 0
        for g in groups:
            part = render_group(g)
            n_cg += sum(1 for x in part if x.startswith("!["))
            md += part
        name = re.sub(r'[\\/:*?"<>|]', "_", f"{pref}_{act}.md")
        path = OUT / name
        path.write_text("\n".join(md), encoding="utf-8")
        print(f"{path.name}: {len(md)} 行, {n_cg} 张图")


if __name__ == "__main__":
    main()
