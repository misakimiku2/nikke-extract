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

BUNDLES = list(range(14098, 14113))   # eventui-marian_assets_adventure_*
OUT = pathlib.Path(r"E:\test\nikke-web\public\fading_ui")
FORCE = "--force" in sys.argv

# 只导出网页实际用到的纹理，避免把 30 MB 的特效图集也搬过去
WANT = {
    "marian_bg_texture", "marian_texture_paper", "marian_ptn_paper",
    "marian_ptn_wood_01", "marian_ptn_wood_02",
    "marian_main_back_bg_01", "marian_main_back_bg_02", "marian_main_back_bg_03",
    "marian_main_back_bg_04", "marian_main_back_bg_05",
    "marian_main_top_bg", "marian_main_middle_bg",
    "marian_mask_scene", "marian_bg_tilte", "marian_deco_state_01",
    "marian_deco_state_02", "marian_bg_state", "marian_bg_choice",
    "marian_bg_choice_maria", "marian_bg_choice_hidden", "marian_txt_check",
    "marian_txt_choice_hidden", "marian_icn_hint", "marian_txt_script",
    "marian_txt_accessdenied", "marian_txt_denied", "marian_deco_01",
    "marian_deco_02", "marian_deco_03", "marian_deco_04", "marian_deco_05",
    "marian_deco_book", "marian_deco_book_marian", "marian_btn_bg",
    "marian_map_bg_mono", "marian_routeselect_01", "marian_routeselect_02",
    "marian_routeselect_03", "marian_bg_book", "marian_divider_01",
    "marian_main_paper", "marian_icn_memory", "marian_icn_lock",
    "marian_bg_check", "marian_icn_reddot",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cat = sqlite3.connect(v2.manifest_path("core"))
    table = v2.cidx_map("core")
    cdb = v2.ROOT / "core" / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    dec = zstd.ZstdDecompressor()

    saved = skipped = 0
    for fid in BUNDLES:
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
            if name not in WANT:
                continue
            dest = OUT / (name + ".png")
            if dest.exists() and not FORCE:
                skipped += 1
                continue
            try:
                tex.image.save(dest)
                saved += 1
                print("saved", dest.name)
            except Exception as e:
                print("skip", name, e)
    cat.close()
    print(f"done: saved={saved} skipped={skipped} -> {OUT}")


if __name__ == "__main__":
    main()
