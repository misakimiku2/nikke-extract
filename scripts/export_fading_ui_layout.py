#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 FADING AFFECTION 各界面 prefab 的完整 UI 布局树到规范化 JSON。

与 render_ui_prefab.py 的区别：那个脚本把 prefab 画成 PNG，本脚本保留所有
RectTransform 的结构化数据（锚点 / pivot / sizeDelta / anchoredPosition /
scale / 子节点顺序），以及每个 Image 引用的 Sprite、Image.Type、颜色，
供 web 端按原版数据精确还原布局。

用法：
    python scripts/export_fading_ui_layout.py                      # 导出全部目标界面
    python scripts/export_fading_ui_layout.py --id 14111           # 只导出剧情页
    python scripts/export_fading_ui_layout.py --id 14111 --out X.json
"""
from __future__ import annotations

import io
import json
import math
import re
import sqlite3
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import UnityPy
import zstandard as zstd
import export_cg_v2 as v2

# 小游戏各界面 bundle（与 export_fading_ui.py 的 BUNDLES 对齐）
SCREENS = {
    14098: "achievement_popup",
    14100: "ending",
    14101: "firstselect",
    14102: "intro",
    14103: "inventory",
    14104: "inventory_popup",
    14105: "main",
    14106: "popup_guide",
    14107: "popup_guide_menu",
    14108: "recall",
    14109: "recall_popup",
    14110: "routeselect",
    14111: "scenario",
    14112: "special_intro",
}

OUT_DIR = pathlib.Path(r"E:\test\nikke-web\build\fading_ui_layout")
# 贴图导出去重后的目录，用于把 sprite 解析成 /fading_ui/xxx.png
UI_PNG_DIR = pathlib.Path(r"E:\test\nikke-web\public\fading_ui")

ARGS = sys.argv[1:]


def opt(flag, default=None):
    return ARGS[ARGS.index(flag) + 1] if flag in ARGS else default


def _num(v, a, default):
    """注意不能用 `or default`：0.0 是合法值（anchor=0 / pivot=0），会被误判成缺失。"""
    x = getattr(v, a, None)
    return round(float(x), 3) if x is not None else default


def v2f(v, default=0.0):
    if v is None:
        return [default, default]
    return [_num(v, a, default) for a in ("x", "y")]


def v4f(v, default=0.0):
    if v is None:
        return [default] * 4
    return [_num(v, a, default) for a in ("x", "y", "z", "w")]


def rgba(v):
    """UnityEngine.Color 用 r/g/b/a，不是 Vector4 的 x/y/z/w。"""
    if v is None:
        return [1, 1, 1, 1]
    return [_num(v, a, 1.0) for a in ("r", "g", "b", "a")]


def sanitize(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name) or "unnamed"


def load_bundle(pool: str, fid: int, cache: dict):
    if pool not in cache:
        cat = sqlite3.connect(v2.manifest_path(pool))
        cdb = v2.ROOT / pool / "chunk" / "store.cdb"
        cache[pool] = (cat, v2.cidx_map(pool), cdb, cdb.stat().st_size)
    cat, table, cdb, cdb_size = cache[pool]
    bundle, _parts, missing = v2.rebuild(cat, table, cdb, zstd.ZstdDecompressor(), fid, cdb_size)
    if missing or not bundle or not bundle.startswith(b"UnityFS"):
        raise RuntimeError(f"bundle {fid} missing={missing}")
    return UnityPy.load(io.BytesIO(bundle))


def extract(env, pool: str, fid: int) -> dict:
    objs = {}
    for o in env.objects:
        try:
            objs[o.path_id] = (o.type.name, o.read())
        except Exception:
            objs[o.path_id] = (o.type.name, None)

    go_name, go_active = {}, {}
    sprites, textures = {}, {}
    rts = {}
    for pid, (t, d) in objs.items():
        if d is None:
            continue
        if t == "GameObject":
            go_name[pid] = str(getattr(d, "m_Name", "") or "")
            try:
                go_active[pid] = bool(d.m_IsActive)
            except Exception:
                go_active[pid] = True
        elif t == "Sprite":
            sprites[pid] = d
        elif t == "Texture2D":
            textures[str(getattr(d, "m_Name", "") or "")] = d
        elif t in ("RectTransform", "Transform"):
            rts[pid] = d

    # Sprite path_id -> {texture 文件名, border, rect, pivot}
    sprite_meta = {}
    for pid, sp in sprites.items():
        name = str(getattr(sp, "m_Name", "") or "")
        tex_name = name
        rd = getattr(sp, "m_RD", None)
        tex = getattr(rd, "texture", None) if rd else None
        if tex is not None:
            tex_name = str(getattr(tex, "m_Name", "") or tex_name) if isinstance(tex, object) else str(tex)
        # 解析 PPtr 的情况
        if tex_name in ("", "None") or tex_name not in textures:
            for cand in (name, tex_name):
                if cand and cand in textures:
                    tex_name = cand
                    break
        png = sanitize(tex_name) + ".png"
        if not (UI_PNG_DIR / png).exists():
            # 退回用 sprite 名找 PNG
            alt = sanitize(name) + ".png"
            if (UI_PNG_DIR / alt).exists():
                png = alt
        rect = getattr(sp, "m_Rect", None)
        sprite_meta[pid] = {
            "sprite": name,
            "texture": tex_name,
            "png": png if (UI_PNG_DIR / png).exists() else None,
            "border": v4f(getattr(sp, "m_Border", None)),
            "rect": [round(float(getattr(rect, "width", 0) or 0), 2),
                     round(float(getattr(rect, "height", 0) or 0), 2)] if rect else [0, 0],
            "pivot": v2f(getattr(sp, "m_Pivot", None), 0.5),
        }

    # 每个 GameObject 上挂的组件数据（Image / Text）
    comp = {}
    for pid, (t, d) in objs.items():
        if t != "MonoBehaviour" or d is None or type(d).__name__ != "MonoBehaviour":
            continue
        gpid = getattr(getattr(d, "m_GameObject", None), "path_id", 0)
        sp = getattr(d, "m_Sprite", None)
        txt = getattr(d, "m_text", None)
        txt2 = getattr(d, "m_Text", None)
        if sp is None and txt is None and txt2 is None:
            continue
        item = {}
        if sp is not None:
            spid = getattr(sp, "path_id", 0)
            col = getattr(d, "m_Color", None)
            item["image"] = {
                "spritePathId": spid,
                "sprite": (sprite_meta.get(spid) or {}).get("sprite"),
                "png": (sprite_meta.get(spid) or {}).get("png"),
                "type": int(getattr(d, "m_Type", 0) or 0),  # 0 Simple 1 Sliced 2 Tiled 3 Filled
                "color": rgba(col),
                "fill": round(float(getattr(d, "m_FillAmount", 1.0) or 1.0), 3),
            }
        text = txt if txt is not None else txt2
        if text is not None:
            item["text"] = str(text)
        comp.setdefault(gpid, {}).update(item)

    # 父子关系 + 兄弟顺序
    child_of = {}
    for pid, d in rts.items():
        f = getattr(d, "m_Father", None)
        child_of[pid] = getattr(f, "path_id", 0) if f is not None else 0
    roots = [pid for pid in rts if child_of[pid] == 0]

    def node(pid):
        d = rts[pid]
        gpid = getattr(getattr(d, "m_GameObject", None), "path_id", 0)
        n = {
            "name": go_name.get(gpid, "?"),
            "active": go_active.get(gpid, True),
            "anchorMin": v2f(getattr(d, "m_AnchorMin", None), 0.5),
            "anchorMax": v2f(getattr(d, "m_AnchorMax", None), 0.5),
            "pivot": v2f(getattr(d, "m_Pivot", None), 0.5),
            "sizeDelta": v2f(getattr(d, "m_SizeDelta", None), 0.0),
            "anchoredPosition": v2f(getattr(d, "m_AnchoredPosition", None), 0.0),
            "scale": v2f(getattr(d, "m_LocalScale", None), 1.0),
            "rotation": round(float(getattr(getattr(d, "m_LocalRotation", None), "z", 0) or 0), 4),
        }
        c = comp.get(gpid)
        if c:
            n.update(c)
        # 按 m_Children 原始兄弟顺序
        order = []
        for ch in getattr(d, "m_Children", []) or []:
            cp = getattr(ch, "path_id", None)
            if cp in rts:
                order.append(cp)
        if not order:
            order = [k for k, v in child_of.items() if v == pid]
        kids = [node(ch) for ch in order]
        if kids:
            n["children"] = kids
        return n

    # 设计分辨率：prefab 里没有 CanvasScaler，取 NIKKE 通用竖屏参考分辨率；
    # 可用 --canvas WxH 覆盖。不要从 sizeDelta 猜（会拿到局部装饰图的尺寸）。
    cv = opt("--canvas", "1080x1920")
    try:
        cw, ch = (int(v) for v in cv.lower().split("x"))
    except Exception:
        cw, ch = 1080, 1920
    canvas = {"w": cw, "h": ch}

    tree = [node(r) for r in roots]
    # 计算「有效 active」：自身 active 且所有祖先 active。prefab 里同一个按钮的
    # normal/checked/hint/hidden/disable 等状态都做成子节点，只有一个默认 active。
    def mark_eff(n, parent_eff=True):
        n["eff"] = bool(parent_eff and n.get("active", True))
        for c in n.get("children", []):
            mark_eff(c, n["eff"])
    for r in tree:
        mark_eff(r)

    def prune(n):
        """只保留 eff 节点，去掉 inactive 变体，减小体积。"""
        out = {k: v for k, v in n.items() if k != "children"}
        kids = [prune(c) for c in n.get("children", []) if c.get("eff")]
        if kids:
            out["children"] = kids
        return out

    # 只保留可见树里用到的 sprite 元数据
    used = set()
    def collect(n):
        im = n.get("image")
        if im:
            used.add(str(im.get("spritePathId")))
        for c in n.get("children", []):
            collect(c)
    for r in tree:
        collect(r)
    sprite_out = {k: sprite_meta[int(k)] for k in used if int(k) in sprite_meta}

    # 动态模板：剧情页的选项按钮是 prefab 里一个 active=false 的 item_page，
    # 运行时按选项数克隆。web 端只需要它几个节点的 RectTransform 来摆放动态内容，
    # 因此只保留通往目标节点的骨架（去掉大量图片/状态变体），避免 JSON 膨胀。
    TARGETS = {"txt_label_01", "board_scenario_select"}

    def skeleton(n):
        """返回只含目标路径的骨架；子树没有目标则返回 None。"""
        if n["name"] == "board_scenario_select":
            out = {k: v for k, v in n.items() if k != "children"}
            out["children"] = [
                {k: v for k, v in b.items() if k != "children"}
                for b in n.get("children", []) if "btn_scenario_select" in b["name"]
            ]
            return out
        if n["name"] in TARGETS:
            return {k: v for k, v in n.items() if k != "children"}
        kids = [s for c in n.get("children", []) if (s := skeleton(c)) is not None]
        if not kids:
            return None
        out = {k: v for k, v in n.items() if k != "children"}
        out["children"] = kids
        return out

    templates = {}
    def collect_templates(n, path=""):
        p = path + "/" + n["name"]
        if n["name"] in ("item_page", "board_previous_select_option") and "scenario_marian" in p:
            skel = skeleton(n)
            if skel:
                templates[n["name"]] = skel
            return
        for c in n.get("children", []):
            collect_templates(c, p)
    for r in tree:
        collect_templates(r)

    return {
        "id": fid,
        "pool": pool,
        "screen": SCREENS.get(fid, f"bundle_{fid}"),
        # NIKKE 竖屏设计分辨率（prefab 里没有 CanvasScaler，取通用值；可用 --canvas 覆盖）
        "canvas": canvas,
        "spriteMeta": sprite_out,
        "tree": [prune(r) for r in tree],
        "templates": templates,
        "fullTree": tree,
    }


def main():
    ids = [int(opt("--id"))] if opt("--id") else list(SCREENS)
    cache = {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fid in ids:
        pool = "core"
        if fid == 5050:
            pool = "dp"
        try:
            env = load_bundle(pool, fid, cache)
        except Exception as e:
            print(f"SKIP {fid}: {e}")
            continue
        data = extract(env, pool, fid)
        full_tree = data.pop("fullTree")
        out = pathlib.Path(opt("--out")) if opt("--out") else (OUT_DIR / f"{data['screen']}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        # 完整树（含 inactive 状态变体）单独存，供分析各按钮的 normal/checked/hint 等状态
        full_out = out.with_name(out.stem + ".full.json")
        full_data = dict(data, tree=full_tree)
        full_out.write_text(json.dumps(full_data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved {out}  nodes={_count(data['tree'])} full={_count(full_tree)} canvas={data['canvas']}")
    for cat, _, _, _ in cache.values():
        cat.close()


def _count(tree):
    return sum(1 + _count(n.get("children", [])) for n in tree)


if __name__ == "__main__":
    main()
