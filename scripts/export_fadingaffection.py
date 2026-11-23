#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 NIKKE 活动小游戏「FADING AFFECTION / fadingaffection」的分支数据。

内部事件 key = event_firstaffection；小游戏本体是 EventTextAdvPlus 系列静态表
（不是 EventScenarioDialog 剧情）。数据表全部来自本机 staticdata/，文本来自
解密后的 Locale_Event。

输出：
  staging/fadingaffection_minigame.json   完整分支图（路线 / 页面 / 选项 / 结局）
  E:/test/nikke-web/public/data/fadingaffection.json   网站直接消费的副本

MPK 记录布局（逆向 2026-11-22，字段区定位 2026-11-23）：
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

解锁条件是定长字段，不需要靠字节扫描猜：
  选项：-37 选项文本 key 字符串之后（4 字节对齐）依次是
          i32 condType  0 无条件 / 1 需要记忆 / 2 需要状态 / 3 需要结局
          i32 condValue 记忆 id（LootItemTable 记录 id）或结局页号
        172 条选项里 38 条带条件，其中只有 25 条带 hint —— 只看 hint 会漏 13 条。
  页面：-34 正文 key 字符串之后第 9 字节是
          u8  kind      0 普通页 / 1 授予记忆的节点 / 2 结局页
          i32 (+8)      本页授予的记忆 id（0 = 不授予）
        45 条记忆正好被 46 个页面授予（6203 与 6205 都给 1203）。
        记忆 id != 授予页号：例如 1-14「小径」(1114) 由页面 1142 授予。
  地点选择：记录末尾同样是记忆 id / 结局页号（1114「小径」、1214、结局 7205）。

状态：Manager 表 83501 记录里每条状态是「i32 a | i32 b | 名称串 | 图标串」，
      体力 10/10、粮食 1/1、侵蚀 100/50 —— 粮食上限只有 1 份，是随身物品不是消耗条。
      整个表族（Manager/Route/EventPage/SelectOption/FirstSelect/LootItem/
      ProgressReward/SpecialIntro）里没有任何状态增减量：把 8 张表的所有 4 字节窗口
      都扫过，[-9,-1] 且后面不是字符串 tag 的字段命中数为 0。
      所以状态只是剧情门槛/演出内容，不导出 per-option cost。
      侵蚀度按路线启用（routes[].erosion）：只有路线 2 存在「选项 -> 侵蚀结局(7xxx)」
      的跳转；路线 1 的 7101 由页面 1209 自动推进触发。页面所属路线取 st+9 字段。
  跳转页号仍以左移 1~2 字节的形式存放，页面/选项的 dest 靠逐字节扫描 i32 还原。
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

# 状态定义来自 EventTextAdvPlusManagerTable 记录 83501（见 parse_manager）：
# 每条状态是「i32 a | i32 b | 名称串 | 图标串」，实测 hp 10/10、food 1/1、erosion 100/50。
# 名称串的 tag 即每条状态的分隔标记。
STATUS_TAGS = {"hp": -44, "food": -46, "erosion": -49}
STR_RE = re.compile(r"^Locale_Event:fadingaffection_")

# 记忆条目分三类，解锁条件里引用的是 LootItem 记录 id（不是页号）
LOOT_KINDS = {"saveitem": "save", "deleteditem": "deleted", "fragmenteditem": "fragment"}


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
def field_at(raw: bytes, pos: int) -> int:
    return struct.unpack_from("<i", raw, pos)[0] if pos + 4 <= len(raw) else 0


def parse_pages(loc: dict[str, str], loot_ids: set[int]) -> dict[int, dict]:
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
        # 头之后第一个字段（st+9）是路线号 11/12/13 —— 结局页也带，比 id 前缀可靠
        rtag = field_at(raw, st + 9)
        key_end = next(n for tag, s, n in strs if tag == -34 and s == key)
        # 正文 key 字符串之后固定 +9 是「抵达本页授予的记忆 id」（0 = 不给）
        grant = field_at(raw, key_end + 9)
        if grant not in loot_ids:
            grant = 0
        cg = next((s for tag in CG_TAGS for s in by_tag.get(tag, []) if s.startswith("EventScene_")), None)
        bgm = next((s for s in by_tag.get(-26, []) + by_tag.get(-25, []) if s.startswith("event_bgm_")), None)
        pages[page_id] = dict(
            id=page_id,
            key=key,
            text=text_of(loc, key),
            route=rtag - 10 if rtag in (11, 12, 13) else None,
            cg=cg,
            bgm=bgm,
            grant=grant or None,
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


def parse_manager(loc: dict[str, str]) -> dict:
    """EventTextAdvPlusManagerTable 记录 83501：三条状态的定义。

    每条状态在表里是「i32 a | i32 b | 名称串 | 图标串」（数值紧挨名称串之前）：
      体力 a=10 b=10 / 粮食 a=1 b=1 / 侵蚀 a=100 b=50
    a 是上限，粮食上限只有 1 份 —— 与官方教程「选择特定选项时，可能需要粮食」一致，
    它是随身物品而不是消耗条。侵蚀的 b=50 按 0..100 量尺上的触发阈值理解
    （教程：「侵蚀数值达到一定程度时，记录对象将进入侵蚀状态」；表内无法与初值区分）。

    重要：整个 EventTextAdvPlus 表族里找不到任何状态增减量（见 README/文档），
    所以状态只作为剧情门槛导出，不导出 per-option cost。
    """
    raw = (STATIC / "EventTextAdvPlusManagerTable.mpk").read_bytes()
    st, end, _, _ = record_spans(raw)[0]
    strs = strings_in(raw, st, end)
    items = []
    for i, (tag, s, nxt) in enumerate(strs):
        key = next((k for k, t in STATUS_TAGS.items() if t == tag), None)
        if not key:
            continue
        data_start = nxt - len(s.encode("utf-8"))
        items.append(dict(
            key=key, name=text_of(loc, s), nameKey=s, icon=next(
                (x for _, x, _ in strs[i + 1:i + 3] if x.startswith("icn_")), None),
            max=field_at(raw, data_start - 16), second=field_at(raw, data_start - 12),
        ))
    maxes = {it["key"]: it["max"] for it in items}
    init = {"hp": maxes.get("hp", 10), "food": maxes.get("food", 1), "erosion": 0}
    return dict(items=items, init=init,
                max={**{"hp": 10, "food": 1, "erosion": 100}, **maxes})


def req_of(ctype: int, cval: int, loc: dict[str, str], pages: dict[int, dict],
           memories: dict[int, dict]) -> dict | None:
    """把选项的 (condType, condValue) 翻成可读的解锁条件。

    condType 1 -> condValue 是记忆 id；2 -> 状态门槛（粮食）；3 -> 需先抵达的结局页。
    """
    if not ctype or not cval:
        return None
    if ctype == 1:
        mem = memories.get(cval)
        if not mem:
            return {"kind": "memory", "id": cval, "page": None, "name": f"#{cval}"}
        return {"kind": "memory", "id": cval, "page": mem["grantPage"],
                "memory": f"{mem['route']}-{mem['index']}", "name": mem["name"],
                "memoryKind": mem["kind"]}
    if ctype == 3:
        title = ""
        if cval in pages:
            title = text_of(loc, pages[cval]["key"] + "_title")
        return {"kind": "ending", "id": cval, "page": cval, "name": title}
    if ctype == 2:
        return {"kind": "state", "id": cval, "page": None, "name": f"粮食 ≥ {cval}"}
    return {"kind": "unknown", "id": cval, "page": None, "name": ""}


def parse_choices(loc: dict[str, str], pages: dict[int, dict],
                  memories: dict[int, dict]) -> dict[int, dict]:
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
        # 每个选项都带 (condType, condValue)，位于选项 key 字符串之后、4 字节对齐。
        # 只有 25 条带 hint，但带条件的有 38 条：条件不能只在有 hint 时才读。
        key_end = next(n for tag, s, n in strs if tag == -37 and s == key)
        req = req_of(field_at(raw, key_end), field_at(raw, key_end + 4), loc, pages, memories)
        ctext = text_of(loc, key)
        out[rid] = dict(
            id=rid,
            page=src,
            key=key,
            text=ctext,
            hintKey=hint,
            hint=text_of(loc, hint),
            req=req,
            sfx=sfx,
            dest=dest,
            candidates=cand,
        )
    return out


def parse_first(loc: dict[str, str], pages: dict[int, dict],
                memories: dict[int, dict]) -> list[dict]:
    raw = (STATIC / "EventTextAdvPlusFirstSelectTable.mpk").read_bytes()
    spans = record_spans(raw)
    out = []
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        key = next((s for _, s, _ in strs if STR_RE.match(s)), None)
        if not key:
            continue
        # 目标页紧跟在字符串之后；记录末尾的 4 位数是解锁条件：
        #   1114/1214 是记忆 id（小径 / 一起走的路），7205 是结局页号。
        after = max((n for _, _, n in strs), default=st)
        tail = [v for _, v in ints_in(raw, after, end, 1000, 9999)]
        cand = [v for v in tail if v in pages]
        dest = cand[0] if cand else None
        unlock = None
        for v in reversed(tail):
            # 记录里第一个 4 位数是目标页号，它同时也可能是某个记忆 id，必须跳过
            if v == dest:
                continue
            if v in memories:
                mem = memories[v]
                unlock = {"kind": "memory", "id": v, "page": mem["grantPage"],
                          "memory": f"{mem['route']}-{mem['index']}", "name": mem["name"],
                          "memoryKind": mem["kind"]}
            elif 6000 <= v <= 9999 and v in pages:
                unlock = {"kind": "ending", "id": v, "page": v,
                          "name": text_of(loc, pages[v]["key"] + "_title")}
            else:
                continue
            break
        m = re.match(r"fadingaffection_(\d+)_\d+$", key.split(":", 1)[-1])
        out.append(dict(page=int(m.group(1)) if m else rid, key=key,
                        text=text_of(loc, key),
                        dest=dest, candidates=cand, unlock=unlock))
    return out


def parse_routes(loc: dict[str, str], pages: dict[int, dict]) -> list[dict]:
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
        rno = int(m.group(1)) if m else None
        # 路线解锁：原作要求先看完前一条记录的结局。TrueEnd 是该记录的收束：
        # 路线2 需 8101「命运共同体」，路线3 需 8201「相守的梦」
        req = None
        if rno in (2, 3):
            rp = 8101 if rno == 2 else 8201
            req = {"kind": "ending", "id": rp, "page": rp,
                   "name": text_of(loc, pages[rp]["key"] + "_title") if rp in pages else ""}
        out.append(dict(
            no=rno,
            unlockRequirement=req,
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


def parse_memories(loc: dict[str, str], pages: dict[int, dict]) -> dict[int, dict]:
    """LootItemTable 共 45 条记忆：已储存 / 已删除 / 仅剩一部分。

    记录 id 就是记忆 id（选项解锁条件引用它），授予页从页面表的 +9 字段反查。
    """
    raw = (STATIC / "EventTextAdvPlusLootItemTable.mpk").read_bytes()
    spans = record_spans(raw)
    granted: dict[int, list[int]] = {}
    for pid, pg in pages.items():
        if pg["grant"]:
            granted.setdefault(pg["grant"], []).append(pid)
    out: dict[int, dict] = {}
    for st, end, rid, _ in spans:
        strs = strings_in(raw, st, end)
        ss = [s for _, s, _ in strs]
        name = next((s for s in ss if s.endswith("_name")), None)
        if not name:
            continue
        kind = next((k for kw, k in LOOT_KINDS.items() if kw in name), "save")
        g = re.search(r"item_(\d+)_(\d+)_name$", name)
        src = granted.get(rid, [])
        out[rid] = dict(
            id=rid, kind=kind,
            route=int(g.group(1)) if g else 0, index=int(g.group(2)) if g else 0,
            name=text_of(loc, name), desc=text_of(loc, next((s for s in ss if "_description" in s), None)),
            short=text_of(loc, next((s for s in ss if "_inven_02" in s), None)),
            grantPage=src[0] if src else None,
            grantPages=src,
        )
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


def memory_ids() -> set[int]:
    """LootItemTable 的记录 id 集合（= 记忆 id，解锁条件引用的就是这个）。"""
    raw = (STATIC / "EventTextAdvPlusLootItemTable.mpk").read_bytes()
    return {rid for st, end, rid, _ in record_spans(raw)
            if any(s.endswith("_name") for _, s, _ in strings_in(raw, st, end))}


def main() -> None:
    loc = locale_map()
    mem_ids = memory_ids()
    pages = parse_pages(loc, mem_ids)
    memories = parse_memories(loc, pages)
    memory_by_page = {m["grantPage"]: m for m in memories.values() if m["grantPage"]}
    routes = parse_routes(loc, pages)
    choices = parse_choices(loc, pages, memories)
    first = parse_first(loc, pages, memories)
    hashes = cg_hashes()
    bgs = bg_hashes()

    # 侵蚀度按路线启用：只有存在「选项 -> 侵蚀结局(7xxx)」跳转的路线才计数。
    # 路线1 的 7101 由页面 1209 自动推进触发，不经过侵蚀数值。
    # 页面所属路线取页面表 st+9 字段（11/12/13），不是靠 id 前缀猜的。
    def origin_route(choice: dict) -> int | None:
        pg = pages.get(choice["page"])
        return pg["route"] if pg else None

    erosion_routes = {r["no"] for r in routes if r["no"] and any(
        c["dest"] and 7000 <= c["dest"] < 8000 and origin_route(c) == r["no"]
        for c in choices.values())}
    for r in routes:
        r["erosion"] = r["no"] in erosion_routes

    mgr = parse_manager(loc)
    data = dict(
        version="qa-261123 (client rev 583593) / EventTextAdvPlus",
        event="event_firstaffection",
        title="FADING AFFECTION",
        subtitle="渐逝的爱意",
        status=mgr,
        backgrounds=bgs,
        memories=[memories[k] for k in sorted(memories)],
        memoryByPage={str(k): v for k, v in sorted(memory_by_page.items())},
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
    gated = [c for c in choices.values() if c["req"]]
    broken = [c["id"] for c in gated if c["req"]["kind"] == "memory" and not c["req"]["page"]]
    broken += [c["id"] for c in gated if c["req"]["kind"] == "ending" and c["req"]["page"] not in pages]
    broken += [f["key"] for f in first if f["unlock"] and f["unlock"]["kind"] == "memory"
               and not f["unlock"]["page"]]
    print(f"routes={len(routes)} pages={len(pages)} choices={len(choices)} "
          f"first={len(first)} endings={len(endings)} memories={len(memories)} "
          f"cgHashes={len(data['cgHashes'])} backgrounds={len(bgs)}")
    print(f"gated options={len(gated)} (with hint {sum(1 for c in gated if c['hint'])}) "
          f"gated locations={sum(1 for f in first if f['unlock'])} "
          f"erosion routes={sorted(erosion_routes)} granted pages={len(memory_by_page)}")
    print("manager status: " + " / ".join(
        f"{it['name']} {it['max']},{it['second']} ({it['icon']})" for it in mgr["items"]))
    if broken:
        print(f"!! unresolved conditions: {broken}")
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
    print(f"wrote {web} ({web.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
