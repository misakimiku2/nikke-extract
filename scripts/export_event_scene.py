"""Export one NIKKE Spine event-scene bundle by name substring.

    python scripts/export_event_scene.py skyontherock

Writes <动态CG>/模型/EventScene_<NAME>/<base>.{atlas,skel,png}
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2

OUT = v2.BASE / "动态CG" / "模型"


def text_bytes(obj):
    s = obj.read().m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    return bytes(s or b"")


def main() -> None:
    needle = sys.argv[1] if len(sys.argv) > 1 else "skyontherock"
    cat = sqlite3.connect(v2.manifest_path("core"))
    table = v2.cidx_map("core")
    cdb = v2.ROOT / "core" / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size
    dec = zstd.ZstdDecompressor()

    rows = cat.execute(
        "select file_id,key from files_chunktype where lower(key) like ? and lower(key) like '%spineeventscenesgroup%'",
        (f"%{needle.lower()}%",),
    ).fetchall()
    print("bundles:", len(rows))
    for fid, key in rows:
        bundle, parts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
        if not bundle or not bundle.startswith(b"UnityFS"):
            print("  FAIL", key, "parts", parts, "missing", missing)
            continue
        env = UnityPy.load(io.BytesIO(bundle))
        assets, textures = {}, []
        for o in env.objects:
            try:
                name = str(getattr(o.read(), "m_Name", "") or "")
            except Exception:
                continue
            if o.type.name == "TextAsset" and name.endswith((".atlas", ".skel", ".json")):
                assets[name] = o
            elif o.type.name == "Texture2D":
                textures.append((name, o))
        atlases = [k for k in assets if k.endswith(".atlas")]
        if not atlases:
            print("  no atlas in", key)
            continue
        base = atlases[0][: -len(".atlas")]
        skel = base + ".skel"
        if skel not in assets:
            print("  no skel in", key, list(assets))
            continue
        folder = OUT / re.sub(r"[^\w.-]+", "_", base)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (base + ".atlas")).write_bytes(text_bytes(assets[base + ".atlas"]))
        (folder / skel).write_bytes(text_bytes(assets[skel]))
        pick = next((o for n, o in textures if n in (base + ".png", base)), None)
        if pick is None and textures:
            pick = max(textures, key=lambda t: t[1].read().m_Width * t[1].read().m_Height)[1]
        if pick is not None:
            img = pick.read().image
            img.save(folder / (base + ".png"))
            print(f"  -> {folder}  png={img.size}  atlas={len(textures)} sheets")
        else:
            print(f"  -> {folder}  (textures: {[n for n, _ in textures]})")
        print("     assets:", sorted(assets))


if __name__ == "__main__":
    main()
