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
    print(f"done: saved={saved} skipped={skipped} -> {OUT}")


if __name__ == "__main__":
    main()
