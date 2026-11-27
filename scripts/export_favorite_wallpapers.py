"""Export Favorite Item wallpapers and map them to their treasure stories.

Source bundles are favoriteitemwallpaper(hd)_assets_favoriteitem/favoriteitemscene_*.
Unlike story CGs, their Spine models are named FavoriteItemScene_*, so the
EventScene_* exporter never sees them. FavoriteItemQuestTable and
FavoriteItemQuestStageTable provide the wallpaper -> treasurestory_* mapping.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import time

import UnityPy
import zstandard as zstd

import export_cg_v2 as v2

BASE = pathlib.Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
STAGING = BASE / "staging"
OUT = BASE / "CG" / "07_珍藏品CG"
RUNTIME = BASE / "动态CG" / "runtime"
META = STAGING / "favorite_wallpapers.json"
TOKEN = re.compile(rb"[ -~]{4,}")
WALLPAPER = re.compile(r"mi_favoriteitem_wallpaper_(c\d{3})_(\d{2})")
QUEST_NAME = re.compile(r"Locale_SubQuest:FAVORITE_QUEST_NAME_(\d+)")
QUEST_DESC = re.compile(r"Locale_SubQuest:FAVORITE_QUEST_DESC_(\d+)")
STORY = re.compile(r"(treasurestory_[a-z]+_\d+(?:_[se])?)")
STAGE = re.compile(r"Locale_Stage:(\d+)_name")
STORY_GROUPS = {
    p.name.split(".", 1)[1][:-4]
    for p in STATIC.glob("AttractiveScenarioDialogTable.treasurestory_*.mpk")
}


def clean_story(token: str) -> str:
    match = STORY.match(token)
    if not match:
        return ""
    exact = [g for g in STORY_GROUPS if token.startswith(g)]
    return max(exact, key=len) if exact else match.group(1)


def tokens(path: pathlib.Path) -> list[str]:
    return [m.group().decode("ascii", "replace") for m in TOKEN.finditer(path.read_bytes())]


def locale_rows() -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = {}
    for path in sorted((BASE / "decrypted").glob("*.dec")):
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("Locale_SubQuest", "Locale_Stage"):
                if table not in tables:
                    continue
                slot = out.setdefault(table, {})
                for key, en, ko, ja, zh in con.execute(
                    f'SELECT Key, en, ko, ja, "zh-CN" FROM "{table}"'
                ):
                    values = {"zh": zh or "", "en": en or "", "ko": ko or "", "ja": ja or ""}
                    if any(values.values()):
                        slot[key] = values
            con.close()
        except sqlite3.Error:
            continue
    return out


def story_sort(group: str) -> tuple:
    m = re.match(r"treasurestory_[a-z]+_(\d+)(?:_([se]))?$", group)
    if not m:
        return (10**9, group)
    return (int(m.group(1)), {"s": 0, "": 1, "e": 2}.get(m.group(2) or "", 1))


def parse_mapping(locales: dict) -> list[dict]:
    records: list[dict] = []
    current = None
    wallpaper = ""
    for token in tokens(STATIC / "FavoriteItemQuestTable.mpk"):
        match = WALLPAPER.fullmatch(token)
        if match:
            wallpaper = token
            continue
        match = QUEST_NAME.match(token)
        if match:
            quest_id = match.group(1)
            current = {
                "id": quest_id,
                "wallpaper": wallpaper,
                "storyGroups": [],
                "names": locales.get("Locale_SubQuest", {}).get(f"FAVORITE_QUEST_NAME_{quest_id}", {}),
                "titles": locales.get("Locale_SubQuest", {}).get(f"FAVORITE_QUEST_DESC_{quest_id}", {}),
                "source": "quest",
            }
            records.append(current)
            continue
        if current is None:
            continue
        match = QUEST_DESC.match(token)
        if match:
            quest_id = match.group(1)
            current["titles"] = locales.get("Locale_SubQuest", {}).get(
                f"FAVORITE_QUEST_DESC_{quest_id}", {}
            )
            continue
        match = STORY.match(token)
        if match:
            group = clean_story(token)
            current["storyGroups"].append(group)

    by_code = {}
    for record in records:
        match = WALLPAPER.fullmatch(record["wallpaper"])
        if not match:
            raise ValueError(f" quest without wallpaper: {record}")
        code, variant = match.groups()
        item = by_code.setdefault(code, {
            "name": f"FavoriteItemScene_{code}_{variant}",
            "characterCode": code,
            "variant": variant,
            "thumbnail": record["wallpaper"],
            "storyBucket": "",
            "storyGroups": [],
            "quests": [],
            "stages": [],
        })
        item["quests"].append(record)
        for group in record["storyGroups"]:
            if group not in item["storyGroups"]:
                item["storyGroups"].append(group)
            slug = re.match(r"(treasurestory_[a-z]+)_\d+", group)
            if slug:
                item["storyBucket"] = slug.group(1)

    stage_tokens = tokens(STATIC / "FavoriteItemQuestStageTable.mpk")
    stage_id = ""
    for token in stage_tokens:
        match = STAGE.fullmatch(token)
        if match:
            stage_id = match.group(1)
            continue
        story = STORY.match(token)
        if not stage_id or not story:
            continue
        group = clean_story(token)
        slug = re.match(r"(treasurestory_([a-z]+))_\d+", group)
        if not slug:
            continue
        item = next((v for v in by_code.values() if v["storyBucket"] == slug.group(1)), None)
        if item is None:
            raise ValueError(f" stage story has no wallpaper: {group}")
        item["stages"].append({
            "id": stage_id,
            "storyGroups": [group],
            "names": locales.get("Locale_Stage", {}).get(f"{stage_id}_name", {}),
            "source": "stage",
        })
        if group not in item["storyGroups"]:
            item["storyGroups"].append(group)

    result = []
    for code, item in sorted(by_code.items()):
        item["storyGroups"].sort(key=story_sort)
        item["modelPath"] = f"CG/07_珍藏品CG/{item['name']}/{item['name']}"
        result.append(item)
    return result


def text_bytes(obj) -> bytes:
    value = obj.read().m_Script
    if isinstance(value, str):
        return value.encode("utf-8", "surrogateescape")
    return bytes(value or b"")


def atlas_pages(text: str) -> list[str]:
    pages = []
    for block in re.split(r"\n\s*\n", text):
        first = block.strip().splitlines()[0].strip() if block.strip() else ""
        if first and ":" not in first:
            pages.append(first)
    return pages


def export_model(cat, table, cdb, dec, item: dict, force: bool, skip_render: bool) -> dict:
    code, variant = item["characterCode"], item["variant"]
    pattern = f"favoriteitemwallpaper(hd)_assets_favoriteitem/favoriteitemscene_{code}_{variant}_"
    rows = cat.execute("SELECT file_id, key FROM files_chunktype WHERE key LIKE ?", (pattern + "%",)).fetchall()
    if len(rows) != 1:
        raise ValueError(f"expected one HD bundle for {item['name']}, got {len(rows)}")
    file_id, key = rows[0]
    bundle, parts, missing = v2.rebuild(cat, table, cdb, dec, file_id, cdb.stat().st_size)
    if missing or not bundle or not bundle.startswith(b"UnityFS"):
        raise ValueError(f"incomplete bundle: missing={missing}, parts={parts}")

    env = UnityPy.load(io.BytesIO(bundle))
    assets = {}
    textures = {}
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            name = str(getattr(obj.read(), "m_Name", "") or "")
            if name.endswith((".atlas", ".skel")):
                assets[name] = obj
        elif obj.type.name == "Texture2D":
            data = obj.read()
            textures[str(getattr(data, "m_Name", "") or "")] = data

    base = item["name"]
    if base + ".atlas" not in assets or base + ".skel" not in assets:
        raise ValueError("missing atlas/skel")
    atlas_text = text_bytes(assets[base + ".atlas"]).decode("utf-8", "replace")
    atlas_text = atlas_text.replace("\r\n", "\n").replace("\r", "\n")
    pages = atlas_pages(atlas_text)
    if not pages:
        raise ValueError("atlas has no page")

    folder = OUT / base
    folder.mkdir(parents=True, exist_ok=True)
    page_files = []
    replacements = {}
    for index, page in enumerate(pages):
        texture_name = page[:-4] if page.lower().endswith(".png") else page
        if texture_name not in textures:
            raise ValueError(f"missing atlas texture: {texture_name}")
        stem = pathlib.Path(page).stem
        output_stem = base if index == 0 else stem
        filename = output_stem + ".spine.png"
        image = textures[texture_name].image
        if not isinstance(image, v2.Image.Image):
            image = image.convert("RGBA")
        image.save(folder / filename)
        replacements[page] = filename
        page_files.append(filename)

    for old, new in replacements.items():
        atlas_text = atlas_text.replace(old, new)
    (folder / (base + ".atlas")).write_bytes(atlas_text.encode("utf-8"))
    (folder / (base + ".skel")).write_bytes(text_bytes(assets[base + ".skel"]))

    still = folder / (base + ".png")
    rendered = False
    error = ""
    if not skip_render and (force or not still.exists()):
        proc = subprocess.run(
            ["node", "render_static.mjs", pathlib.Path(os.path.relpath(folder, RUNTIME)).as_posix(),
             base, pathlib.Path(os.path.relpath(still, RUNTIME)).as_posix(), "2048", "1.2"],
            cwd=str(RUNTIME), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180,
        )
        if proc.returncode or not still.exists():
            error = (proc.stderr or proc.stdout).strip()[-500:]
        else:
            rendered = True
    return {
        **item,
        "bundle": key,
        "chunks": parts,
        "missingChunks": missing,
        "pages": page_files,
        "still": str(still.relative_to(BASE)).replace("\\", "/") if still.exists() else "",
        "rendered": still.exists(),
        "renderError": error,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="character codes, comma separated")
    parser.add_argument("--force", action="store_true", help="rerender existing stills")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    mapping = parse_mapping(locale_rows())
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        mapping = [x for x in mapping if x["characterCode"] in wanted]
    OUT.mkdir(parents=True, exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)

    cat = sqlite3.connect(v2.manifest_path("dp"))
    table = v2.cidx_map("dp")
    cdb = v2.ROOT / "dp" / "chunk" / "store.cdb"
    dec = zstd.ZstdDecompressor()
    results = []
    started = time.time()
    for i, item in enumerate(mapping, 1):
        try:
            result = export_model(cat, table, cdb, dec, item, args.force, args.skip_render)
        except Exception as exc:
            result = {**item, "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(f"[{i}/{len(mapping)}] {item['name']} "
              f"{'ERROR ' + result['error'] if result.get('error') else 'OK'}", flush=True)

    previous = {}
    if META.exists():
        saved = json.loads(META.read_text(encoding="utf-8"))
        previous = {x["name"]: x for x in saved.get("items", [])}
    previous.update({x["name"]: x for x in results})
    results = [previous[k] for k in sorted(previous)]
    META.write_text(json.dumps({
        "total": len(results),
        "storyGroups": len({g for x in results for g in x["storyGroups"]}),
        "items": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"metadata: {META}")
    print(f"exported={sum(not x.get('error') for x in results)} "
          f"rendered={sum(x.get('rendered') for x in results)} "
          f"elapsed={time.time() - started:.1f}s")
    if any(x.get("error") or x.get("renderError") for x in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
