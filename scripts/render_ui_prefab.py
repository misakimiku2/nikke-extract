"""Render a Unity UI prefab bundle to a PNG by walking RectTransforms.

    python scripts/render_ui_prefab.py --id 15257 --pool core --out out.png \
        [--canvas 1080x1920] [--scale 2] [--only opening] [--layer-dir DIR]

Only draws Image nodes whose sprite resolves to a Texture2D in the bundle.
Good enough to reconstruct event key-art composed from layered sprites.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

import UnityPy
import zstandard as zstd
from PIL import Image

import export_cg_v2 as v2


def main() -> None:
    args = sys.argv[1:]
    def opt(flag, default=None):
        return args[args.index(flag) + 1] if flag in args else default

    fid = int(opt("--id"))
    pool = opt("--pool", "core")
    out = Path(opt("--out", "ui_render.png"))
    canvas = opt("--canvas", "1080x1920")
    cw, ch = (int(v) for v in canvas.lower().split("x"))
    scale = float(opt("--scale", "1"))
    only = (opt("--only") or "").lower()
    layer_dir = opt("--layer-dir")

    cat = sqlite3.connect(v2.manifest_path(pool))
    table = v2.cidx_map(pool)
    cdb = v2.ROOT / pool / "chunk" / "store.cdb"
    dec = zstd.ZstdDecompressor()
    bundle, parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb.stat().st_size)
    print(f"bundle {len(bundle):,} parts={parts} missing={missing}")
    env = UnityPy.load(io.BytesIO(bundle))

    objs = {}
    for o in env.objects:
        try:
            objs[o.path_id] = (o.type.name, o.read())
        except Exception:
            objs[o.path_id] = (o.type.name, None)

    go_name = {}
    for pid, (t, d) in objs.items():
        if t == "GameObject" and d is not None:
            go_name[pid] = str(getattr(d, "m_Name", "") or "")

    # texture lookup by name
    textures = {}
    for pid, (t, d) in objs.items():
        if t == "Texture2D" and d is not None:
            try:
                textures[str(getattr(d, "m_Name", ""))] = d
            except Exception:
                pass
    print("textures:", list(textures))

    sprites = {}
    for pid, (t, d) in objs.items():
        if t == "Sprite" and d is not None:
            sprites[pid] = d

    rts = {}
    for pid, (t, d) in objs.items():
        if t in ("RectTransform", "Transform") and d is not None:
            rts[pid] = d

    def vec(v, default=0.0):
        return (getattr(v, "x", default), getattr(v, "y", default)) if v is not None else (default, default)

    def world_rect(pid, parent):
        d = rts[pid]
        amin = vec(getattr(d, "m_AnchorMin", None), 0.5)
        amax = vec(getattr(d, "m_AnchorMax", None), 0.5)
        ap = vec(getattr(d, "m_AnchoredPosition", None), 0.0)
        sd = vec(getattr(d, "m_SizeDelta", None), 100.0)
        pv = vec(getattr(d, "m_Pivot", None), 0.5)
        sc = vec(getattr(d, "m_LocalScale", None), 1.0)
        px, py, pw, ph = parent
        w = sd[0] + (amax[0] - amin[0]) * pw
        h = sd[1] + (amax[1] - amin[1]) * ph
        cx = px + amin[0] * pw + ap[0]
        cy = py + amin[1] * ph + ap[1]
        w *= sc[0]
        h *= sc[1]
        x = cx - pv[0] * w
        y = cy - pv[1] * h
        return (x, y, w, h)

    # roots: transforms without father inside bundle
    child_of = {}
    roots = []
    for pid, d in rts.items():
        f = getattr(d, "m_Father", None)
        pfid = getattr(f, "path_id", 0) if f is not None else 0
        child_of[pid] = pfid
        if pfid == 0:
            roots.append(pid)
    # root canvas size: use the largest RectTransform sizeDelta or the given canvas
    root_box = (0.0, 0.0, float(cw), float(ch))

    draw_ops = []

    def walk(pid, parent_box, depth, is_root=False):
        d = rts[pid]
        box = parent_box if is_root else world_rect(pid, parent_box)
        gpid = getattr(getattr(d, "m_GameObject", None), "path_id", 0)
        gname = go_name.get(gpid, "")
        # draw images attached to this GameObject
        for opid, (t, od) in objs.items():
            if t != "MonoBehaviour" or od is None:
                continue
            if type(od).__name__ != "MonoBehaviour":
                continue
            if getattr(getattr(od, "m_GameObject", None), "path_id", 0) != gpid:
                continue
            sp = getattr(od, "m_Sprite", None)
            if sp is None:
                continue
            sdata = sprites.get(getattr(sp, "path_id", 0))
            if sdata is None:
                continue
            sname = str(getattr(sdata, "m_Name", "") or "")
            tex = textures.get(sname)
            if tex is None:
                # sprite name may differ from texture name; use m_RD.texture
                rd = getattr(sdata, "m_RD", None)
                t2 = getattr(rd, "texture", None) if rd else None
                if t2 is not None:
                    tex = textures.get(str(getattr(t2, "m_Name", "") or ""))
            if tex is None:
                continue
            col = getattr(od, "m_Color", None)
            alpha = getattr(col, "a", 1.0) if col is not None else 1.0
            mtype = getattr(od, "m_Type", 0)
            fill = getattr(od, "m_FillAmount", 1.0)
            if alpha <= 0.01:
                continue
            draw_ops.append((depth, len(draw_ops), gname, sname, box, tex, alpha, mtype, fill))
        kids = [c for c, p in child_of.items() if p == pid]
        # keep original sibling order from m_Children
        order = []
        for c in getattr(d, "m_Children", []) or []:
            cp = getattr(c, "path_id", None)
            if cp in child_of:
                order.append(cp)
        if not order:
            order = kids
        for c in order:
            walk(c, box, depth + 1)

    for r in roots:
        walk(r, root_box, 0, is_root=True)

    # painter order: depth asc, then document order (parents before children)
    draw_ops.sort(key=lambda t: (t[0], t[1]))
    print(f"draw ops: {len(draw_ops)}")
    if only:
        draw_ops = [d for d in draw_ops if only in d[2].lower() or only in d[3].lower()]

    W, H = int(cw * scale), int(ch * scale)
    canvas_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if layer_dir:
        Path(layer_dir).mkdir(parents=True, exist_ok=True)
    meta = []
    for i, (depth, _, gname, sname, box, tex, alpha, mtype, fill) in enumerate(draw_ops):
        x, y, w, h = box
        if w <= 0 or h <= 0:
            continue
        # UI y axis is bottom-up; image y axis top-down
        left = x * scale
        top = (ch - (y + h)) * scale
        ww, hh = max(1, round(w * scale)), max(1, round(h * scale))
        try:
            src = tex.image.convert("RGBA")
        except Exception as e:
            print("  tex fail", sname, e)
            continue
        if mtype == 2:  # tiled
            tile = Image.new("RGBA", (ww, hh), (0, 0, 0, 0))
            for ty in range(0, hh, src.height):
                for tx in range(0, ww, src.width):
                    tile.paste(src, (tx, ty))
            layer = tile
        else:
            layer = src.resize((ww, hh), Image.LANCZOS) if (ww, hh) != src.size else src.copy()
        if alpha < 0.999:
            a = layer.getchannel("A").point(lambda v: int(v * alpha))
            layer.putalpha(a)
        canvas_img.alpha_composite(layer, (round(left), round(top)))
        meta.append(dict(i=i, go=gname, sprite=sname, box=[round(v, 1) for v in box],
                         alpha=round(alpha, 3), type=mtype))
        if layer_dir:
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in gname or "node")
            layer.save(Path(layer_dir) / f"{i:02d}_{safe}.png")

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas_img.save(out)
    print("saved", out, canvas_img.size)
    if layer_dir:
        (Path(layer_dir) / "layout.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
