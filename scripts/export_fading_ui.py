#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 FIRST AFFECTION 小游戏的原版 UI 纹理到网站 public/fading_ui/。

素材来源：本机资源池 core 里的 eventui-marian_assets_adventure_* bundle
（file_id 14098..14112，由 probe_bundle.py --list marian 找到）。这些纹理是
游戏内纸张档案 UI 的真实贴图：纸张纹理、标题条、状态面板、选项条、
Checked / ??? / HINT / Script / ACCESS DENIED 标签、藤蔓装饰、路线插画等。

用法：python scripts/export_fading_ui.py
幂等：已存在的文件跳过；可用 --force 覆盖。
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import UnityPy
import zstandard as zstd
import export_cg_v2 as v2

# 小游戏本体 UI：adventure_* 全套 + 结局/状态图标 + view-fadingaffection* 视图壳
BUNDLES = (
    [("core", i) for i in list(range(14098, 14113)) + [14117] +
     list(range(14120, 14127)) + list(range(26802, 26814))] +
    # dp 池的 icons-event-89_marian(hd)：教程插画与 icn_fadingaffection_* 图标
    [("dp", 5050)]
)
OUT = pathlib.Path(r"E:\test\nikke-web\public\fading_ui")
# Sprite 子资源里的九宫格 border / 原始 Rect / pivot —— PNG 本身不带这些信息，
# 但 Unity UI 靠它们决定 Sliced / Tiled 的拉伸方式。写到 build/ 入库，
# 由 nikke-web 的 Vite 插件合并进素材清单。
SPRITES_META = pathlib.Path(r"E:\test\nikke-web\build\fading_ui_sprites.json")
FORCE = "--force" in sys.argv

# 不再做白名单筛选：上述 bundle 里的全部 Texture2D 都导出，保证「所有用到的图片」都在。
# 排除的是明显属于其它活动的通用 atlas（名字里有别的活动 key），它们在游戏里不会
# 被小游戏引用，且体积很大。
EXCLUDE_NEEDLES = (
    "2x2love", "arkguardian", "blankticket", "terminusticket",
    "wavetoyou", "footstepwalkrun", "bow-wowparadise", "memoriesteller",
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dec = zstd.ZstdDecompressor()
    saved = skipped = 0
    sprites: dict[str, dict] = {}
    # 按资源池缓存连接，避免每张 bundle 重开 catalog
    pools = {}
    for pool, fid in BUNDLES:
        if pool not in pools:
            cat = sqlite3.connect(v2.manifest_path(pool))
            cdb = v2.ROOT / pool / "chunk" / "store.cdb"
            pools[pool] = (cat, v2.cidx_map(pool), cdb, cdb.stat().st_size)
        cat, table, cdb, cdb_size = pools[pool]
        bundle, _parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
        if missing or not bundle or not bundle.startswith(b"UnityFS"):
            continue
        env = UnityPy.load(io.BytesIO(bundle))
        for o in env.objects:
            # Sprite 子资源：九宫格 border / 原始 Rect / pivot。
            # 同一个名字可能在多个 bundle 出现，取第一份即可（内容一致）。
            if o.type.name == "Sprite":
                try:
                    sp = o.read()
                    name = str(getattr(sp, "m_Name", "") or "")
                except Exception:
                    continue
                low = name.lower()
                if not name or any(x in low for x in EXCLUDE_NEEDLES):
                    continue
                safe = re.sub(r"[^\w.-]+", "_", name) or f"sprite_{o.path_id}"
                if safe in sprites:
                    continue

                def v4(v):
                    if v is None:
                        return [0, 0, 0, 0]
                    return [round(float(getattr(v, a, 0) or 0), 2) for a in ("x", "y", "z", "w")]

                rect = getattr(sp, "m_Rect", None)
                pivot = getattr(sp, "m_Pivot", None)
                sprites[safe] = {
                    # Unity Sprite.border 顺序 = 左, 下, 右, 上
                    "border": v4(getattr(sp, "m_Border", None)),
                    "rect": [round(float(getattr(rect, "width", 0) or 0), 2),
                             round(float(getattr(rect, "height", 0) or 0), 2)],
                    "pivot": [round(float(getattr(pivot, "x", 0) or 0), 3),
                              round(float(getattr(pivot, "y", 0) or 0), 3)],
                }
                continue
            if o.type.name != "Texture2D":
                continue
            try:
                tex = o.read()
                name = str(getattr(tex, "m_Name", "") or "")
            except Exception:
                continue
            low = name.lower()
            if any(x in low for x in EXCLUDE_NEEDLES):
                continue
            # 贴图名可能含 '|' 等 Windows 非法字符，统一清洗
            safe = re.sub(r"[^\w.-]+", "_", name) or f"tex_{o.path_id}"
            dest = OUT / (safe + ".png")
            if dest.exists() and not FORCE:
                skipped += 1
                continue
            try:
                tex.image.save(dest)
                saved += 1
                print("saved", dest.name)
            except Exception as e:
                print("skip", name, e)
    for cat, _, _, _ in pools.values():
        cat.close()
    # Sprite 元数据单独落盘（很小，入 build/ 库），PNG 仍只放 public/fading_ui/
    SPRITES_META.parent.mkdir(parents=True, exist_ok=True)
    SPRITES_META.write_text(
        json.dumps({"_note": "Unity Sprite 子资源的九宫格信息；border 顺序=左,下,右,上；由 export_fading_ui.py 重新生成",
                    "items": dict(sorted(sprites.items()))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"done: saved={saved} skipped={skipped} -> {OUT}")
    print(f"sprite meta: {len(sprites)} -> {SPRITES_META}")


if __name__ == "__main__":
    main()
