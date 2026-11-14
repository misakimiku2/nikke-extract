"""Export the newest NIKKE event scenario (Marian 1 + 2) from local decrypted data.

Sources (all local, read-only):
  - Locale_MainScenario SQLite (from saus/raw/*.lsc, NKDB-decrypted)
  - EventScenarioDialog.Group.csv (from StaticData.pack -> StaticData.zip)
"""
import json
import re
import sqlite3
from pathlib import Path

from text_clean import clean

BASE = Path(r"E:\test\nikke_extract")
LOCALE_DB = BASE / "decrypted" / "4f4bdc30e957b0f8157a2ec7b399f545.dec"
GROUP_CSV = BASE / "staticdata" / "EventScenarioDialog.Group.csv"
OUT_MD = BASE / "NIKKE_最新活动剧情_玛丽安_简中.md"
OUT_JSON = BASE / "NIKKE_最新活动剧情_玛丽安_结构化.json"

CHAPTER_LABEL = {
    "prologue": "序章",
    "intermission": "幕间",
    "epilogue": "尾声",
}


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


def main():
    conn = sqlite3.connect(LOCALE_DB)
    conn.row_factory = sqlite3.Row
    chapters = chapter_order()

    md = [
        "# NIKKE 最新活动剧情 · 玛丽安（Marian）",
        "",
        "> 简体中文（zh-CN）正文，按客户端剧情章节顺序排列。",
        "> 来源：本机游戏静态数据 `StaticData.pack`（版本 `data/qa-261029-10b/579369`）+ 本地化库 `Locale_MainScenario`。",
        f"> 共 {len(chapters)} 个章节。",
        "",
        "---",
        "",
    ]
    structured = {"version": "data/qa-261029-10b/579369", "locale": "zh-CN",
                  "event": "event_marian1 + event_marian2", "chapters": []}
    total_lines = 0

    for idx, group in enumerate(chapters, 1):
        part, label = label_of(group)
        trow = conn.execute(
            'SELECT "zh-CN" FROM "Locale_MainScenario" WHERE "Key"=?', (group + "_title",)
        ).fetchone()
        title = (trow[0] if trow and trow[0] else "").strip()

        rows = conn.execute(
            'SELECT "Key","zh-CN","en","ja" FROM "Locale_MainScenario" WHERE "Key" LIKE ?',
            (group + "_%",),
        ).fetchall()
        lines = []
        for r in rows:
            m = re.match(re.escape(group) + r"_(\d+)$", r["Key"])
            if m:
                lines.append((int(m.group(1)), r))
        lines.sort(key=lambda x: x[0])
        total_lines += len(lines)

        md.append(f"## {idx:02d}. {part} · {label}" + (f"：{title}" if title else ""))
        md.append("")
        md.append(f"<!-- group: {group} -->")
        md.append("")
        if title:
            md.append(f"**{title}**")
            md.append("")
        for n, r in lines:
            text = (r["zh-CN"] or "").strip()
            if not text:
                continue
            md.append(text)
            md.append("")
        md.append("---")
        md.append("")

        structured["chapters"].append({
            "group": group, "part": part, "label": label, "title": title,
            "lines": [{"n": n, "key": r["Key"], "zh-CN": clean(r["zh-CN"]),
                       "en": r["en"], "ja": r["ja"]} for n, r in lines],
        })

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"chapters={len(chapters)} lines={total_lines}")
    print("md  ->", OUT_MD, OUT_MD.stat().st_size, "bytes")
    print("json->", OUT_JSON, OUT_JSON.stat().st_size, "bytes")
    print("first chapters:", [c["group"] for c in structured["chapters"][:3]])
    print("last  chapters:", [c["group"] for c in structured["chapters"][-3:]])


if __name__ == "__main__":
    main()
