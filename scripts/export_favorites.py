# -*- coding: utf-8 -*-
"""导出珍藏品（Favorite Item / 收集品娃娃）数据 → staging/favorite_stats.json

数据来源：
  1. staticdata/FavoriteItemTable.mpk —— 12 个珍藏品本体（6 职业 × R/SR 限量版）
     变长记录：flag(0x11) + rowid(u32) + 若干 [负tag][u32长度][utf8字符串] + int token
     主记录由 `favoriteitem_collection_<cls>_<0|1>` 名称 key 标识：
       <cls> ∈ ar(步枪) / mg(机枪) / rl(发射器) / sg(霰弹) / smg(冲锋) / sr(狙击)
       _00 = R 版，_01 = SR 限量版
     rowid 形如 100101 / 100102 / ...，同时是等级表的关联键（fid）。
  2. staticdata/FavoriteItemLevelTable.mpk —— 每级三围
     定长 62B × 255 条，tag-value 混合编码。每条记录：
       u32@1  = rowid（前几位=珍藏品序号，后两位=等级；16 个职业款各 16 级 0-15）
       u32@5  = 本体表 rowid（fid，用于关联，如 100101）
       u32@13 = 等级 phase（0-15）
       u32@26 = ATK, u32@35 = DEF, u32@44 = HP
     数值经社区数据（nikke.gg / gamekee）交叉验证：
       R 满级 147250/4736/1002，SR 满级 301800/9688/2058。
  3. Locale_Item 库取中英文名。

注意：本表只提供三围（HP/ATK/DEF）；珍藏品的百分比技能效果（防御+37%、
受伤-17%、掩体HP+30% 等）随职业与阶段变化，是战斗属性，不进入三围面板，
前端按职业常量单独展示，不写入本 JSON。
"""
import json
import pathlib
import re
import sqlite3
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "staticdata"
OUT = ROOT / "staging"
DEC = ROOT / "decrypted"

# 职业缩写 → 中文武器名（与 data.ts 的 SPEC_WEAPON 一致）
CLS_CN = {
    "ar": "步枪", "mg": "机枪", "rl": "发射器",
    "sg": "霰弹枪", "smg": "冲锋枪", "sr": "狙击步枪",
}
# 职业 → 图标 si_favoriteitem_<cls>_00
ICON_BY_CLS = {
    "ar": "si_favoriteitem_ar_00", "mg": "si_favoriteitem_mg_00",
    "rl": "si_favoriteitem_rl_00", "sg": "si_favoriteitem_sg_00",
    "smg": "si_favoriteitem_smg_00", "sr": "si_favoriteitem_sr_00",
}

# 本体表字符串字段 tag（负）→ 语义
T_NAME = -42    # Locale_Item:<key> 名称
T_DESC = -47    # Locale_Item:<key>_desc 描述
T_SI = -22      # si_favoriteitem_xx 图标 key
T_PROP = -28    # favoriteitem_common_prop_xx


def parse_items():
    """解析本体表，返回 fid → {key, cls, rare, desc_key} 的主记录。"""
    b = (STATIC / "FavoriteItemTable.mpk").read_bytes()
    out = {}
    # 主记录特征：flag 0x11 + rowid(100000-200000) + 名称 key 含 favoriteitem_collection
    for i in range(4, len(b) - 5):
        if b[i] != 0x11:
            continue
        rid = struct.unpack_from("<I", b, i + 1)[0]
        if not (100000 < rid < 200000):
            continue
        # 名称是第一条字符串字段：tag @i+5, len @i+9, utf8 @i+13
        # tag 大多是 -42，SMG 两条是 -43，故不校验 tag，靠名称 key 前缀判定
        tag = struct.unpack_from("<i", b, i + 5)[0]
        ln = struct.unpack_from("<I", b, i + 9)[0]
        if not (0 < ln < 300):
            continue
        name_key = b[i + 13:i + 13 + ln].decode("utf-8", "replace")
        # name_key 形如 Locale_Item:favoriteitem_collection_ar_00
        prefix = "Locale_Item:favoriteitem_collection_"
        if not name_key.startswith(prefix):
            continue
        tail = name_key[len(prefix):]
        parts = tail.split("_")
        if len(parts) != 2 or not parts[0].isalpha() or parts[1] not in ("00", "01"):
            continue
        cls, rare = parts[0], int(parts[1])
        key = f"favoriteitem_collection_{cls}_{rare:02d}"
        # 顺序解析后续字符串字段，取 _desc 描述 key
        desc_key = ""
        p = i + 13 + ln
        for _ in range(8):
            if p + 8 > len(b):
                break
            t = struct.unpack_from("<i", b, p)[0]
            if t >= 0:
                p += 4
                continue
            ln2 = struct.unpack_from("<I", b, p + 4)[0]
            if not (0 < ln2 < 300):
                break
            s = b[p + 8:p + 8 + ln2].decode("utf-8", "replace")
            if s.endswith("_desc"):
                desc_key = s
                break
            p += 8 + ln2
        out[rid] = {
            "id": rid, "key": key, "cls": cls, "rare": rare,
            "nameKey": name_key, "descKey": desc_key,
            "icon": ICON_BY_CLS.get(cls, ""),
            "weapon": CLS_CN.get(cls, cls),
        }
    return out


def parse_levels(items):
    """解析等级表，给每个本体记录挂 16 级三围。"""
    b = (STATIC / "FavoriteItemLevelTable.mpk").read_bytes()
    n = struct.unpack_from("<I", b, 0)[0]
    REC = 62
    assert n * REC + 4 == len(b), (n, len(b))
    levels = {fid: {} for fid in items}
    for i in range(n):
        seg = b[4 + i * REC:4 + (i + 1) * REC]
        fid = struct.unpack_from("<I", seg, 5)[0]
        if fid not in levels:
            continue
        phase = struct.unpack_from("<I", seg, 13)[0]
        if not (0 <= phase <= 15):
            continue
        atk = struct.unpack_from("<I", seg, 26)[0]
        dfn = struct.unpack_from("<I", seg, 35)[0]
        hp = struct.unpack_from("<I", seg, 44)[0]
        levels[fid][phase] = {"lv": phase, "atk": atk, "def": dfn, "hp": hp}
    return levels


def parse_names():
    names = {}
    for path in sorted(DEC.glob("*.dec")):
        try:
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            if "Locale_Item" not in {r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}:
                c.close()
                continue
            for fid_key in c.execute(
                "select \"Key\",\"zh-CN\",\"en\" from Locale_Item where \"Key\" like 'favoriteitem_collection_%'"
            ).fetchall():
                k, zh, en = fid_key
                names[k] = (zh or "", en or "")
            c.close()
        except sqlite3.Error:
            continue
    return names


def main():
    items = parse_items()
    levels = parse_levels(items)
    names = parse_names()
    out = []
    for fid, info in sorted(items.items()):
        name_key = info["nameKey"].split(":", 1)[-1]
        zh, en = names.get(name_key, (name_key, ""))
        desc_key = info["descKey"].split(":", 1)[-1] if info["descKey"] else ""
        desc_zh = names.get(desc_key, ("", ""))[0]
        lv_rows = [levels[fid][p] for p in range(16) if p in levels[fid]]
        out.append({
            "id": fid,
            "key": info["key"],
            "cls": info["cls"],
            "weapon": info["weapon"],
            "rare": "SR" if info["rare"] else "R",
            "name": zh, "nameEn": en,
            "desc": desc_zh,
            "icon": info["icon"],
            "levels": lv_rows,
        })

    OUT.mkdir(exist_ok=True)
    dst = OUT / "favorite_stats.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"导出 {dst} ({dst.stat().st_size / 1024:.1f} KB)  共 {len(out)} 个珍藏品")
    for f in out:
        mx = f["levels"][-1] if f["levels"] else {}
        print(f"  {f['id']} {f['rare']:2s} {f['weapon']:4s} {f['name']:16s} "
              f"Lv15: HP={mx.get('hp', 0):>7,} ATK={mx.get('atk', 0):>5,} DEF={mx.get('def', 0):>5,} "
              f"({len(f['levels'])} 级)")


if __name__ == "__main__":
    main()
