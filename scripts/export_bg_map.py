"""Build the dynamic-CG <-> background mapping (CG索引/动态CG背景对照.csv/json).

Spine 动态 CG 的背景有三种来源，按优先级整理成一张对照表：
  1. X_bg 背景板 —— 库里有 `EventScene_X_bg.png`，命名约定即配对
  2. 剧情背景证据 —— 剧情 JSON 行级 (cgd, cgb) 组合（剧情表里 CG token 与
     背景 token 同记录出现，bg 随记录持续）
  3. 模型自带 bg region —— atlas 里有 bg_* / *_bg / background 区域，模型自包含
其余为「无背景证据」：多为动态壁纸（LiveWallpaperTable）与角色剧情演出模型
（ScenarioCharacterSettingTable 按角色触发），剧情表不引用，阅读器铺透明底即可。

输出列：
  动态CG, 自带bg, 背景板, 剧情背景, 建议背景, 用途, 背景板文件
  * 建议背景 = 背景板 > 剧情背景 > （自带bg 时留空=模型自包含）> 空=铺透明底
  * 用途 = wallpaper（图鉴/动态壁纸）/ episode（角色演出）/ story（剧情表触发）
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cg_refs

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "CG索引"
STATIC = BASE / "staticdata"

TOKEN = re.compile(rb"[ -~]{4,}")
REGION = re.compile(r"^[A-Za-z0-9_]+$")


def atlas_has_bg(atlas: Path) -> bool:
    try:
        txt = atlas.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in txt.splitlines():
        s = line.strip().lower()
        if REGION.fullmatch(s or "") and (
                s == "bg" or s.startswith("bg_") or s.endswith("_bg")
                or "background" in s):
            return True
    return False


def table_refs(name: str) -> set[str]:
    """指定 mpk 里出现的 EventScene_* 名集合。"""
    p = STATIC / name
    if not p.exists():
        return set()
    return {m.group().decode() for m in re.finditer(rb"EventScene_[A-Za-z0-9_]+",
                                                    p.read_bytes())}


def main() -> None:
    static_cg, dynamic_cg = cg_refs.load_cg_library()
    spine = sorted(a.stem for a in (BASE / "CG").rglob("*.atlas"))
    wallpaper_refs = table_refs("LiveWallpaperTable.mpk")
    episode_refs = table_refs("ScenarioCharacterSettingTable.mpk")

    # 剧情 JSON 里的 (cgd, cgb) 组合
    story_pairs: dict[str, set[str]] = defaultdict(set)
    story_uses: Counter = Counter()

    def eat(lines):
        for l in lines:
            if l.get("cgd"):
                story_uses[l["cgd"]] += 1
                if l.get("cgb"):
                    story_pairs[l["cgd"]].add(l["cgb"])

    main = json.loads((BASE / "主线剧情" / "主线剧情_全量.json").read_text(encoding="utf-8"))
    for ch in main.get("chapters", []):
        for sec in ch.get("sections", []):
            eat(sec.get("lines") or [])
    marian = BASE / "其他剧情" / "活动剧情" / "Marian" / "event_marian_结构化.json"
    if marian.exists():
        for ch in json.loads(marian.read_text(encoding="utf-8")).get("chapters", []):
            eat(ch.get("lines") or [])
    for cat in ["活动剧情", "妮姬个人剧情", "咨询对话", "支线剧情",
                "外传与前哨基地日常", "支线故事", "短信与日常对话", "补充剧情文本"]:
        p = BASE / "其他剧情" / cat / f"{cat}_全量.json"
        if not p.exists():
            continue
        for u in json.loads(p.read_text(encoding="utf-8")):
            for g in u.get("groups") or []:
                eat(g.get("lines") or [])

    rows = []
    for name in spine:
        atlas = next((BASE / "CG").rglob(f"{name}.atlas"))
        has_self_bg = atlas_has_bg(atlas)
        board = f"{name}_bg"
        board_file = static_cg.get(board.lower(), "")
        evidence = sorted(story_pairs.get(name, ()))
        if board_file:
            suggest = board
        elif evidence:
            suggest = evidence[0]
        elif has_self_bg:
            suggest = ""
        else:
            suggest = ""
        use = []
        if story_uses.get(name):
            use.append("story")
        if name in wallpaper_refs:
            use.append("wallpaper")
        if name in episode_refs:
            use.append("episode")
        rows.append({
            "动态CG": name,
            "自带bg": "√" if has_self_bg else "",
            "背景板": board if board_file else "",
            "剧情背景": "；".join(evidence),
            "建议背景": suggest,
            "用途": "+".join(use) or "-",
            "剧情引用行数": story_uses.get(name, 0),
            "背景板文件": board_file,
        })

    OUT.mkdir(exist_ok=True)
    cols = ["动态CG", "自带bg", "背景板", "剧情背景", "建议背景", "用途", "剧情引用行数", "背景板文件"]
    with (OUT / "动态CG背景对照.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    (OUT / "动态CG背景对照.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    n_self = sum(1 for r in rows if r["自带bg"])
    n_board = sum(1 for r in rows if r["背景板"])
    n_story = sum(1 for r in rows if r["剧情背景"])
    n_none = sum(1 for r in rows if not r["自带bg"] and not r["背景板"] and not r["剧情背景"])
    print(f"动态 CG {len(rows)}：自带bg {n_self} / X_bg板 {n_board} / 剧情bg证据 {n_story} / 无任何背景 {n_none}")
    for r in rows:
        if not r["自带bg"] and not r["背景板"] and not r["剧情背景"]:
            print("  无背景:", r["动态CG"], f"({r['用途']})")
    print("written", OUT / "动态CG背景对照.csv")


if __name__ == "__main__":
    main()
