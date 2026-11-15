"""Export NIKKE "burst skill cut-in" Spine scenes as composed 2048px stills.

The cut-ins live inside `livewallpaperprefabs_assets_livewallpaper/eventscene_c*_cutscene_*.bundle`
(core pool). Each bundle carries:
  TextAsset  <name>.atlas / <name>.skel
  Texture2D  <name>            the atlas sheet (parts laid out, not a picture)

So they can't be exported like a normal CG texture — they have to be rendered
through the same Spine runtime used for the story dynamic CGs.

  python scripts/export_char_cutins.py --limit 5      # 试跑
  python scripts/export_char_cutins.py                # 全量

Output: staging/spine_char/<name>/  (atlas/skel/sheet)
        CG/04_角色过场/EventScene_<name>.png  (rendered still)
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import sqlite3
import subprocess
import sys
import time

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2

BASE = pathlib.Path(__file__).resolve().parents[1]
STAGING = BASE / "staging" / "spine_char"
OUT_DIR = BASE / "CG" / "04_角色过场"
RUNTIME = BASE / "动态CG" / "runtime"
SIZE = 2048


def text_bytes(obj):
    s = obj.read().m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    return bytes(s or b"")


def cutin_bundles(cat):
    rows = cat.execute(
        "select file_id, key from files_chunktype"
        " where lower(key) like '%livewallpaperprefabs%cutscene%'"
    ).fetchall()
    def quality(key):
        return 0 if "(hd)" in key.lower() else 1
    rows.sort(key=lambda r: (quality(r[1]), r[0]))
    return rows


BG_EXCLUDE = re.compile(
    r"mask|uv|pattern|ptc|trail|ani|blur|remap|dis|water|smoke|gra|solid|part"
    r"|wind|flash|line|light|impact|noise|cloud|shape|ball|lens|frame|hud", re.I)

# 启发式抽出来但人工判定不适合当背景的（联络表核过）：
#   c441 是黑角 FX 遮罩、c223_01 是 128² 近纯黑
BG_SKIP = {"c441_00_skillcut", "c223_01_skillcut"}
# 2×2 图集（白天/黑夜/剪影/裂痕），取左上白天象限
BG_CROP = {"c851_00_skillut": (0, 0, 512, 512)}

# 启发式漏掉的「场景背景」：名字不带 bg 的整幅场景图，人工指定贴图与裁剪框。
#   c352_02（海伦·浴后）：大招是泡澡演出，模型本身不画躯干（游戏里被水面/水花
#   粒子盖住），必须把浴缸场景垫在底下画面才成立。fx 图集上半是两个场景变体，
#   取右上的亮色版（激溅水花态）。
# 值支持两种形式：单个 (贴图, 裁剪框) 或 [(贴图, 裁剪框), ...] —— 后者按顺序
# 存成 bg.png / bg2.png（多镜切换的大招每个镜头一张场景图，网页按时间切换）。
BG_SCENE_OVERRIDE = {
    "c352_02_skillcut": [
        ("fx_c352_02_cut_scene_atlas_01", (0, 0, 512, 512)),     # 第一镜：海景窗全景（透视）
        ("fx_c352_02_cut_scene_atlas_01", (512, 0, 1024, 512)),  # 第二镜：木地板近景
    ],
}


def pick_bg_texture(textures, base):
    """从 bundle 里挑一张可用的背景贴图。

    游戏里大招的背景有的是独立手绘场景（c010_bg / c131_bg_01），有的是
    Unity 粒子+渐变板拼的（复现不了）。这里只认「名字以 bg 段结尾、属于本
    家族、接近不透明」的贴图——FX 图集透明区多，会被不透明度阈值挡掉。
    """
    fam = re.match(r"^(c\d+)", base)
    fam = fam.group(1) if fam else base.split("_")[0]
    cands = []
    for name, obj in textures:
        if not re.search(r"(^|_)bg(_?\d+)?$", name, re.I):
            continue
        if BG_EXCLUDE.search(name):
            continue
        if not (name == f"{fam}_bg" or name.startswith((f"{fam}_", f"fx_{fam}_"))):
            continue
        try:
            img = obj.read().image
        except Exception:
            continue
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        hist = img.getchannel("A").histogram()
        opaque = sum(hist[250:]) / (img.width * img.height)
        if opaque < 0.9:
            continue
        cands.append((name.startswith("fx_"), not name == f"{fam}_bg", -img.width * img.height, name, img))
    if not cands:
        return None
    cands.sort(key=lambda c: c[:4])
    return cands[0][3], cands[0][4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（试跑用）")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()

    STAGING.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cat = sqlite3.connect(v2.manifest_path("core"))
    table = v2.cidx_map("core")
    cdb = v2.ROOT / "core" / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    dec = zstd.ZstdDecompressor()

    rows = cutin_bundles(cat)
    if args.limit:
        rows = rows[:args.limit]
    print(f"cut-in bundles: {len(rows)}", flush=True)

    stats = {"exported": 0, "rendered": 0, "render_fail": 0, "bgs": 0,
             "no_atlas": 0, "no_skel": 0, "incomplete": 0, "fail": 0}
    started = time.time()
    for n, (fid, key) in enumerate(rows, 1):
        bundle, _parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
        if missing or not bundle or not bundle.startswith(b"UnityFS"):
            stats["incomplete"] += 1
            continue
        try:
            env = UnityPy.load(io.BytesIO(bundle))
            objects = list(env.objects)
        except Exception:
            stats["fail"] += 1
            continue

        assets, textures = {}, []
        for o in objects:
            try:
                name = str(getattr(o.read(), "m_Name", "") or "")
            except Exception:
                continue
            if o.type.name == "TextAsset" and name.endswith((".atlas", ".skel")):
                assets[name] = o
            elif o.type.name == "Texture2D":
                textures.append((name, o))

        atlases = [k for k in assets if k.endswith(".atlas")]
        if not atlases:
            stats["no_atlas"] += 1
            continue
        base = atlases[0][:-len(".atlas")]
        if base + ".skel" not in assets:
            stats["no_skel"] += 1
            continue

        folder = STAGING / re.sub(r"[^\w.-]+", "_", base)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (base + ".atlas")).write_bytes(text_bytes(assets[base + ".atlas"]))
        (folder / (base + ".skel")).write_bytes(text_bytes(assets[base + ".skel"]))

        sheet = folder / (base + ".png")
        # 图集可能有多页：<base>.png 与 <base>_2.png（特效/武器第二页），都要存
        pages = [(nm, o) for nm, o in textures
                 if nm == base or re.fullmatch(re.escape(base) + r"_\d+", nm)]
        if not pages:
            pick = next((o for nm, o in textures if nm == base.split("_")[0]), None)
            if pick is None and textures:
                pick = max(textures, key=lambda t: t[1].read().m_Width * t[1].read().m_Height)[1]
            if pick is None:
                stats["fail"] += 1
                continue
            pages = [(base, pick)]
        for nm, obj in pages:
            obj.read().image.save(folder / (nm + ".png"))
        stats["exported"] += 1

        # 独立背景贴图（有的话）存成 bg.png，网页大招模式铺底层用
        if base in BG_SCENE_OVERRIDE:
            entries = BG_SCENE_OVERRIDE[base]
            if entries and not isinstance(entries[0], (tuple, list)):
                entries = [entries]
            for bi, (tex_name, crop) in enumerate(entries):
                obj = next((o for nm, o in textures if nm == tex_name), None)
                if obj is None:
                    continue
                img = obj.read().image
                if crop:
                    img = img.crop(crop)
                img.save(folder / ("bg.png" if bi == 0 else f"bg{bi + 1}.png"))
                stats["bgs"] += 1
        else:
            bg = None if base in BG_SKIP else pick_bg_texture(textures, base)
            if bg:
                img = bg[1]
                if base in BG_CROP:
                    img = img.crop(BG_CROP[base])
                img.save(folder / "bg.png")
                stats["bgs"] += 1

        if not args.no_render and base.startswith("c"):
            out = OUT_DIR / f"EventScene_{base}.png"
            if out.exists():
                stats["rendered"] += 1
                continue
            p = subprocess.run(
                ["node", "render_static.mjs", str(folder), base, str(out), str(SIZE), "1.2"],
                cwd=str(RUNTIME), capture_output=True, text=True, timeout=180,
            )
            if p.returncode != 0 or not out.exists():
                stats["render_fail"] += 1
                print("  RENDER FAIL", base, p.stderr.strip()[:160], flush=True)
            else:
                stats["rendered"] += 1

        if n % 20 == 0:
            print(f"  {n}/{len(rows)} {stats} {round(time.time()-started)}s", flush=True)

    print("done", json.dumps(stats, ensure_ascii=False),
          f"{round(time.time()-started)}s")


if __name__ == "__main__":
    main()
