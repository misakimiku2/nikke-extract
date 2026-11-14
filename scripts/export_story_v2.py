"""Export newest NIKKE event scenario WITH speaker names (zh-CN).

Speaker detection:
  - EventScenarioDialogTable.<group>.mpk records are split by dialogue id strings.
  - In each record, the first token BEFORE the "Locale_MainScenario:" key that matches
    a character id from ScenarioCharacterSettingTable.mpk is the speaker.
  - Character id -> Locale_Character:<n>_name -> zh-CN name.
  - Records with no speaker token are narration / unnamed lines (game shows no name box).
"""
import json
import re
import sqlite3
from pathlib import Path

from text_clean import clean, speaker_of

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
LOCALE_MAIN = BASE / "decrypted" / "4f4bdc30e957b0f8157a2ec7b399f545.dec"
LOCALE_CHAR = BASE / "decrypted" / "e6059faf00471aa305c16cabe88871bb.dec"
GROUP_CSV = STATIC / "EventScenarioDialog.Group.csv"
OUT_MD = BASE / "NIKKE_最新活动剧情_玛丽安_简中.md"
OUT_JSON = BASE / "NIKKE_最新活动剧情_玛丽安_结构化.json"

TOKEN = re.compile(rb"[ -~]{4,}")


def build_names():
    raw = (STATIC / "ScenarioCharacterSettingTable.mpk").read_bytes()
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]
    pairs = {}
    for i, s in enumerate(toks):
        m = re.match(r"^Locale_Character:([A-Za-z0-9_]+)_name", s)
        if m and i > 0:
            pairs[toks[i - 1]] = m.group(1)
    conn = sqlite3.connect(LOCALE_CHAR)
    names = {}
    for rid, key in pairs.items():
        row = conn.execute(
            'SELECT "zh-CN" FROM "Locale_Character" WHERE "Key"=?', (key + "_name",)
        ).fetchone()
        names[rid] = row[0] if row and row[0] else rid
    conn.close()
    return names


def chapter_order():
    lines = [l.strip() for l in GROUP_CSV.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    return [l for l in lines if l.startswith("event_marian1_") or l.startswith("event_marian2_")]


def label_of(group):
    part = "第一部" if group.startswith("event_marian1_") else "第二部"
    tail = group[len("event_marian1_"):] if group.startswith("event_marian1_") else group[len("event_marian2_"):]
    if tail.startswith("prologue"):
        return part, "序章"
    if tail.startswith("epilogue"):
        return part, "尾声"
    if tail.startswith("intermission"):
        return part, "幕间 " + tail.rsplit("_", 1)[-1]
    m = re.match(r"(\d+)_([se])$", tail)
    if m:
        return part, f"第 {int(m.group(1))} 话 · {'前篇' if m.group(2) == 's' else '后篇'}"
    return part, tail


def parse_chapter(group, names):
    path = STATIC / f"EventScenarioDialogTable.{group}.mpk"
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    id_re = re.compile(re.escape(group) + r"_(\d+)$")
    anchors = [(o, int(id_re.match(s).group(1))) for o, s in toks if id_re.fullmatch(s)]
    out = {}
    for k, (start, n) in enumerate(anchors):
        end = anchors[k + 1][0] if k + 1 < len(anchors) else len(raw)
        seg = [s for o, s in toks if start <= o < end]
        lk = next((i for i, s in enumerate(seg) if s.startswith("Locale_MainScenario:")), None)
        if lk is None:
            continue
        key = seg[lk][len("Locale_MainScenario:"):]
        # tokens before the localkey: [portrait/character id, speaker-display id]
        # A name box is shown ONLY when two character ids are present; the LAST one
        # is the displayed name (e.g. "No.6" -> 6号, "unknown" -> ？？？).
        # With 0 or 1 id the line is narration / an unnamed line (no name box in game).
        before = seg[2:lk]
        chars = [s for s in before if s in names]
        speaker, sid = speaker_of(before, names)
        pid = chars[0] if chars else None
        out[n] = dict(
            key=key,
            speaker_id=sid,
            speaker=speaker,
            portrait_id=pid,
            portrait=names.get(pid) if pid else None,
        )
    return out


def main():
    names = build_names()
    main_conn = sqlite3.connect(LOCALE_MAIN)
    main_conn.row_factory = sqlite3.Row
    chapters = chapter_order()

    md = [
        "# NIKKE 最新活动剧情 · 玛丽安（Marian）",
        "",
        "> 简体中文（zh-CN）正文，按客户端剧情章节顺序排列，**加粗前缀为说话人**。",
        "> 未标注说话人的段落是旁白或无名字台词（游戏内不显示名字框）；JSON 里另存了画面立绘角色 `portrait` 供查考。",
        "> 来源：本机 `StaticData.pack`（`data/qa-261029-10b/579369`）+ `Locale_MainScenario` + `ScenarioCharacterSettingTable` + `Locale_Character`。",
        f"> 共 {len(chapters)} 个章节。",
        "",
        "---",
        "",
    ]
    structured = {"version": "data/qa-261029-10b/579369", "locale": "zh-CN",
                  "event": "event_marian1 + event_marian2", "chapters": []}
    total = with_sp = 0
    mismatches = []

    for idx, group in enumerate(chapters, 1):
        part, label = label_of(group)
        trow = main_conn.execute(
            'SELECT "zh-CN" FROM "Locale_MainScenario" WHERE "Key"=?', (group + "_title",)
        ).fetchone()
        title = (trow[0] if trow and trow[0] else "").strip()

        meta = parse_chapter(group, names)
        rows = main_conn.execute(
            'SELECT "Key","zh-CN","en","ja" FROM "Locale_MainScenario" WHERE "Key" LIKE ?',
            (group + "_%",),
        ).fetchall()
        text_by_n = {}
        for r in rows:
            m = re.match(re.escape(group) + r"_(\d+)$", r["Key"])
            if m:
                text_by_n[int(m.group(1))] = r
        if set(text_by_n) - set(meta):
            mismatches.append((group, sorted(set(text_by_n) - set(meta))[:5]))

        md.append(f"## {idx:02d}. {part} · {label}")
        md.append("")
        md.append(f"<!-- group: {group} -->")
        md.append("")
        if title:
            md.append(f"*章节标题：{title}*")
            md.append("")

        lines = []
        for n in sorted(text_by_n):
            r = text_by_n[n]
            info = meta.get(n, {})
            sp = info.get("speaker")
            text = (r["zh-CN"] or "").strip()
            lines.append({
                "n": n, "key": r["Key"],
                "speaker": sp, "speaker_id": info.get("speaker_id"),
                "portrait": info.get("portrait"), "portrait_id": info.get("portrait_id"),
                "zh-CN": clean(r["zh-CN"]), "en": r["en"], "ja": r["ja"],
            })
            total += 1
            if sp:
                with_sp += 1
            if not text:
                continue
            md.append(f"**{sp}**：{text}" if sp else text)
            md.append("")
        md.append("---")
        md.append("")
        structured["chapters"].append({
            "group": group, "part": part, "label": label, "title": title, "lines": lines,
        })

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"chapters={len(chapters)} lines={total} with_speaker={with_sp} narration={total - with_sp}")
    print("chapters missing dialogue metadata:", mismatches)
    uniq = {l["speaker"] for c in structured["chapters"] for l in c["lines"] if l["speaker"]}
    print("distinct speakers:", len(uniq))
    print("  ", " / ".join(sorted(uniq)))
    print("md  ->", OUT_MD, OUT_MD.stat().st_size)
    print("json->", OUT_JSON, OUT_JSON.stat().st_size)


if __name__ == "__main__":
    main()
