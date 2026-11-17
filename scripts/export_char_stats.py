"""导出妮姬角色基础属性（HP / ATK / DEF）到 staging/。

数据源（全部来自本机 staticdata/，无需联网）：
  CharacterTable.mpk      每个角色的稀有度、职业、武器 -> 模板键
  CharacterStatTable.mpk  54 个模板 × 1400 级的 HP/ATK/DEF 曲线

模板键编码：稀有度(1=R 3=SR 5=SSR) ×1000 + 职业(1=火力 2=防御 3=辅助) ×100 + 武器(1..6)
  武器 1=ar 2=sr 3=smg 4=sg 5=rl 6=mg

用法：
  python scripts/export_char_stats.py
  python scripts/export_char_stats.py --levels 1,200,400,600
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import struct
from collections import Counter

BASE = pathlib.Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
STAGING = BASE / "staging"
WEB_DATA = pathlib.Path(r"E:\test\nikke-web\public\data")

RARITY = {1: "R", 2: "SR", 3: "SSR"}
CLASS_CN = {1: "火力型", 2: "防御型", 3: "辅助型"}
WEAPON = {1: "ar", 2: "sr", 3: "smg", 4: "sg", 5: "rl", 6: "mg"}

NAME_RE = re.compile(rb"Locale_Character:(\d+)_name")
CV_RE = re.compile(rb"Locale_Character:(\d+)_cv")


# ---------- CharacterTable ----------
def parse_character_table() -> dict[int, dict]:
    b = (STATIC / "CharacterTable.mpk").read_bytes()

    names = []
    for m in NAME_RE.finditer(b):
        tag_off = m.start() - 8
        if tag_off < 0:
            continue
        tag = struct.unpack_from("<i", b, tag_off)[0]
        if tag in (-25, -26):                      # 旧/新 schema
            names.append((tag_off, m.end(), int(m.group(1))))

    cvs = []
    for m in CV_RE.finditer(b):
        tag_off = m.start() - 8
        if tag_off < 0:
            continue
        tag = struct.unpack_from("<i", b, tag_off)[0]
        if tag in (-23, -24):
            cvs.append((tag_off, int(m.group(1))))

    out: dict[int, dict] = {}
    for i, (ns, ne, cid) in enumerate(names):
        nxt = names[i + 1][0] if i + 1 < len(names) else len(b)
        cand = [c for c in cvs if ns < c[0] < nxt and c[1] == cid]
        if not cand:
            continue
        cs, _ = cand[0]

        chunk = b[ne:cs]
        vals, off = [], 0
        while off + 4 <= len(chunk):
            v = struct.unpack_from("<i", chunk, off)[0]
            off += 4
            if v < 0:                              # 负 tag = 字符串字段，跳过
                ln = struct.unpack_from("<I", chunk, off)[0]
                off += 4 + ln
                continue
            vals.append(v)
        if len(vals) != 32:
            continue

        tmpl = vals[7]
        if cid in out:                             # 只保留变体 1
            continue
        out[cid] = {
            "template": tmpl,
            "rarity": RARITY.get(vals[4], "?"),
            "cls": tmpl // 100 % 10,
            "weapon": WEAPON.get(tmpl % 100, "?"),
        }
    return out


# ---------- CharacterStatTable ----------
def parse_stat_table() -> dict[int, dict[int, tuple[int, int, int]]]:
    """template -> level -> (hp, atk, def)"""
    b = (STATIC / "CharacterStatTable.mpk").read_bytes()
    n = struct.unpack_from("<I", b, 0)[0]
    rec_size = (len(b) - 4) // n
    assert 4 + n * rec_size == len(b), "记录长度不是整数"

    curves: dict[int, dict[int, tuple[int, int, int]]] = {}
    for i in range(n):
        off = 4 + i * rec_size
        vals = struct.unpack_from("<10i", b, off + 1)
        tmpl, lv = vals[1], vals[2]
        curves.setdefault(tmpl, {})[lv] = (vals[3], vals[5], vals[6])
    return curves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="", help="CSV 里输出的等级，逗号分隔")
    ap.add_argument("--max-level", type=int, default=1400)
    args = ap.parse_args()

    chars = parse_character_table()
    curves = parse_stat_table()
    print(f"characters: {len(chars)}   templates: {len(curves)}")

    names = {}
    meta_path = WEB_DATA / "characters.json"
    if meta_path.exists():
        for it in json.loads(meta_path.read_text(encoding="utf-8"))["items"]:
            names[it["id"]] = it
    meta = {}
    mp = WEB_DATA / "char_meta.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))

    # 按 max_level 裁剪曲线
    trimmed = {
        t: {lv: v for lv, v in c.items() if lv <= args.max_level}
        for t, c in curves.items()
    }

    missing_tmpl = sorted({c["template"] for c in chars.values()} - set(curves))
    print("templates missing curve:", missing_tmpl)

    STAGING.mkdir(parents=True, exist_ok=True)

    # 1) 完整曲线（前端按等级查表）
    curves_out = {
        str(t): {
            "hp": [c[lv][0] for lv in sorted(c)],
            "atk": [c[lv][1] for lv in sorted(c)],
            "def": [c[lv][2] for lv in sorted(c)],
        }
        for t, c in sorted(trimmed.items())
    }
    (STAGING / "stat_curves.json").write_text(
        json.dumps(curves_out, separators=(",", ":")), encoding="utf-8"
    )

    # 2) 角色汇总
    levels = [1, 40, 80, 120, 160, 200, 240, 280, 300, 400, 500, 600, 800, 1000, 1200, 1400]
    chars_out = {}
    for cid, c in sorted(chars.items()):
        curve = trimmed.get(c["template"], {})
        n = names.get(cid, {})
        m = meta.get(str(cid), {})
        entry = {
            "id": cid,
            "name": n.get("name"),
            "nameEn": (n.get("names") or {}).get("en"),
            "code": n.get("code"),
            "template": c["template"],
            "rarity": c["rarity"],
            "cls": c["cls"],
            "clsName": CLASS_CN.get(c["cls"]),
            "weapon": c["weapon"],
            "burst": m.get("burst"),
            "element": m.get("element"),
            "squad": m.get("squad"),
            "stats": {},
        }
        for lv in levels:
            if lv in curve:
                hp, atk, dfn = curve[lv]
                entry["stats"][str(lv)] = {"hp": hp, "atk": atk, "def": dfn}
        chars_out[str(cid)] = entry
    (STAGING / "char_stats.json").write_text(
        json.dumps(chars_out, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # 3) CSV
    lv_list = [int(x) for x in args.levels.split(",") if x.strip()] or levels
    csv_path = STAGING / "char_stats.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        head = ["id", "code", "name", "rarity", "class", "weapon", "template"]
        for lv in lv_list:
            head += [f"L{lv}_hp", f"L{lv}_atk", f"L{lv}_def"]
        w.writerow(head)
        for cid, e in chars_out.items():
            row = [e["id"], e["code"], e["name"], e["rarity"], e["clsName"], e["weapon"], e["template"]]
            for lv in lv_list:
                s = e["stats"].get(str(lv))
                row += [s["hp"], s["atk"], s["def"]] if s else ["", "", ""]
            w.writerow(row)

    print("rarity:", Counter(c["rarity"] for c in chars.values()))
    print("wrote:")
    for p in (STAGING / "stat_curves.json", STAGING / "char_stats.json", csv_path):
        print(f"  {p}  {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
