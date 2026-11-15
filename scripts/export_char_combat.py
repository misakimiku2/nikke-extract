"""Extract combat spine models (战斗姿态: aim 背身射击 / cover 掩体) from the dp pool.

Source (dp pool):
  spinecombatcharactergroup(hd)_assets_spine/combat/<char>/<variant>/<pose>_hd_<hash>.bundle
    TextAsset  <char>_aim_<variant>.atlas / .skel     (cover 同理)
    Texture2D  <name> 2048² 图集（可能有 <name>_2 第二页）

站姿管线 (export_char_standing.py) 的姊妹版，区别：
  - 每个皮肤两个姿态：aim（背对镜头开枪）与 cover（掩体后），姿态由 key 段区分
  - 不渲染静态帧：角色页战斗模式直接播实时模型，加载态沿用现有 spinner
  - bundle 数 803（aim+cover 合计），全程只做重拼 + UnityPy 解包，约 15 分钟

  python scripts/export_char_combat.py --pose aim --only c010_00   # 先试一个
  python scripts/export_char_combat.py                             # 全量 aim+cover

Output: staging/spine_combat/<name>/   name = c010_aim_00 / c010_cover_00
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import sqlite3
import time

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2

BASE = pathlib.Path(__file__).resolve().parents[1]
STAGING = BASE / "staging" / "spine_combat"


def text_bytes(obj):
    s = obj.read().m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    return bytes(s or b"")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pose", default="all", choices=["all", "aim", "cover"],
                    help="只要哪个战斗姿态（默认全要）")
    ap.add_argument("--only", default="",
                    help="只处理这些 皮肤（char/variant），逗号分隔，例如 c010_00,c012_00")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    STAGING.mkdir(parents=True, exist_ok=True)

    cat = sqlite3.connect(v2.manifest_path("dp"))
    table = v2.cidx_map("dp")
    cdb = v2.ROOT / "dp" / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    dec = zstd.ZstdDecompressor()

    rows = cat.execute(
        "select file_id, key from files_chunktype"
        " where key like 'spinecombatcharactergroup(hd)%'"
    ).fetchall()
    rows.sort(key=lambda r: r[1])
    # key 形如 .../combat/c010/00/aim_hd_<hash>.bundle，姿态与皮肤都能从 key 里拿
    filtered = []
    for fid, key in rows:
        seg = key.rstrip("/").rsplit("/", 1)[-1]      # aim_hd_<hash>.bundle
        pose = seg.split("_", 1)[0]                    # aim | cover
        m = re.search(r"/combat/([\w]+/[\w]+)/", key)
        skin = f"{m.group(1).replace('/', '_')}" if m else ""
        if args.pose != "all" and pose != args.pose:
            continue
        if args.only and skin not in {s.strip() for s in args.only.split(",") if s.strip()}:
            continue
        filtered.append((fid, key, pose))
    if args.limit:
        filtered = filtered[: args.limit]
    print(f"combat bundles: {len(filtered)} (pose={args.pose})", flush=True)

    stats = {"ok": 0, "fail": 0, "no_atlas": 0, "no_skel": 0, "incomplete": 0, "skip": 0}
    started = time.time()
    for n, (fid, key, pose) in enumerate(filtered, 1):
        bundle, _p, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
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
        if (folder / (base + ".atlas")).exists():
            stats["skip"] += 1
            continue
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (base + ".atlas")).write_bytes(text_bytes(assets[base + ".atlas"]))
        (folder / (base + ".skel")).write_bytes(text_bytes(assets[base + ".skel"]))

        # 图集页可能与站姿一样有多页：<base>.png 与 <base>_2.png（武器/特效页）
        pages = [(nm, o) for nm, o in textures if nm == base or re.fullmatch(re.escape(base) + r"_\d+", nm)]
        if not pages:
            pick = next((o for nm, o in textures if nm == base), None)
            if pick is None and textures:
                pick = max(textures, key=lambda t: t[1].read().m_Width * t[1].read().m_Height)[1]
            if pick is None:
                stats["fail"] += 1
                continue
            pages = [(base, pick)]
        for nm, obj in pages:
            obj.read().image.save(folder / (nm + ".png"))
        stats["ok"] += 1

        if n % 50 == 0:
            print(f"  {n}/{len(filtered)} {stats} {round(time.time()-started)}s", flush=True)

    print("done", json.dumps(stats, ensure_ascii=False), f"{round(time.time()-started)}s")


if __name__ == "__main__":
    main()
