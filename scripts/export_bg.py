"""Export ALL plain scenario backgrounds (non-EventScene scenariobackground bundles).

scenariobackground(hd) 组里有两类 bundle：
  assets_eventscene_<名>_<hash>.bundle   EventScene_* CG（export_cg_v2.py 负责）
  assets_<场景名>_<hash>.bundle          纯剧情背景（本脚本负责）——剧情演出里
                                          铺在人物/spine 动态 CG 下面的场景板，
                                          纹理名如 BigHotSpring_d / Desert_05 / IceLand_01

背景不是 CG 插画，单独归档到 CG/06_剧情背景/，文件名用游戏内纹理原名——
剧情表里的背景 token（裸资源名）就是按这个名字出现的，可直接对上。
bundle 身份名 = 纹理名小写，与 eventscene 组同款。

幂等：已存在的成品跳过不覆盖；SD bundle 的 chunk 本机不下载（HD 设备），自动跳过。
输出：CG/06_剧情背景/*.png + CG/06_剧情背景/_清单/剧情背景清单.csv
"""
from __future__ import annotations

import collections
import csv
import io
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import UnityPy
import zstandard as zstd
from PIL import Image

import export_cg_v2 as v2
from export_cg_v2 import noise_score

BASE = v2.BASE
ROOT = v2.ROOT
OUT = BASE / "CG" / "06_剧情背景"
LIST_DIR = OUT / "_清单"

IDENTITY = re.compile(
    r"scenariobackground\((hd|sd)\)_assets_(?!eventscene_)(.+?)_[0-9a-f]{32}\.bundle$", re.I)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dec = zstd.ZstdDecompressor()
    stats = collections.Counter()
    report = []
    started = time.time()

    cat = sqlite3.connect(v2.manifest_path("dp"))
    table = v2.cidx_map("dp")
    cdb = ROOT / "dp" / "chunk" / "store.cdb"
    cdb_size = cdb.stat().st_size

    # HD 优先：同身份先处理 hd，sd 直接跳过（本机 SD chunk 全缺，重了也没用）
    rows = cat.execute(
        "select file_id,key from files_chunktype where key like 'scenariobackground%_assets_%'").fetchall()
    seen_quality = {}
    for fid, key in rows:
        m = IDENTITY.fullmatch(key)
        if not m:
            stats["unmatched"] += 1
            continue
        quality, ident = m.group(1).lower(), m.group(2).lower()
        if ident not in seen_quality or quality == "hd":
            seen_quality[ident] = (fid, key, quality)
    print(f"plain background identities: {len(seen_quality)}")

    for ident, (fid, key, quality) in sorted(seen_quality.items()):
        stats["bundles"] += 1
        if quality != "hd":
            stats["skipped_sd"] += 1
            continue
        bundle, nparts, missing = v2.rebuild(cat, table, cdb, dec, fid, cdb_size)
        if missing or not bundle or not bundle.startswith(b"UnityFS"):
            stats["incomplete"] += 1
            report.append((ident, key, "", "", 0, "重建失败", ""))
            continue
        try:
            env = UnityPy.load(io.BytesIO(bundle))
            objects = list(env.objects)
        except Exception:
            stats["unitypy_fail"] += 1
            continue
        for obj in objects:
            if obj.type.name != "Texture2D":
                continue
            try:
                tex = obj.read()
                name = str(getattr(tex, "m_Name", "") or "")
                if not name:
                    continue
                img = tex.image
                if not isinstance(img, Image.Image):
                    img = img.convert("RGBA")
                dest = OUT / (re.sub(r"[^\w.-]+", "_", name) + ".png")
                if dest.exists():
                    stats["already_exists"] += 1
                    continue
                img.save(dest)
                sc = noise_score(img)
                report.append((ident, key, name, f"{img.size[0]}x{img.size[1]}",
                               dest.stat().st_size, "ok" if sc <= 50 else "suspicious", sc))
                stats["exported"] += 1
                if sc > 50:
                    stats["suspicious"] += 1
            except Exception:
                stats["texture_fail"] += 1
        if stats["bundles"] % 100 == 0:
            print(f"  {stats['bundles']} bundles, {stats['exported']} bgs, "
                  f"{round(time.time()-started)}s", flush=True)
    cat.close()

    LIST_DIR.mkdir(exist_ok=True)
    with (LIST_DIR / "剧情背景清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["身份名", "bundle", "纹理名", "尺寸", "字节数", "状态", "噪声分"])
        for row in sorted(set(report)):
            w.writerow(row)
    print("\nstats", dict(stats))
    print("elapsed", round(time.time() - started, 1), "s ->", OUT)


if __name__ == "__main__":
    main()
