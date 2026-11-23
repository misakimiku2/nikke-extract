#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出小游戏主菜单标题页的 Spine 模型到 nikke-web/public/spine/。

素材在 core bundle 14102（view_assets_view-fadingaffectionintro）里，四件套齐全：
  TextAsset  MinigameTitle_fadingaffection_01.atlas   图集定义（page 2048²，scale 1.8）
  TextAsset  MinigameTitle_fadingaffection_01.skel    Spine 4.1.20A 二进制骨架
  Texture2D  MinigameTitle_fadingaffection_01         图集页贴图
  MonoBehaviour MinigameTitle_fadingaffection_01_SkeletonData / _Atlas / _Material

为什么不直接丢进 CG/ 走 build_spine_models.py：那个脚本从 nikke_extract/CG 全量
扫 .atlas，而 build_cg_index.py 也扫 CG/，标题页模型会被当成剧情 CG 收进图库。
这里单独落 public/spine/，CG 索引看不见它。

PMA 处理与 build_spine_models.py 保持一致（同一个坑不能踩两遍）：
图集页是 pma:true，浏览器解码后仍是预乘数据，SpinePlayer 里已经关了
GLTexture 的再次预乘；但 alpha=0 的像素必须整颗清零，否则 libwebp 会往里塞
压缩填充色，PMA 混合（ONE）下这些垃圾色直接加到画面上，沿部件轮廓出现白细线。
所以用 lossless + exact=True。

用法：python scripts/export_fading_intro_spine.py [--force]
"""
from __future__ import annotations

import io
import pathlib
import re
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import UnityPy  # noqa: E402
from PIL import Image  # noqa: E402

import export_fading_ui_layout as L  # noqa: E402

NAME = "MinigameTitle_fadingaffection_01"
BUNDLE = 14102
OUT = pathlib.Path(r"E:\test\nikke-web\public\spine") / NAME
FORCE = "--force" in sys.argv


def read_text_asset(obj) -> bytes:
    """UnityPy 的 TextAsset.m_Script 在不同版本里可能是 str / bytes / 带 .data 的对象。"""
    s = obj.m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    if isinstance(s, (bytes, bytearray)):
        return bytes(s)
    return getattr(s, "data", b"")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dst_atlas = OUT / (NAME + ".atlas")
    dst_skel = OUT / (NAME + ".skel")
    dst_png = OUT / (NAME + ".spine.webp")
    if all(p.exists() for p in (dst_atlas, dst_skel, dst_png)) and not FORCE:
        print("已存在，跳过（--force 覆盖）")
        return

    env = L.load_bundle("core", BUNDLE, {})
    atlas_text = skel = img = None
    for o in env.objects:
        try:
            d = o.read()
        except Exception:
            continue
        nm = str(getattr(d, "m_Name", "") or "")
        if o.type.name == "TextAsset" and nm == NAME + ".atlas":
            atlas_text = read_text_asset(d).decode("utf-8", "replace")
        elif o.type.name == "TextAsset" and nm == NAME + ".skel":
            skel = read_text_asset(d)
        elif o.type.name == "Texture2D" and nm == NAME:
            img = d.image

    missing = [n for n, v in (("atlas", atlas_text), ("skel", skel), ("texture", img)) if not v]
    if missing:
        sys.exit(f"bundle {BUNDLE} 里缺：{', '.join(missing)}")

    # 图集第一行是页文件名，换成实际导出的贴图名
    lines = atlas_text.splitlines()
    lines[0] = NAME + ".spine.webp"
    atlas_text = "\n".join(lines) + "\n"

    im = img.convert("RGBA") if hasattr(img, "convert") else Image.open(io.BytesIO(img[1])).convert("RGBA")
    # 声明尺寸 vs 真实贴图尺寸不一致时，atlas 的 size 与全部几何字段要同比缩放。
    # 口径与 nikke-web/build/build_spine_models.py 的 fit_atlas_to_image 完全一致：
    # Spine 运行时用 size 算 UV、用 bounds/offsets/orig 算附件几何，两边空间不一致
    # 画面就会碎成马赛克，所以这些字段必须一起缩。
    declared = re.search(r"^size:\s*(\d+),\s*(\d+)", atlas_text, re.M)
    if declared and (int(declared.group(1)), int(declared.group(2))) != im.size:
        aw, ah = int(declared.group(1)), int(declared.group(2))
        rx, ry = im.size[0] / aw, im.size[1] / ah
        if abs(rx - ry) > 0.01:
            sys.exit(f"! 贴图 {im.size} 与 atlas size {aw}x{ah} 非等比，不能自动缩放，请人工确认")
        print(f"! atlas size {aw}x{ah} -> 贴图 {im.size[0]}x{im.size[1]}，同比缩放 {rx:.3f}")
        fields = {"bounds", "offsets", "orig", "offset", "xy"}

        def scale_line(m):
            key = m.group(2)
            if key == "size":
                return f"{m.group(1)}{key}{m.group(3)}{im.size[0]},{im.size[1]}"
            if key not in fields:
                return m.group(0)
            vals = ",".join(str(round(int(v.strip()) * rx)) for v in m.group(4).split(","))
            return m.group(1) + key + m.group(3) + vals

        atlas_text = re.sub(r"^(\s*)(\w+)(\s*:\s*)(.+)$", scale_line, atlas_text, flags=re.M)

    # alpha=0 的像素整颗清零，避免 webp 往全透明像素里塞填充色
    alpha = im.getchannel("A")
    zero = alpha.point(lambda v: 255 if v == 0 else 0)
    im = Image.composite(Image.new("RGBA", im.size, (0, 0, 0, 0)), im, zero)
    im.save(dst_png, "WEBP", lossless=True, method=6, exact=True)

    dst_atlas.write_text(atlas_text, encoding="utf-8")
    dst_skel.write_bytes(skel)
    print(f"saved {OUT}")
    for p in (dst_atlas, dst_skel, dst_png):
        print(f"  {p.name:44s} {p.stat().st_size:>9,} bytes")


if __name__ == "__main__":
    main()
