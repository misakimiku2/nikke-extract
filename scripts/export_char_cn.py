"""从国服 WeGame 客户端提取指定角色的全部资源（含 NKAB v4 解密）。

国服（胜利女神：新的希望，com_tencent）资源结构与国际服 com.shiftup.patch 完全不同：
  - 主资源池在 <游戏>/nikke_Data/runtime_data/cache/<outer>/<内容哈希>，
    内容哈希 = bundle 文件名末尾 32 hex；文件为 NKAB v4 加密（decrypt_nkab_cn.py 解）
  - bundle 清单不在游戏目录，而在
    %LOCALAPPDATA%/Low/com_tencent/胜利女神：新的希望/com.unity.addressables/*.json
    （Unity Addressables 目录，internalIds 含 bundle 相对路径）
  - 角色中文名 → ID: runtime_data/saus/saus/lss/Locale_Character.lss（明文 SQLite）

用法:
    python scripts/export_char_cn.py --id 8004            # 按角色 ID
    python scripts/export_char_cn.py --name 婴宁           # 按中文名反查 ID
    python scripts/export_char_cn.py --list                # 列出可提取的 CN 新角色
    python scripts/export_char_cn.py --id 8004 --kinds stand,combat,skillcut,icons

输出（BASE = nikke_extract 根）:
    staging/spine_stand/<c8004_00>/       站姿 Spine（atlas/skel/png，同 export_char_standing）
    staging/spine_combat/c8004_aim_00/    战斗姿态（同 export_char_combat）
    staging/spine_char/c8004_00_skillcut/ 大招 cut-in Spine + bg.png 场景层
                                          （同 export_char_cutins；跑 build/build_char_spine.py
                                           即进网站 public/spine_skillcut/）
    staging/cn_icons/c8004_00*.png        全身立绘/小图标
    staging/cn_sfx/<c8004>/               音频/语音 bundle（AudioClip 名单见 _objects.txt）

kinds 说明:
    stand      spinestandingcharactergroup   站姿
    combat     spinecombatcharactergroup     aim/cover 战斗姿态
    skillcut   spotskillcutscene + livewallpaperprefabs   大招 cut-in（Spine+场景层）
    icons      icons-char-full / icons-char-mi            立绘卡
    sd         sdcharacters                  SD 模型贴图
    sfx        sfx_assets_required / audiogrouppcsfx      音频（AudioClip，未解码）
    all        以上全部
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sqlite3
import sys
import time
import pathlib

import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decrypt_nkab_cn

BASE = pathlib.Path(__file__).resolve().parents[1]
GAME_ROOT = decrypt_nkab_cn.GAME_ROOT
_local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~") + "/AppData/Local")
AD_DIR = os.path.join(os.path.dirname(_local.rstrip("\\/") or _local), "LocalLow",
                      "com_tencent", "胜利女神：新的希望", "com.unity.addressables")
if not os.path.isdir(AD_DIR):  # 环境变量异常时的兜底
    AD_DIR = os.environ.get("NIKKE_CN_ADDR", AD_DIR)
CACHE = os.path.join(GAME_ROOT, "nikke_Data", "runtime_data", "cache")
LSS_CHAR = os.path.join(GAME_ROOT, "nikke_Data", "runtime_data", "saus", "saus",
                        "lss", "Locale_Character.lss")

TPL = re.compile(r"^\{[^}]*\}[\\/]?")
HASH = re.compile(r"_([0-9a-f]{32})\.bundle$")

CATALOG_COUNT = 7  # 当前版目录 JSON 份数（core/dp/fd/uc 各 main+hd 等）


def newest_catalogs() -> list[str]:
    files = glob.glob(os.path.join(AD_DIR, "*.json"))
    files.sort(key=os.path.getmtime, reverse=True)
    return files[:CATALOG_COUNT]


def resolve_target(args):
    """返回 (char_id, variant, code)。code = c082_80 / c8004_00 这类完整皮肤名。"""
    if args.code:
        m = re.match(r"^c(\d+)(?:_(\d+))?$", args.code)
        if not m:
            sys.exit(f"--code 格式应为 c082_80 或 c8004: {args.code}")
        char_id, variant = int(m.group(1)), m.group(2) or "00"
        return char_id, variant, f"c{m.group(1)}_{variant}"
    if args.id:
        variant = args.variant or "00"
        char_id = int(args.id)
        return char_id, variant, f"c{char_id:04d}_{variant}" if char_id < 10000 \
            else f"c{char_id}_{variant}"
    if args.name:
        con = sqlite3.connect(LSS_CHAR)
        rows = con.execute(
            "select Key, \"zh-CN\" from Locale_Character where \"zh-CN\" = ? and Key like '%_name'",
            (args.name,)).fetchall()
        con.close()
        if not rows:
            sys.exit(f"Locale_Character.lss 里找不到 {args.name}")
        key = rows[0][0]
        char_id = int(re.match(r"(\d+)_name", key).group(1))
        variant = args.variant or "00"
        code = f"c{char_id:03d}_{variant}"
        return char_id, variant, code
    sys.exit("需要 --code / --id / --name")


def collect_inventory(char_id: int, variant: str | None = None) -> dict[str, str]:
    """bundle 相对路径 -> catalog 文件名（去重）。

    variant=None（角色默认皮肤）：匹配 c8004 / c8004_00；
    variant='80'（专属皮肤）：匹配 c082_80 与 c082/80 两种路径写法。
    """
    code = f"c{char_id:03d}"
    if variant and variant != "00":
        pat = re.compile(rf"{code}[/_]{variant}(?!\d)")
    else:
        pat = re.compile(rf"{code}(?!\d)")
    seen: dict[str, str] = {}
    for cat in newest_catalogs():
        d = json.load(open(cat, encoding="utf-8"))
        for i in d.get("m_InternalIds", []):
            name = TPL.sub("", i)
            if name.endswith(".bundle") and pat.search(name) and name not in seen:
                seen[name] = os.path.basename(cat)
    return seen


def build_hash_index() -> dict[str, str]:
    idx = {}
    for outer in os.listdir(CACHE):
        o = os.path.join(CACHE, outer)
        if not os.path.isdir(o):
            continue
        for sub in os.listdir(o):
            p = os.path.join(o, sub)
            if os.path.isfile(p):
                idx.setdefault(sub, p)
            elif os.path.isfile(os.path.join(p, "__data")):
                idx.setdefault(sub, os.path.join(p, "__data"))
    return idx


def category_of(name: str) -> str:
    group = name.split("_assets_")[0].replace("\\", "/").split("/")[-1]
    for key, cat in [
        ("spinestandingcharactergroup", "stand"),
        ("spinestandingprefabgroup", "stand_prefab"),
        ("spinecombatcharactergroup", "combat"),
        ("icons-char-full", "icons"),
        ("icons-char-mi", "icons"),
        ("sdcharacters", "sd"),
        ("spotskillcutscene", "skillcut"),
        ("livewallpaperprefabs", "skillcut"),
        ("gachaui", "gacha_ui"),
        ("effect-spot-player", "skill_fx"),
        ("scriptabledata-sound", "sound_data"),
        ("scriptabledata", "skill_data"),
        ("sfx", "sfx"),
        ("audiogrouppcsfx", "sfx"),
        ("audiogroupscenario", "sfx"),
        ("spotweapon", "weapon"),
    ]:
        if group.startswith(key):
            return cat
    return "other"


def text_bytes(obj) -> bytes:
    s = obj.read().m_Script
    if isinstance(s, str):
        return s.encode("utf-8", "surrogateescape")
    return bytes(s or b"")


def load_bundle(path: str):
    head = open(path, "rb").read(4)
    if head == b"NKAB":
        raw = open(path, "rb").read()
        dec, _h = decrypt_nkab_cn.decrypt(raw)
        return UnityPy.load(io.BytesIO(dec))
    return UnityPy.load(path)


def export_spine(env, dest: pathlib.Path, base_name: str | None = None) -> list[str]:
    """导出 TextAsset(.atlas/.skel) + Texture2D 图集页；base_name 用于统一命名"""
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for obj in env.objects:
        t = obj.type.name
        try:
            nm = str(getattr(obj.read(), "m_Name", "") or "")
        except Exception:
            continue
        try:
            if t == "TextAsset" and nm.endswith((".atlas", ".skel")):
                out_name = nm
                if base_name:
                    out_name = base_name + nm[nm.index("."):]
                (dest / out_name).write_bytes(text_bytes(obj))
                saved.append(out_name)
            elif t == "Texture2D":
                img = obj.read().image
                if img is None:
                    continue
                out_name = f"{nm}.png"
                if base_name and nm.endswith("_2") is False and nm != base_name \
                        and not nm.startswith(base_name):
                    out_name = f"{base_name}.png"
                img.convert("RGBA").save(dest / out_name)
                saved.append(out_name)
        except Exception as e:
            print(f"    [warn] {t} {nm}: {e}")
    return saved


def export_images(env, dest: pathlib.Path, prefix: str = "") -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for obj in env.objects:
        t = obj.type.name
        try:
            nm = str(getattr(obj.read(), "m_Name", "") or "")
        except Exception:
            continue
        try:
            if t == "Texture2D":
                img = obj.read().image
                if img is not None:
                    img.convert("RGBA").save(dest / f"{prefix}{nm}.png")
                    saved.append(f"{prefix}{nm}.png")
            elif t == "Sprite":
                img = obj.read().image
                if img is not None:
                    img.convert("RGBA").save(dest / f"{prefix}sprite_{nm}.png")
                    saved.append(f"{prefix}sprite_{nm}.png")
        except Exception:
            pass
    return saved


# 场景层： livewallpaper bundle 里的整图（BG/Glow/Leaf/mask）保留原名作 bg/演出层
SCENE_KEEP = re.compile(r"^(BG|Glow|Leaf|mask)$", re.I)


def export_skillcut(env_by_name: list, dest: pathlib.Path, own_prefix: str):
    """spotskillcutscene + livewallpaper 两个 bundle 合并导出。

    注意：cut_scene bundle 里可能同时打包多个角色的 skillcut TextAsset
    （c8004 的 bundle 里也有 c8005_00_skillcut），必须按前缀过滤，
    否则会互相覆盖 atlas/skel。own_prefix 形如 c8004_00_skillcut / c082_80_skillcut。
    """
    dest.mkdir(parents=True, exist_ok=True)
    other_skillcut = re.compile(r"^c\d+_\d+_skillcut\.(atlas|skel)$")
    for env, _src_name in env_by_name:
        for obj in env.objects:
            t = obj.type.name
            try:
                nm = str(getattr(obj.read(), "m_Name", "") or "")
            except Exception:
                continue
            try:
                if t == "TextAsset" and nm.endswith((".atlas", ".skel")):
                    if not nm.startswith(own_prefix + "."):
                        continue  # 其他角色的 skillcut，跳过
                    (dest / nm).write_bytes(text_bytes(obj))
                elif t == "Texture2D":
                    img = obj.read().image
                    if img is None:
                        continue
                    if nm.startswith(own_prefix):
                        img.convert("RGBA").save(dest / f"{nm}.png")  # 图集页
                    elif SCENE_KEEP.match(nm):
                        img.convert("RGBA").save(dest / f"{nm.lower()}.png")
                    elif not other_skillcut.match(nm):
                        img.convert("RGBA").save(dest / f"fx_{nm}.png")
                    # 其他角色的图集页跳过
            except Exception as e:
                print(f"    [warn] {t} {nm}: {e}")


def export_audio_inventory(env, dest: pathlib.Path, tag: str):
    """AudioClip 无法直接解码（需 fmod），导出解密 bundle + 名单供后续处理"""
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    for obj in env.objects:
        if obj.type.name == "AudioClip":
            try:
                names.append(str(obj.read().m_Name))
            except Exception:
                pass
    (dest / f"{tag}_clips.txt").write_text("\n".join(names), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", help="角色 ID（如 8004；配合 --variant，默认 00）")
    ap.add_argument("--name", help="角色中文名（如 婴宁）")
    ap.add_argument("--code", help="完整皮肤代码（如 c082_80 / c8004_00），优先于 --id/--name")
    ap.add_argument("--variant", default=None, help="皮肤段（默认 00）")
    ap.add_argument("--kinds", default="stand,combat,skillcut,icons",
                    help="逗号分隔: stand,combat,skillcut,icons,sd,sfx,all")
    ap.add_argument("--list", action="store_true", help="列出 CN 目录里国际服没有的新角色")
    args = ap.parse_args()

    if args.list:
        # 对照国际服 roster（staging/spine_stand 已有目录）
        have = set()
        for p in glob.glob(str(BASE / "staging" / "spine_stand" / "*")):
            have.add(os.path.basename(p).split("_")[0])
        ids = set()
        con = sqlite3.connect(LSS_CHAR)
        for (k,) in con.execute("select Key from Locale_Character where Key like '%_name'"):
            m = re.match(r"(\d+)_name", k)
            if m:
                ids.add(int(m.group(1)))
        con.close()
        news = sorted(i for i in ids if f"c{i}" not in have)
        print("Locale_Character.lss 中未在国际服 roster 的角色 ID:")
        print("  " + " ".join(str(i) for i in news))
        return

    char_id, variant, code = resolve_target(args)
    kinds = set(["stand", "combat", "skillcut", "icons", "sd", "sfx"] if args.kinds == "all"
                else args.kinds.split(","))
    cid = f"c{char_id:04d}"
    print(f"目标: {code}  kinds: {sorted(kinds)}")

    inv = collect_inventory(char_id, variant)
    idx = build_hash_index()
    n_hit = sum(1 for name in inv if (HASH.search(name) and HASH.search(name).group(1) in idx))
    print(f"bundle 清单: {len(inv)}，cache 命中: {n_hit}")

    t0 = time.time()
    dup_count: dict[str, int] = {}
    for name, cat_file in sorted(inv.items()):
        hsh = HASH.search(name)
        path = idx.get(hsh.group(1)) if hsh else None
        if not path:
            print(f"[缺缓存] {name}")
            continue
        cat = category_of(name)
        if cat not in kinds:
            continue
        try:
            env = load_bundle(path)
        except Exception as e:
            print(f"[解密失败] {name}: {str(e)[:70]}")
            continue
        base = re.sub(r"[\W]+", "_", name.split("_assets_")[-1])
        base = HASH.sub("", base)
        try:
            if cat == "stand":
                dest_key = f"stand/{code}"
                n = dup_count.get(dest_key, 0)
                dup_count[dest_key] = n + 1
                dest = BASE / "staging" / "spine_stand" / (code if n == 0 else f"{code}__dup{n}")
                if n:
                    print(f"  [!] 同名站姿出现第 {n+1} 份（美术修订版共存?），另存 {dest.name}")
                files = export_spine(env, dest, base_name=code)
            elif cat == "combat":
                m = re.search(r"spine/combat/.*/(aim|cover)_hd", name)
                pose = m.group(1) if m else "aim"
                model = f"{code.split('_')[0]}_{pose}_{variant}"   # c082_aim_80
                dest_key = f"combat/{model}"
                n = dup_count.get(dest_key, 0)
                dup_count[dest_key] = n + 1
                dest = BASE / "staging" / "spine_combat" / \
                    (model if n == 0 else f"{model}__dup{n}")
                if n:
                    print(f"  [!] 同名 {pose} 姿态出现第 {n+1} 份，另存 {dest.name}")
                files = export_spine(env, dest, base_name=model)
            elif cat == "skillcut":
                stem = code
                dest = BASE / "staging" / "spine_char" / f"{stem}_skillcut"
                envs = skillcut_envs.setdefault(stem, [])
                envs.append((env, name))
                continue
            elif cat == "icons":
                dest = BASE / "staging" / "cn_icons"
                files = export_images(env, dest)
            elif cat == "sd":
                dest = BASE / "staging" / "cn_sd" / code
                files = export_images(env, dest)
            elif cat == "sfx":
                dest = BASE / "staging" / "cn_sfx" / code
                export_audio_inventory(env, dest, base)
                (dest / f"{base}.bundle.dec").write_bytes(
                    decrypt_nkab_cn.decrypt(open(path, "rb").read())[0]
                    if open(path, "rb").read(4) == b"NKAB" else open(path, "rb").read())
                files = ["bundle"]
            else:
                dest = BASE / "staging" / "cn_misc" / code
                dest.mkdir(parents=True, exist_ok=True)
                (dest / f"{base}.bundle.dec").write_bytes(
                    decrypt_nkab_cn.decrypt(open(path, "rb").read())[0])
                files = ["bundle"]
            print(f"[{cat}] {name.split('_assets_')[-1]} -> {dest.relative_to(BASE)} "
                  f"({len(files)} files)  {time.time()-t0:.0f}s")
        except Exception as e:
            print(f"[导出失败] {name}: {str(e)[:80]}")

    # skillcut 合并导出（spotskillcutscene 的 Spine + livewallpaper 的场景层）
    for stem, envs in skillcut_envs.items():
        dest = BASE / "staging" / "spine_char" / f"{stem}_skillcut"
        export_skillcut(envs, dest, f"{stem}_skillcut")
        files = sorted(x.name for x in dest.iterdir())
        print(f"[skillcut] {stem} -> {dest.relative_to(BASE)} ({len(files)} files)")


skillcut_envs: dict[str, list] = {}

if __name__ == "__main__":
    main()
