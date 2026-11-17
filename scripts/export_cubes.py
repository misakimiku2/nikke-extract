# -*- coding: utf-8 -*-
"""导出魔方（Harmony Cube）数据 → staging/cube_stats.json

数据来源：
  1. staticdata/ItemHarmonyCubeLevelTable.mpk  —— 每级的三围固定加成 / 插槽数
     头部 4B 记录数（270 = 18 魔方 × 15 级），每条 79 字节定长。
     记录头：flag(1B,0x09) + rowid(u32) + cubeId(u32) + level(u32)
     记录尾：3 组 [0x02][key:u32][value:u32]，key 1=ATK 2=HP 3=DEF（全集共通，与魔方种类无关）
     中间：技能 id（7xxxxxx）、升级信用点、插槽数
  2. staticdata/ItemHarmonyCubeTable.mpk + Locale_Item —— 18 个魔方的 id 与中英文名
  3. 各魔方自身的技能效果为社区实测表（nikke.gg / prydwen），
     档位规律：Lv1-2 / Lv3-6 / Lv7-15 三档，分别约为满值的 1/2、3/4、1 倍。
     其中 Vigor(最大HP) 与 Endurance(防御力) 会作用到三围面板，其余为战斗属性。
"""
import json
import pathlib
import sqlite3
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "staticdata"
OUT = ROOT / "staging"
LOCALE_DB = ROOT / "decrypted" / "38af6f4a2a5d25df89b95c0fa5e13006.dec"

# 魔方 id → (本地化 key, 效果名, 单位, 三档数值, 影响的三围字段)
# 三档：Lv1-2 / Lv3-6 / Lv7-15
EFFECTS = {
    1: ("artifact_all_1", "命中率增加", "%", [2.54, 3.81, 5.09], None),
    2: ("artifact_all_2", "蓄力伤害增加", "%", [2.54, 3.81, 5.09], None),
    3: ("artifact_all_3", "装弹速度增加", "%", [14.84, 22.27, 29.69], None),
    4: ("artifact_all_4", "弹药返还", "发", [1, 2, 3], None),
    5: ("artifact_all_5", "蓄力速度增加", "%", [1.06, 1.59, 2.12], None),
    6: ("artifact_all_6", "最大装弹数增加", "%", [14.84, 22.29, 29.69], None),
    7: ("artifact_all_7", "爆裂技能生成增加", "%", [2.33, 3.5, 4.66], None),
    8: ("artifact_all_8", "最大体力增加", "%", [4.84, 7.27, 9.69], "hp"),
    9: ("artifact_all_9", "防御力增加", "%", [24.20, 36.35, 48.45], "def"),
    10: ("artifact_all_10", "HP 恢复量增加", "%", [8.08, 12.12, 16.16], None),
    11: ("artifact_all_11", "受到伤害减少", "%", [4.84, 7.27, 9.69], None),
    12: ("artifact_all_12", "低体力时最大体力增加", "%", [6.07, 9.10, 12.14], None),
    13: ("artifact_all_13", "零件伤害增加", "%", [15.95, 23.92, 31.90], None),
    14: ("artifact_all_14", "穿透伤害增加", "%", [7.07, 10.6, 14.14], None),
    15: ("artifact_all_15", "真实伤害增加", "%", [7.07, 10.6, 14.14], None),
    16: ("artifact_all_16", "掩体最大体力增加", "%", [7.27, 10.9, 14.54], None),
    17: ("artifact_all_17", "分布伤害增加", "%", [8.84, 13.26, 17.69], None),
    18: ("artifact_all_18", "满爆裂时最大体力增加", "%", [4.01, 6.01, 8.02], None),
}

# 所有魔方通用的「优越代码伤害」按等级（Lv1-4 无）
ELEMENTAL = [None, None, None, None, 8.48, 8.48, 8.48, 8.48,
             10.6, 12.72, 14.84, 14.84, 16.96, 16.96, 19.09]

# Locale 库里读不到时的兜底名称
FALLBACK_NAMES = {
    1: ("遗迹突击魔方", "Assault Cube"), 2: ("战术突击魔方", "Onslaught Cube"),
    3: ("遗迹巨熊魔方", "Resilience Cube"), 4: ("战术巨熊魔方", "Bastion Cube"),
    5: ("遗迹促进魔方", "Adjutant Cube"), 6: ("战术促进魔方", "Wingman Cube"),
    7: ("遗迹量子魔方", "Quantum Cube"), 8: ("体力神器魔方", "Vigor Cube"),
    9: ("遗迹强韧魔方", "Endurance Cube"), 10: ("遗迹治疗魔方", "Healing Cube"),
    11: ("遗迹回火魔方", "Tempering Cube"), 12: ("遗迹辅助魔方", "Assist Cube"),
    13: ("遗迹毁灭魔方", "Destruction Cube"), 14: ("遗迹穿透魔方", "Piercing Cube"),
    15: ("遗迹粉碎魔方", "Rupture Cube"), 16: ("遗迹掩体魔方", "Stealth Cube"),
    17: ("遗迹分裂魔方", "Diffusion Cube"), 18: ("遗迹外框魔方", "Bezel Cube"),
}

REC = 79
CUBE_TABLE = STATIC / "ItemHarmonyCubeTable.mpk"


def parse_icon_ids():
    """从 ItemHarmonyCubeTable 取出「序号 → 外观 ID」。

    每条记录：flag(0x0f) + rowid + name + desc + sort + location_key + 序号 + 外观ID
              + 发光键 + 主题色 + ...
    外观 ID 就是图标名 `ie_{id}` 的后半段（同时和记录里的主题色一一对应），
    它并不等于序号 —— 例如 7 号「量子魔方」是 11001，8 号「体力神器」是 13001。
    """
    b = CUBE_TABLE.read_bytes()
    starts = []
    for i in range(len(b) - 9):
        if b[i] != 0x0F:
            continue
        rid = struct.unpack_from("<I", b, i + 1)[0]
        if not (1000300 < rid < 1000400):
            continue
        if struct.unpack_from("<i", b, i + 5)[0] not in (-30, -29, -28, -27, -26, -25):
            continue
        starts.append(i)

    out = {}
    for r in starts:
        off = r + 1
        toks = []
        while off < len(b) - 4:
            tag = struct.unpack_from("<i", b, off)[0]
            if tag < 0:
                ln = struct.unpack_from("<I", b, off + 4)[0]
                if ln > 400:
                    break
                toks.append(b[off + 8:off + 8 + ln].decode("utf-8", "replace"))
                off += 8 + ln
            else:
                toks.append(tag)
                off += 4
            if len(toks) >= 9:
                break
        if len(toks) < 9:
            continue
        ordinal, icon_id, color = toks[5], toks[6], toks[8]
        if isinstance(ordinal, int) and isinstance(icon_id, int) and 1 <= ordinal <= 18:
            out[ordinal] = {"iconId": icon_id, "color": color}
    return out


def parse_levels():
    b = (STATIC / "ItemHarmonyCubeLevelTable.mpk").read_bytes()
    n = struct.unpack_from("<I", b, 0)[0]
    assert n % 15 == 0, n
    rows = []
    for i in range(15):                       # 第一个魔方的 15 级即可，三围加成全集通用
        seg = b[4 + i * REC: 4 + i * REC + REC]
        assert seg[0] == 0x09, (i, seg[0])
        cell = seg[1:13]
        _rowid, _cid, lv = struct.unpack("<3I", cell)
        # 44 = 插槽数（32 处是技能 id，40 处是升级信用点）
        slots = struct.unpack_from("<I", seg, 44)[0]
        # 尾部 3 组 [0x02][key][value]
        vals = {}
        for k in range(3):
            off = REC - 27 + k * 9
            mark, key, value = struct.unpack_from("<BII", seg, off)
            assert mark == 0x02, (i, k, mark)
            vals[key] = value
        rows.append({"lv": lv, "atk": vals[1], "def": vals[3], "hp": vals[2], "slots": slots})
    return rows


def parse_names():
    names = {}
    if LOCALE_DB.exists():
        try:
            c = sqlite3.connect(f"file:{LOCALE_DB}?mode=ro", uri=True)
            for i in range(1, 19):
                r = c.execute(
                    'select "zh-CN","en" from Locale_Item where "Key"=?',
                    (f"artifact_all_{i}",)).fetchone()
                if r and r[0]:
                    names[i] = (r[0], r[1] or "")
        except Exception as e:
            print("  locale 读取失败，用兜底名称:", e)
    for i in range(1, 19):
        names.setdefault(i, FALLBACK_NAMES[i])
    return names


def main():
    levels = parse_levels()
    names = parse_names()
    meta = parse_icon_ids()
    cubes = []
    for i in range(1, 19):
        key, effect, unit, tiers, affects = EFFECTS[i]
        zh, en = names[i]
        info = meta.get(i, {})
        cubes.append({
            "id": 10000 + i,
            "iconId": info.get("iconId", 10000 + i),
            "color": info.get("color", ""),
            "key": key,
            "name": zh,
            "nameEn": en,
            "effect": effect,
            "unit": unit,
            "tiers": tiers,
            "affects": affects,
        })

    data = {
        "levels": levels,
        "cubes": cubes,
        "elemental": ELEMENTAL,
        # 技能档位边界：Lv1-2 / Lv3-6 / Lv7-15
        "tierBounds": [2, 6, 15],
    }
    OUT.mkdir(exist_ok=True)
    dst = OUT / "cube_stats.json"
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"导出 {dst}  ({dst.stat().st_size / 1024:.1f} KB)")
    print("等级  ATK   DEF   HP       插槽")
    for r in levels:
        print(f"  Lv{r['lv']:<2d} {r['atk']:>5d} {r['def']:>5d} {r['hp']:>7,d}   {r['slots']}")
    print("魔方：")
    for c in cubes:
        print(f"  {c['id']} icon={c['iconId']} {c['color']} {c['name']:8s} {c['nameEn']:18s} {c['effect']} "
              f"{c['tiers'][0]}/{c['tiers'][1]}/{c['tiers'][2]}{c['unit']}"
              f"{'  ← 计入三围(' + c['affects'] + ')' if c['affects'] else ''}")


if __name__ == "__main__":
    main()
