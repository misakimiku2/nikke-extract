#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 NIKKE 活动「SKY ON THE ROCK」剧情文本（简中，带说话人）。

随 2026-11-19 国际服更新上线的新活动，内部 event key = event_skyontherock。
对白结构来自新解包的 staticdata/EventScenarioDialogTable.event_skyontherock_*.mpk，
正文在 decrypted 的 Locale_SubScenario（不是 MainScenario），speaker 名走
Locale_Character:<id>_name。流程与 export_story_v2.py 一致，仅 locale 表不同。

输出：
  NIKKE_最新活动剧情_SKY_ON_THE_ROCK_简中.md
  NIKKE_最新活动剧情_SKY_ON_THE_ROCK_结构化.json
"""
import json
import re
import sqlite3
from pathlib import Path

import cg_refs
from text_clean import clean, speaker_of, speaker_of_type, record_type

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
GROUP_CSV = STATIC / "EventScenarioDialog.Group.csv"
OUT_MD = BASE / "NIKKE_最新活动剧情_SKY_ON_THE_ROCK_简中.md"
OUT_JSON = BASE / "NIKKE_最新活动剧情_SKY_ON_THE_ROCK_结构化.json"
PREFIX = "event_skyontherock_"
VERSION = "data/qa-261119-10b/580722 (client rev 583058/583593)"
TOKEN = re.compile(rb"[ -~]{4,}")


def find_locale(table):
    for p in (BASE / "decrypted").glob("*.dec"):
        try:
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            if table in [r[0] for r in c.execute("select name from sqlite_master where type='table'")]:
                return c
            c.close()
        except Exception:
            pass
    raise SystemExit(f"locale table not found: {table}")


class Store:
    """多张 Locale 表的只读查询封装：store.get(table, key) -> 文本。"""

    def __init__(self):
        self.conns = {}

    def add(self, table, conn):
        self.conns[table] = conn

    def get(self, table, key):
        c = self.conns.get(table)
        if c is None:
            return None
        row = c.execute(f'SELECT "zh-CN" FROM "{table}" WHERE "Key"=?', (key,)).fetchone()
        return row[0] if row else None


def build_names(conn):
    """角色内部 id -> 中文名（ScenarioCharacterSettingTable 的 Locale_Character:<n>_name）。"""
    raw = (STATIC / "ScenarioCharacterSettingTable.mpk").read_bytes()
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]
    pairs = {}
    for i, s in enumerate(toks):
        m = re.match(r"^Locale_Character:([A-Za-z0-9_]+)_name$", s)
        if m and i > 0:
            pairs[toks[i - 1]] = m.group(1)
    names = {}
    for rid, key in pairs.items():
        row = conn.execute(
            'SELECT "zh-CN" FROM "Locale_Character" WHERE "Key"=?', (key + "_name",)
        ).fetchone()
        names[rid] = row[0] if row and row[0] else rid
    return names


def label_of(group):
    tail = group[len(PREFIX):]
    if tail.startswith("prologue"):
        return "序章"
    if tail.startswith("epilogue"):
        return "尾声"
    if tail.startswith("intermission"):
        return "幕间"
    m = re.match(r"(\d+)_([se])$", tail)
    if m:
        return f"第 {int(m.group(1))} 话 · {'前篇' if m.group(2) == 's' else '后篇'}"
    return tail


def parse_chapter(group, names, store, table="Locale_SubScenario"):
    """与 export_rest.parse 同构：以 Locale 标记为锚点，向前找 group 标记。

    行 key 后常粘着二进制字节（..._1A），按「行 key + 数字」匹配会整段漏掉；
    以 Locale_<table>:<key> 为锚点、再回看 group token，才能拿到完整说话人 token。
    """
    path = STATIC / f"EventScenarioDialogTable.{group}.mpk"
    raw = path.read_bytes()
    toks = [(m.start(), m.end(), m.group().decode("ascii", "replace"))
            for m in TOKEN.finditer(raw)]
    out = {}

    def group_ok(tok, g):
        return tok == g or (tok.startswith(g) and len(tok) <= len(g) + 2)

    for i, (_s, _e, t) in enumerate(toks):
        if not t.startswith("Locale_") or ":" not in t:
            continue
        tbl, key = t.split(":", 1)
        if tbl != table or store.get(tbl, key) is None:
            continue
        gi = next((j for j in range(i - 1, max(-1, i - 80), -1)
                   if group_ok(toks[j][2], group)), None)
        if gi is None:
            continue
        pre = [x for _o, _e, x in toks[gi + 1:i]]
        m = re.search(r"_(\d+)$", key)
        if not m:
            continue
        n = int(m.group(1))
        chars = [s for s in pre if s in names]
        speaker, sid = speaker_of(pre, names)
        typ = record_type(raw, group, toks[gi][0])
        if typ in (0, 1, 2, 4, 5):
            by_type = speaker_of_type(typ)
            if by_type is not None:
                speaker, sid = by_type
        pid = chars[0] if chars else None
        out[n] = dict(
            key=key, speaker_id=sid, speaker=speaker,
            portrait_id=pid, portrait=names.get(pid) if pid else None,
        )
    return out


def scan_cg(group, store, bg_names=None):
    """CG 转场/背景/特效独立扫描：不按 Locale_SubScenario 过滤，全部 Locale 锚点都算记录边界。

    返回 {行号: {"cg": [...] / "bg": [...] / "fx": [...]}}，各自只在发生变化的行上有条目。
    """
    path = STATIC / f"EventScenarioDialogTable.{group}.mpk"
    raw = path.read_bytes()
    toks = [(m.start(), m.end(), m.group().decode("ascii", "replace"))
            for m in TOKEN.finditer(raw)]

    def group_ok(tok, g):
        return tok == g or (tok.startswith(g) and len(tok) <= len(g) + 2)

    recs = []
    for i, (_s, _e, t) in enumerate(toks):
        if not t.startswith("Locale_") or ":" not in t:
            continue
        gi = next((j for j in range(i - 1, max(-1, i - 80), -1)
                   if group_ok(toks[j][2], group)), None)
        if gi is not None:
            recs.append((i, gi))
    cg_meta: dict[int, dict] = {}
    pending = pending_bg = pending_fx = ()
    prev_cg = prev_bg = prev_fx = None
    for k, (i, gi) in enumerate(recs):
        span_end = toks[recs[k + 1][1]][0] if k + 1 < len(recs) else len(raw)
        # 字面 token + 演出位 id 间接引用的动态 CG
        cgs = cg_refs.merge_cgs(
            cg_refs.collect_cgs(raw, toks[gi][0], span_end),
            cg_refs.collect_movie_cgs(raw, toks[gi][0], span_end))
        bgs = cg_refs.collect_bgs(raw, toks[gi][0], span_end, bg_names or set())
        fxs = cg_refs.collect_fx(raw, toks[gi][0], span_end)
        tbl, key = toks[i][2].split(":", 1)
        if store.get(tbl, key) is None and not cgs and not bgs and not fxs:
            pending = cgs or pending
            pending_bg = bgs or pending_bg
            pending_fx = fxs or pending_fx
            continue
        m = re.search(r"_(\d+)$", key)
        if not m:
            pending = cgs or pending
            pending_bg = bgs or pending_bg
            pending_fx = fxs or pending_fx
            continue
        n = int(m.group(1))
        eff = cgs or pending
        pending = ()
        eff_bg = bgs or pending_bg
        pending_bg = ()
        eff_fx = fxs or pending_fx
        pending_fx = ()
        if cg_refs.changed(prev_cg, eff):
            cg_meta.setdefault(n, {}).update({"cg": list(eff)})
            prev_cg = eff
        if eff_bg and cg_refs.changed(prev_bg, eff_bg):
            cg_meta.setdefault(n, {}).update({"bg": list(eff_bg)})
            prev_bg = eff_bg
        if eff_fx and cg_refs.changed(prev_fx, eff_fx):
            cg_meta.setdefault(n, {}).update({"fx": list(eff_fx)})
            prev_fx = eff_fx
    return cg_meta


def main():
    lc = find_locale("Locale_Character")
    sub = find_locale("Locale_SubScenario")
    main_loc = find_locale("Locale_MainScenario")
    store = Store()
    store.add("Locale_Character", lc)
    store.add("Locale_SubScenario", sub)
    store.add("Locale_MainScenario", main_loc)
    names = build_names(lc)
    static_cg, dynamic_cg = cg_refs.load_cg_library()
    bg_names = cg_refs.load_bg_names()
    lines = [l.strip() for l in GROUP_CSV.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    chapters = [l for l in lines if l.startswith(PREFIX)]
    print("chapters:", len(chapters))

    md = [
        "# NIKKE 最新活动剧情 · SKY ON THE ROCK",
        "",
        "> 简体中文（zh-CN）正文，按客户端剧情章节顺序排列，**加粗前缀为说话人**。",
        "> 未标注说话人的段落是旁白或无名字台词（游戏内不显示名字框）；JSON 里另存了画面立绘角色 `portrait` 供查考。",
        f"> 来源：本机 StaticData.pack（`{VERSION}`）+ Locale_SubScenario + ScenarioCharacterSettingTable + Locale_Character。",
        f"> 共 {len(chapters)} 个章节。",
        "",
        "---",
        "",
    ]
    structured = {"version": VERSION, "locale": "zh-CN",
                  "event": "event_skyontherock", "title": "SKY ON THE ROCK", "chapters": []}
    total = with_sp = 0
    mismatches = []

    for idx, group in enumerate(chapters, 1):
        label = label_of(group)
        trow = sub.execute(
            'SELECT "zh-CN" FROM "Locale_SubScenario" WHERE "Key"=?', (group + "_title",)
        ).fetchone()
        title = (trow[0] if trow and trow[0] else "").strip()

        meta = parse_chapter(group, names, store)
        for n, extra in scan_cg(group, store, bg_names).items():
            if n in meta:
                meta[n].update(extra)
            else:
                meta[n] = {"key": f"{group}_{n}", **extra}
        rows = sub.execute(
            'SELECT "Key","zh-CN","en","ja" FROM "Locale_SubScenario" WHERE "Key" LIKE ?',
            (group + "_%",),
        ).fetchall()
        text_by_n = {}
        for r in rows:
            m = re.match(re.escape(group) + r"_(\d+)$", r[0])
            if m:
                text_by_n[int(m.group(1))] = r
        if set(text_by_n) - set(meta):
            mismatches.append((group, sorted(set(text_by_n) - set(meta))[:5]))

        md.append(f"## {idx:02d}. {label}")
        md.append("")
        md.append(f"<!-- group: {group} -->")
        md.append("")
        if title:
            md.append(f"*章节标题：{title}*")
            md.append("")

        lines_out = []
        # 带 cg 但没有台词文本的记录也要遍历，转场标记不能丢
        for n in sorted(set(text_by_n)
                        | {m for m, v in meta.items() if v.get("cg") or v.get("bg") or v.get("fx")}):
            r = text_by_n.get(n)
            info = meta.get(n, {})
            sp = info.get("speaker")
            if r is None:
                if info.get("bg") or info.get("fx"):
                    md += cg_refs.scene_marker_md(info.get("bg"), info.get("fx"), static_cg, up=".")
                if info.get("cg"):
                    md += cg_refs.marker_md(info["cg"], static_cg, dynamic_cg, up=".")
                continue
            text = (r[1] or "").strip()
            line = {
                "n": n, "key": r[0],
                "speaker": sp, "speaker_id": info.get("speaker_id"),
                "portrait": info.get("portrait"), "portrait_id": info.get("portrait_id"),
                "zh-CN": clean(r[1]), "en": r[2], "ja": r[3],
            }
            if info.get("cg"):
                line["cg"] = info["cg"]
            lines_out.append(line)
            total += 1
            if sp:
                with_sp += 1
            if info.get("bg") or info.get("fx"):
                md += cg_refs.scene_marker_md(info.get("bg"), info.get("fx"), static_cg, up=".")
            if info.get("cg"):
                md += cg_refs.marker_md(info["cg"], static_cg, dynamic_cg, up=".")
            if not text:
                continue
            md.append(f"**{sp}**：{text}" if sp else text)
            md.append("")
        md.append("---")
        md.append("")
        structured["chapters"].append({
            "group": group, "label": label, "title": title, "lines": lines_out,
        })

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"chapters={len(chapters)} lines={total} with_speaker={with_sp} narration={total-with_sp}")
    print("chapters missing dialogue metadata:", mismatches)
    uniq = {l["speaker"] for c in structured["chapters"] for l in c["lines"] if l["speaker"]}
    print("distinct speakers:", len(uniq), "/", " / ".join(sorted(uniq)))


if __name__ == "__main__":
    main()
