#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成主线剧情 group_key -> 游戏内真实小节名（含 A/B 后缀，四语）。

数据源（全部本地）：
  staticdata/MainQuestTable.mpk      stage id -> main_quest_description_localkey_N
  staticdata/CampaignStageTable.mpk  stage id -> 剧情 group 列表（d_main_NN_MM[_s/_e]）
  staticdata/AlbumResourceTable.mpk  【权威】description_localkey_N -> group（游戏章节列表用这张表）
  decrypted/Locale_MainQuest         description_localkey_N -> 小节名（zh-CN/en/ko/ja）

AlbumResourceTable 是游戏内章节列表的权威映射，直接把节名 localkey 关联到 group，
且自带 _a/_b 后缀（A/B 分支）。MainQuestTable 的 desc 编号在后期会错位
（如 desc47「小小的报复」被写成 desc470「深渊碎片」），因此 Album 必须覆盖上去。
A/B 后缀：一个 stage 含 _s/_e 两个 group 时，对应游戏里的 A / B 两个分支。

输出：build/main_section_names.json（由调用方指定 --out）
格式：group_key -> {"zh": ..., "en": ..., "ko": ..., "ja": ...}；缺语言缺省为空串。
"""
import argparse, json, os, re, sqlite3, struct, sys
from collections import OrderedDict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(BASE, "staticdata")


def find_dec(parent):
    for f in os.listdir(parent):
        if not f.endswith(".dec"):
            continue
        p = os.path.join(parent, f)
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            if "Locale_MainQuest" in [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]:
                con.close()
                return p
        except Exception:
            pass
    return None


def u32_range(raw, lo, hi):
    return sorted((i, struct.unpack_from("<I", raw, i)[0])
                  for i in range(0, len(raw) - 4)
                  if lo <= struct.unpack_from("<I", raw, i)[0] < hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    # stage -> desc 编号
    raw = open(os.path.join(STATIC, "MainQuestTable.mpk"), "rb").read()
    cands = u32_range(raw, 6_000_000, 6_200_000)
    stage_desc = {}
    for k, (o, v) in enumerate(cands):
        end = cands[k + 1][0] if k + 1 < len(cands) else len(raw)
        m = re.search(rb"main_quest_description_localkey_(\d+)",
                      raw[o:min(end, o + 300)])
        if m:
            stage_desc[v] = int(m.group(1))

    # stage -> group 列表
    raw2 = open(os.path.join(STATIC, "CampaignStageTable.mpk"), "rb").read()
    toks = [(m.start(), m.group().decode("ascii", "replace"))
            for m in re.finditer(rb"[ -~]{4,}", raw2)]
    sm = [(o, t) for o, t in toks if re.match(r"^Locale_Stage:\d+_name$", t)]
    stage_groups = OrderedDict()
    for k, (o, name) in enumerate(sm):
        end = sm[k + 1][0] if k + 1 < len(sm) else len(raw2)
        sid = int(re.search(r"\d+", name).group())
        grps = [m.group().decode() for m in re.finditer(
            rb"d_main_\d+(?:_?[a-z]+)?_?\d+(?:_[se])?", raw2[o:end])]
        if grps:
            stage_groups[sid] = grps

    # desc 名（四语：zh-CN / en / ko / ja；Locale_MainQuest 同表带全部语言列）
    dec = find_dec(os.path.join(BASE, "decrypted"))
    con = sqlite3.connect(f"file:{dec}?mode=ro", uri=True)
    desc = {}
    desc_full = {}
    for k, zh, en, ko, ja in con.execute(
            'SELECT "Key","zh-CN",en,ko,ja FROM Locale_MainQuest'):
        if not zh:
            continue
        langs = {"zh": zh.strip(), "en": (en or "").strip(),
                 "ko": (ko or "").strip(), "ja": (ja or "").strip()}
        m = re.search(r"main_quest_description_localkey_(\d+)$", k)
        if m:
            desc[int(m.group(1))] = langs
        # 保留完整 key（含 _a/_b 后缀），Album 表用这种格式
        if "main_quest_description_localkey_" in k:
            desc_full[k.split(":", 1)[-1]] = langs
    con.close()

    name_map = {}
    for sid, grps in stage_groups.items():
        dn = stage_desc.get(sid)
        if not dn or dn not in desc:
            continue
        title = desc[dn]
        if len(grps) == 1:
            name_map[grps[0]] = title
        else:
            labels = ["A", "B", "C"][:len(grps)]
            for g, lab in zip(grps, labels):
                name_map[g] = {lang: f"{t}: {lab}" if t else ""
                               for lang, t in title.items()}

    # 后记段（d_main_NNaf_MM 等）不在 CampaignStageTable 里，但 MainQuestTable
    # 的 quest 记录里直接带着 group 名：desc42「判决」-> d_main_04af_01。
    # 以 description token 为锚点扫出这些直接引用。
    desc_marks = sorted((m.start(), int(m.group(1)), m.end())
                        for m in re.finditer(
                            rb"Locale_MainQuest:main_quest_description_localkey_(\d+)", raw))
    for i, (pos, dn, _end) in enumerate(desc_marks):
        if dn not in desc:
            continue
        stop = desc_marks[i + 1][0] if i + 1 < len(desc_marks) else pos + 1200
        seg = raw[pos:min(stop, pos + 1200)]
        # 后记段两种命名都存在：d_main_04af_01（无下划线）和 d_main_46_af_01（有下划线）
        grps = [m.group().decode() for m in re.finditer(
            rb"d_main_\d+(?:_?[a-z]+)?_?\d+(?:_[se])?", seg)]
        for g in grps:
            # 后记段用纯节名（不加 A/B 后缀）
            name_map.setdefault(g, desc[dn])

    # AlbumResourceTable 是游戏章节列表的权威来源：直接给出
    # description_localkey_<N>[_a/_b] -> d_main group 的对应关系。
    # 用它覆盖上面两种启发式解析的结果，修正 desc 编号错位导致的错名
    # （如 d_main_04af_06 曾被误配成「深渊碎片」，实为「小小的报复」）。
    album_raw = open(os.path.join(STATIC, "AlbumResourceTable.mpk"), "rb").read()
    atoks = [(m.start(), m.group().decode("ascii", "replace"))
             for m in re.finditer(rb"[ -~]{4,}", album_raw)]
    for i, (o, t) in enumerate(atoks):
        m = re.match(r"^Locale_MainQuest:(main_quest_description_localkey_\w+)$", t)
        if not m or m.group(1) not in desc_full:
            continue
        for _o2, t2 in atoks[i + 1:i + 4]:
            gm = re.match(r"^(d_main_\w+)$", t2)
            if gm:
                # Album 里的键已含 A/B 译名（如「第一次接触：A」），直接采用
                name_map[gm.group(1)] = desc_full[m.group(1)]
                break

    out = a.out or os.path.join(BASE, "..", "nikke-web", "build",
                                "main_section_names.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(name_map, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"生成 {len(name_map)} 条小节名 -> {out}")


if __name__ == "__main__":
    main()
