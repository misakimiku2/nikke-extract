"""Reorganise the exported CG library into one folder per CG.

Final layout:
  CG/01_活动剧情CG/<活动>/<名称>.png            full illustration
  CG/01_活动剧情CG/<活动>/<名称>.spine.png      Spine atlas sheet (only for dynamic CGs)
  CG/01_活动剧情CG/<活动>/<名称>.atlas
  CG/01_活动剧情CG/<活动>/<名称>.skel

Why the rename: the atlas' first line names its page image, and that name was
identical to the illustration's filename. Keeping both in one folder would make
the atlas load the illustration instead of the sheet, so the sheet becomes
`<name>.spine.png` and the atlas page line is rewritten.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]
CG = BASE / "CG"
FLAT = CG / "全量分类"
MODELS = BASE / "staging" / "spine"
LEGACY_MODELS = BASE / "动态CG" / "模型"
RUNTIME = BASE / "动态CG" / "runtime"
OTHERS = CG / "05_其他动态CG"
PRESERVED = CG / "_preserved_Marian_01.png"

DRY = "--dry-run" in sys.argv
SIZE = 2048


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def flatten() -> None:
    """CG/全量分类/<category> -> CG/<category>; CSVs -> CG/_清单/"""
    if not FLAT.exists():
        return
    listdir = CG / "_清单"
    for item in FLAT.iterdir():
        dst = CG / item.name
        if item.is_dir():
            if dst.exists():
                print("  ! target exists, merging", item.name)
                for f in item.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(item)
                        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                        if not (dst / rel).exists():
                            if not DRY:
                                shutil.move(str(f), str(dst / rel))
            elif not DRY:
                shutil.move(str(item), str(dst))
        elif item.suffix.lower() == ".csv":
            if not DRY:
                listdir.mkdir(exist_ok=True)
                shutil.move(str(item), str(listdir / item.name))
    if not DRY:
        try:
            FLAT.rmdir()
        except OSError:
            pass


def patch_atlas(atlas: pathlib.Path, page: str) -> bool:
    text = atlas.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return False
    if lines[0].strip() == page:
        return False
    lines[0] = page
    if not DRY:
        atlas.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def render_frame(model_dir: pathlib.Path, name: str, out: pathlib.Path) -> bool:
    if DRY:
        print("      would render", out.name)
        return True
    cmd = ["node", "render_static.mjs", str(model_dir), name, str(out), str(SIZE), "1.2"]
    p = subprocess.run(cmd, cwd=str(RUNTIME), capture_output=True, text=True, timeout=120)
    if p.returncode != 0 or not out.exists():
        print("      RENDER FAIL", p.stderr.strip()[:200])
        return False
    try:
        print("      rendered", json.loads(p.stderr.strip().splitlines()[-1]).get("model"))
    except Exception:
        pass
    return True


def main() -> None:
    print("== flatten ==")
    flatten()

    print("== preserve composed Marian_01 ==")
    old = CG / "玛丽安活动剧情" / "EventScene_Marian_01.png"
    if old.exists() and not PRESERVED.exists() and not DRY:
        shutil.copy2(old, PRESERVED)
        print("  preserved", PRESERVED.stat().st_size // 1024, "KB")

    index = {}
    for f in CG.rglob("*.png"):
        rel = f.relative_to(CG)
        first = rel.parts[0] if rel.parts else ""
        if first == "全量分类" and len(rel.parts) > 1:
            first = rel.parts[1]
        if not first[:1].isdigit():
            continue
        if f.name.endswith(".spine.png"):
            continue
        index.setdefault(f.stem.lower(), f)

    models_root = MODELS if MODELS.exists() else LEGACY_MODELS
    if not models_root.exists():
        print("no staging models; nothing to merge")
        return
    models = sorted(d for d in models_root.iterdir() if d.is_dir())
    print(f"== models {len(models)} ==")
    done = rendered = 0
    for d in models:
        name = d.name
        sheet = d / (name + ".png")
        atlas = d / (name + ".atlas")
        skel = d / (name + ".skel")
        if not (sheet.exists() and atlas.exists() and skel.exists()):
            print("  ! incomplete", name)
            continue

        target = index.get(name.lower())
        if target is None:
            from cg_paths import classify
            dest_dir = CG / classify(name)
        else:
            dest_dir = target.parent
        if DRY:
            print(f"  {name}: -> {dest_dir.relative_to(CG)}")
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        spine_png = dest_dir / f"{name}.spine.png"
        illusion = dest_dir / f"{name}.png"

        composed = False
        if illusion.exists():
            same = md5(illusion) == md5(sheet)
            if same:
                illusion.rename(spine_png)
            else:
                composed = True
                if not spine_png.exists():
                    sheet.replace(spine_png)
        else:
            sheet.replace(spine_png)

        patch_atlas(atlas, spine_png.name)
        atlas.replace(dest_dir / atlas.name)
        skel.replace(dest_dir / skel.name)

        if not illusion.exists():
            if name.lower() == "eventscene_marian_01" and PRESERVED.exists():
                shutil.copy2(PRESERVED, illusion)
                print(f"  {name}: restored composed frame")
            else:
                ok = render_frame(dest_dir, name, illusion)
                rendered += 1 if ok else 0
        elif composed:
            pass
        done += 1

        try:
            d.rmdir()
        except OSError:
            print("  ! leftover in", d)

    print(f"processed {done}, rendered {rendered}")
    if PRESERVED.exists() and not DRY:
        PRESERVED.unlink()


if __name__ == "__main__":
    main()
