#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 NIKKE 活动小游戏「FADING AFFECTION / fadingaffection」的分支数据。

内部事件 key = event_firstaffection；小游戏本体是 EventTextAdvPlus 系列静态表
（不是 EventScenarioDialog 剧情）。数据表全部来自本机 staticdata/，文本来自
解密后的 Locale_Event。

输出：
  staging/fadingaffection_minigame.json   完整分支图（路线 / 页面 / 选项 / 结局）
  E:/test/nikke-web/public/data/fadingaffection.json   网站直接消费的副本

MPK 记录布局（逆向 2026-11-22，见 probe 脚本）：
  u32 记录数；每条记录：
    u8  flag   (0x0a 选项 / 0x15 页面 / 0x0f 路线 / 0x1c ...)
    i32 id
    i32 unknown / page-id（因表而异）
    i32 表常量 83501（ParsingTableId，fadingaffection 专有）
    之后是紧密排列的字段：
      i32 >= 0        -> 普通整数
      i32 < 0         -> 字符串：u32 长度 + UTF-8，tag 见下
  已知字符串 tag：-37 选项文本 key / -42 提示 key / -34 页面文本 key /
                -32 页面 CG 名 / -26,-25 页面 BGM /
                -41 结局 CG / -21..-13 SFX / -20 日期 /
                -48 路线描述 / -45 路线介绍 / -20 路线起始页 / -39 结局提示
  页面跳转 ID 以左移 1~2 字节的形式存放；逐字节扫描 i32 即可稳定还原。
"""
from __future__ import annotations

import json
import re
import sqlite3
import struct
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import locale_db

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
STAGING = BASE / "staging"
WEB_DATA = Path(r"E:\test\nikke-web\public\data")

CONST = 83501
NEEDLE = struct.pack("<i", CONST)
FLAGS = (0x08, 0x09, 0x0a, 0x0f, 0x15, 0x1c, 0x0c, 0x06)

# 页面 CG 的全部 tag（结局类型不同 tag 不同）
CG_TAGS = (-32, -41, -46, -42, -40)

# 通用剧情背景：小游戏没有专门的背景表，按地点选用游戏内已有的场景板
BG_NAMES = ["DestroyedStreet", "City_d", "Backstreet", "Lake", "Sunset",
            "RuinIndoor", "ShoppingStreet_d", "CityForest_01", "SnowTown_d"]

# 状态初值（来自 EventTextAdvPlusManagerTable：体力/粮食各 10，侵蚀 0）
STATUS_INIT = {"hp": 10, "food": 10, "erosion": 0}
STATUS_MAX = {"hp": 10, "food": 10, "erosion": 10}

# 选项对状态的影响：按选项文本关键词推导，UI 会明示消耗，避免"凭空扣数值"
COST_RULES = [
    (("分给", "喂", "分享粮食"), {"food": -2, "hp": 0, "erosion": -1}),
    (("吃", "进食", "吃掉", "取出粮食"), {"food": 2, "hp": 1, "erosion": 0}),
    (("进入", "走进", "进去", "仓库", "黑暗"), {"food": 0, "hp": 0, "erosion": 2}),
    (("扎营", "休息", "躲", "藏", "等待"), {"food": -1, "hp": 2, "erosion": -1}),
    (("前进", "继续", "跑", "冲", "交战", "开枪", "朝", "追"), {"food": -1, "hp": -2, "erosion": 1}),
    (("观察", "查看", "寻找", "确认", "戒备", "调查"), {"food": 0, "hp": 0, "erosion": -1}),
]
STR_RE = re.compile(r"^Locale_Event:fadingaffection_")


# ---------- generic MPK record reader ----------
def record_spans(raw: bytes) -> list[tuple[int, int, int, int]]:
    """返回 [(start, end, id, header_delta)]。"""
    starts: list[tuple[int, int]] = []
    pos = 0
    while True:
        i = raw.find(NEEDLE, pos)
        if i < 0:
            break
        for delta in (9, 5):
            st = i - delta
            if st >= 4 and raw[st] in FLAGS:
                rid = struct.unpack_from("<i", raw, st + 1)[0]
                if 0 < rid < 10_000_000:
                    starts.append((st, delta))
                    break
        pos = i + 4
    starts = sorted(set(starts))
    out = []
    for k, (st, delta) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(raw)
        out.append((st, end, struct.unpack_from("<i", raw, st + 1)[0], delta))
    return out


def strings_in(raw: bytes, st: int, end: int) -> list[tuple[int, str, str]]:
    """扫描记录里所有合法的负 tag 字符串，返回 [(tag, text, next_pos)]。"""
    out: list[tuple[int, str, int]] = []
    p = st
    while p + 8 <= end:
        tag = struct.unpack_from("<i", raw, p)[0]
        if -300 <= tag <= -10:
            ln = struct.unpack_from("<I", raw, p + 4)[0]
            if 3 <= ln <= 400 and p + 8 + ln <= end:
                try:
                    s = raw[p + 8:p + 8 + ln].decode("utf-8")
                except UnicodeDecodeError:
                    s = ""
                if s and all(ord(c) >= 9 for c in s):
                    out.append((tag, s, p + 8 + ln))
                    p += 8 + ln
                    continue
        p += 1
    return [(tag, s, nxt) for tag, s, nxt in out]


def ints_in(raw: bytes, st: int, end: int, lo: int, hi: int) -> list[tuple[int, int]]:
    """逐字节扫描范围内的 i32（跳转 ID 可能左移存放，故不能只按 4 对齐）。"""
    out = []
    for o in range(st, end - 3):
        v = struct.unpack_from("<i", raw, o)[0]
        if lo <= v <= hi:
            out.append((o, v))
    return out


# ---------- locale ----------
def locale_map() -> dict[str, str]:
    p = locale_db.find("Locale_Event")
    if p is None:
        raise SystemExit("Locale_Event not found in decrypted/")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        rows = con.execute('SELECT "Key","zh-CN" FROM "Locale_Event"').fetchall()
    finally:
        con.close()
    return {k: (v or "") for k, v in rows}


def text_of(loc: dict[str, str], key: str | None) -> str:
    if not key:
        return ""
    # 字符串字段里带 "Locale_Event:" 表名前缀，SQLite 里的 Key 没有
    plain = key.split(":", 1)[1] if ":" in key else key
    return loc.get(plain, "").strip()


# ---------- table parsers ----------
def parse_pages(loc: dict[str, str]) -> dict[int, dict]:
    raw = (STATIC / "EventTextAdvPlusEventPageTable.mpk").read_bytes()
    spans = record_spans(raw)
    pages: dict[int, dict] = {}
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        by_tag: dict[int, list[str]] = {}
        for tag, s, _ in strs:
            by_tag.setdefault(tag, []).append(s)
        key = next((s for s in by_tag.get(-34, []) if STR_RE.match(s)), None)
        if not key:
            continue
        page_id = rid
        cg = next((s for tag in CG_TAGS for s in by_tag.get(tag, []) if s.startswith("EventScene_")), None)
        bgm = next((s for s in by_tag.get(-26, []) + by_tag.get(-25, []) if s.startswith("event_bgm_")), None)
        pages[page_id] = dict(
            id=page_id,
            key=key,
            text=text_of(loc, key),
            cg=cg,
            bgm=bgm,
            next=None,
            links=[],
            _vals=[v for _, v in ints_in(raw, st, end, 1000, 9999)],
        )
    # 用真实页面集合过滤跳转候选（6655 等状态标志也落在 1000..6999）
    ids = set(pages)
    for page_id, pg in pages.items():
        link = [v for v in pg.pop("_vals") if v in ids and v != page_id]
        pg["next"] = link[-1] if link else None
        pg["links"] = link
    # endings: pages whose text key has a _title sibling
    for pid, pg in pages.items():
        base = pg["key"][len("Locale_Event:"):]
        title = text_of(loc, base + "_title")
        hint = text_of(loc, base + "_hint")
        if title or hint:
            pg["ending"] = {"title": title, "hint": hint}
    return pages


def parse_choices(loc: dict[str, str], pages: dict[int, dict]) -> dict[int, dict]:
    raw = (STATIC / "EventTextAdvPlusSelectOptionTable.mpk").read_bytes()
    spans = record_spans(raw)
    out: dict[int, dict] = {}
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        keys = [s for _, s, _ in strs if STR_RE.match(s) and s.endswith(tuple(f"_{i:02d}" for i in range(1, 21)))]
        key = keys[0] if keys else None
        if not key:
            continue
        hint = next((s for _, s, _ in strs if s.endswith("_hint")), None)
        sfx = next((s for _, s, _ in strs if s.startswith("sfx_")), None)
        vals = [v for _, v in ints_in(raw, st, end, 1000, 9999)]
        src = vals[0] if vals else None
        cand = [v for v in vals[1:] if v in pages]
        dest = cand[-1] if cand else None
        ctext = text_of(loc, key)
        cost = {"hp": 0, "food": 0, "erosion": 0}
        for words, delta in COST_RULES:
            if any(w in ctext for w in words):
                for k, v in delta.items():
                    cost[k] += v
                break
        out[rid] = dict(
            id=rid,
            page=src,
            key=key,
            text=ctext,
            hintKey=hint,
            hint=text_of(loc, hint),
            sfx=sfx,
            dest=dest,
            candidates=cand,
            cost=cost,
        )
    return out


def parse_first(loc: dict[str, str], pages: dict[int, dict]) -> list[dict]:
    raw = (STATIC / "EventTextAdvPlusFirstSelectTable.mpk").read_bytes()
    spans = record_spans(raw)
    out = []
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        key = next((s for _, s, _ in strs if STR_RE.match(s)), None)
        if not key:
            continue
        # 首选项：目标页紧跟在字符串字段之后（后面的 1114 等是其它字段）
        after = max((n for _, _, n in strs), default=st)
        cand = [v for _, v in ints_in(raw, after, end, 1000, 6999) if v in pages]
        m = re.match(r"fadingaffection_(\d+)_\d+$", key.split(":", 1)[-1])
        out.append(dict(page=int(m.group(1)) if m else rid, key=key,
                        text=text_of(loc, key),
                        dest=cand[0] if cand else None, candidates=cand))
    return out


def parse_routes(loc: dict[str, str]) -> list[dict]:
    raw = (STATIC / "EventTextAdvPlusRouteTable.mpk").read_bytes()
    spans = record_spans(raw)
    out = []
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        ss = [s for _, s, _ in strs]
        name = next((s for s in ss if re.search(r"fadingaffection_route\d+_name$", s)), None)
        desc = next((s for s in ss if s.endswith("_description")), None)
        start = next((s for s in ss if re.fullmatch(r"Locale_Event:fadingaffection_\d{4}", s)), None)
        intro = next((s for s in ss if "intro" in s), None)
        date = next((s for s in ss if re.match(r"\d{4}-", s)), None)
        m = re.search(r"fadingaffection_route(\d+)_name$", name or "")
        out.append(dict(
            no=int(m.group(1)) if m else None,
            name=text_of(loc, name),
            nameKey=name,
            desc=text_of(loc, desc),
            startKey=start,
            start=int(start.rsplit("_", 1)[-1]) if start else None,
            intro=text_of(loc, intro),
            introText=text_of(loc, start),
            unlock=date,
        ))
    return out


def parse_memories(loc: dict[str, str]) -> list[dict]:
    """saveitem = 死亡后留下的「已储存的记忆」，45 条，按路线分组。"""
    raw = (STATIC / "EventTextAdvPlusLootItemTable.mpk").read_bytes()
    spans = record_spans(raw)
    out = []
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        ss = [s for _, s, _ in strs]
        m = next((s for s in ss if re.search(r"saveitem_\d+_\d+_name$", s)), None)
        if not m:
            continue
        g = re.search(r"saveitem_(\d+)_(\d+)_name$", m)
        desc = next((s for s in ss if "_description" in s), None)
        inven = next((s for s in ss if "_inven_02" in s), None)
        out.append(dict(
            route=int(g.group(1)), index=int(g.group(2)),
            name=text_of(loc, m), desc=text_of(loc, desc),
            short=text_of(loc, inven),
        ))
    return out


def bg_hashes() -> dict[str, str]:
    p = WEB_DATA / "cg_index.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {it["n"]: it["h"] for it in data.get("items", []) if it["n"] in BG_NAMES}


def cg_hashes() -> dict[str, str]:
    p = WEB_DATA / "cg_index.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {it["n"]: it["h"] for it in data.get("items", [])}


def main() -> None:
    loc = locale_map()
    pages = parse_pages(loc)
    choices = parse_choices(loc, pages)
    first = parse_first(loc, pages)
    routes = parse_routes(loc)
    memories = parse_memories(loc)
    hashes = cg_hashes()
    bgs = bg_hashes()

    # route membership: walk from each route start via first/choices
    by_page_first: dict[int, list[dict]] = {}
    for c in first:
        by_page_first.setdefault(c["page"], []).append(c)
    by_page_choice: dict[int, list[dict]] = {}
    for c in choices.values():
        if c["page"]:
            by_page_choice.setdefault(c["page"], []).append(c)

    data = dict(
        version="qa-261122 (client rev 583593) / EventTextAdvPlus",
        event="event_firstaffection",
        title="FADING AFFECTION",
        subtitle="渐逝的爱意",
        status={"init": STATUS_INIT, "max": STATUS_MAX},
        backgrounds=bgs,
        memories=memories,
        routes=routes,
        pages={str(k): v for k, v in sorted(pages.items())},
        choices={str(k): v for k, v in sorted(choices.items())},
        firstChoices=first,
        cgHashes={k: v for k, v in hashes.items() if k.startswith("EventScene_FadingAffection")},
    )

    STAGING.mkdir(parents=True, exist_ok=True)
    out = STAGING / "fadingaffection_minigame.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    web = WEB_DATA / "fadingaffection.json"
    web.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    endings = {k: v for k, v in pages.items() if v.get("ending")}
    print(f"routes={len(routes)} pages={len(pages)} choices={len(choices)} "
          f"first={len(first)} endings={len(endings)} memories={len(memories)} "
          f"cgHashes={len(data['cgHashes'])} backgrounds={len(bgs)}")
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
    print(f"wrote {web} ({web.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
