"""导出妮姬装备基础属性（部位 × 职业 × 品阶）。

数据源：staticdata/ItemEquipTable.mpk

记录结构（逆向结论）：
  icon 字符串之后是 7 个 int32 头字段，随后是 [count][0x02 key value]×count
  头字段：[1]=部位(1头 2身 3臂 4腿) [3]=品阶(2/4/6/8/9/10)
  属性键：1=ATK 2=HP 3=DEF
  企业专属装(T9M)把数值写成 999999/99999999 占位，直接跳过

用法：python scripts/export_equip.py
输出：staging/equip_stats.json
"""
from __future__ import annotations

import json
import pathlib
import re
import struct

BASE = pathlib.Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
STAGING = BASE / "staging"

PART = {1: "head", 2: "body", 3: "arm", 4: "leg"}
CLS = {"attacker": 1, "defender": 2, "supporter": 3}
ATTR = {1: "atk", 2: "hp", 3: "def"}
ICON = re.compile(rb"icn_equipment_([a-z_0-9]+)")
NAME = re.compile(r"(head|body|arm|leg)_(attacker|defender|supporter)_t(\d+)")


def parse_pairs(seg: bytes):
    if len(seg) < 28:
        return None, []
    head = list(struct.unpack_from("<7i", seg, 0))
    off, pairs = 28, []
    for _ in range(head[6]):
        if off >= len(seg) or seg[off] != 0x02:
            break
        k, v = struct.unpack_from("<2i", seg, off + 1)
        pairs.append((k, v))
        off += 9
    return head, pairs


def main():
    b = (STATIC / "ItemEquipTable.mpk").read_bytes()
    ms = list(ICON.finditer(b))

    rows = {}
    skipped = 0
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(b)
        seg = b[m.end():end]
        head, pairs = parse_pairs(seg)
        if not head:
            continue
        icon = m.group(1).decode()
        mm = NAME.match(icon)
        if not mm:
            continue
        part, cls_s, _tag = mm.groups()
        part_id, tier = head[1], head[3]
        if PART.get(part_id) != part:
            continue
        # 企业装占位
        if any(v >= 999999 for _, v in pairs):
            skipped += 1
            continue
        stats = {"atk": 0, "hp": 0, "def": 0}
        for k, v in pairs:
            if k in ATTR:
                stats[ATTR[k]] = v
        key = (part, CLS[cls_s], tier)
        # 同一组合若有多条，取数值更大的（T9 普通 vs 企业变体）
        if key in rows and sum(rows[key].values()) >= sum(stats.values()):
            continue
        rows[key] = stats

    out = []
    for (part, cls, tier), st in sorted(rows.items()):
        out.append({"part": part, "cls": cls, "tier": tier, **st})

    tiers = sorted({r["tier"] for r in out})
    cls_set = sorted({r["cls"] for r in out})
    parts = sorted({r["part"] for r in out})
    print(f"records: {len(out)}  parts={parts} cls={cls_set} tiers={tiers}  skippedT9M={skipped}")

    STAGING.mkdir(parents=True, exist_ok=True)
    (STAGING / "equip_stats.json").write_text(
        json.dumps({"items": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 抽查 T10
    for r in out:
        if r["tier"] == 10 and r["cls"] == 1:
            print("  T10 attacker", r)


if __name__ == "__main__":
    main()
