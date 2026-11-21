"""最终三方核对：catalog ↔ CG 成品库 ↔ 剧情↔CG 索引。

数据源（全部本地产物）：
  _cg_audit/full_hd_scan.json      catalog 可重建 HD 纹理全量扫描（audit5 产出）
  _cg_audit/story_refs.json        独立逐行扫描的 Dialog 表 CG 引用（audit 产出）
  _cg_audit/non_dialog_refs.json   非 Dialog 族（图鉴/壁纸/文字冒险页）引用
  CG索引/剧情CG对照索引.json        新管线（剧情 JSON 单一事实源）产出的索引

核对项：
  1. catalog 纹理 vs CG/ 文件      -> 提取完备性
  2. 独立扫描 vs 新索引 (台词ID,CG) -> 映射一致性（相邻重复声明按口径豁免）
  3. 索引缺失引用                  -> 环境性缺口清单
  4. 图鉴（LiveWallpaper）清单     -> CG索引/图鉴清单.csv
输出 _cg_audit/final_report.md
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
AUD = BASE / "_cg_audit"
CGI = BASE / "CG索引"

out = []
def p(s=""):
    out.append(str(s))
    print(s)

# ---------- 1. catalog 纹理 vs CG/ 文件 ----------
scan = json.loads((AUD / "full_hd_scan.json").read_text(encoding="utf-8"))
lib = {}
for f in (BASE / "CG").rglob("*.png"):
    if f.name.endswith(".spine.png"):
        continue
    lib.setdefault(f.stem.lower(), f.relative_to(BASE).as_posix())

results = scan.get("results") or []
missing_in_lib = []
for r in results:
    textures = r.get("textures") or []
    for t in textures:
        name = (t if isinstance(t, str) else t.get("name", "")).lower()
        if name.startswith("eventscene_") and name not in lib:
            missing_in_lib.append(name)
p("## 1. catalog ↔ CG 成品库")
p(f"- catalog 可重建 bundle：{scan['stats'].get('bundles_ok')}，已存在 {scan['stats'].get('already_present')}，本次补提 {scan['stats'].get('exported')}")
p(f"- EventScene_* 纹理在库缺失：**{len(missing_in_lib)}** {missing_in_lib[:8]}")
spine_atlas = {a.stem.lower() for a in (BASE / "CG").rglob("*.atlas")}
p(f"- CG 库内静态插画 {sum(1 for k in lib)} 张，动态 CG（atlas）{len(spine_atlas)} 组")
p()

# ---------- 2. 独立扫描 vs 新索引 ----------
idx = json.loads((CGI / "剧情CG对照索引.json").read_text(encoding="utf-8"))
my_pairs = {(r["台词ID"], r["CG名"]) for r in idx}
refs = json.loads((AUD / "story_refs.json").read_text(encoding="utf-8"))
agent_pairs = set()
agent_lines = defaultdict(list)      # file -> [(line_no, cgs)]
agent_line_of_pair = {}
for e in refs:
    lk = e.get("locale_key") or ""
    key = lk.split(":", 1)[1] if ":" in lk else lk
    for cg in e.get("cg") or []:
        agent_pairs.add((key, cg))
        agent_line_of_pair[(key, cg)] = (e.get("file"), e.get("line_no"))
    agent_lines[e.get("file")].append((e.get("line_no"), tuple(e.get("cg") or [])))

only_agent = agent_pairs - my_pairs
only_my = my_pairs - agent_pairs

# 口径豁免：相邻行重复声明同一 CG（屏幕未切换）不算映射缺口
def is_repeat(pair):
    fl = agent_line_of_pair.get(pair)
    if not fl:
        return False
    fname, ln = fl
    seq = sorted(agent_lines.get(fname, []))
    prev_cgs = None
    for n, cgs in seq:
        if n == ln:
            return prev_cgs is not None and set(cgs) == set(prev_cgs)
        prev_cgs = cgs
    return False

repeats = {pr for pr in only_agent if is_repeat(pr)}
real_miss = only_agent - repeats

p("## 2. 独立逐行扫描 ↔ 新索引")
p(f"- 独立扫描 (台词ID,CG) 对：{len(agent_pairs)}；新索引：{len(my_pairs)}")
p(f"- 索引有扫描无：{len(only_my)}")
for pr in sorted(only_my)[:10]:
    p(f"  - `{pr[0]}` → `{pr[1]}`")
p(f"- 扫描有索引无：{len(only_agent)}，其中相邻重复声明（口径豁免）{len(repeats)}，**真实差异 {len(real_miss)}**")
for pr in sorted(real_miss)[:25]:
    fl = agent_line_of_pair.get(pr)
    p(f"  - `{pr[0]}` → `{pr[1]}`  ({fl[0]}:{fl[1]})")
p()

# ---------- 3. 环境性缺口 ----------
missing_by = Counter(r["CG名"] for r in idx if r["匹配"] == "缺失")
p("## 3. 引用但客户端无资源的 CG（环境性缺口）")
p(f"- 共 {len(missing_by)} 名 / {sum(missing_by.values())} 处引用：")
for k, v in sorted(missing_by.items()):
    p(f"  - `{k}` ×{v}")
approx = Counter(r["CG名"] for r in idx if r["匹配"] == "近似")
p(f"- 近似匹配（差分名落到基础图，icedragonsaga 客户端只有 SD 等）：{len(approx)} 名 / {sum(approx.values())} 处")
p()

# ---------- 4. 图鉴（LiveWallpaper）清单 ----------
# 壁纸表引用的 CG 名带 _mi/_si spine 变体后缀，本体与剧情 CG 同名（不带后缀）。
# 按「剥掉变体后缀 -> 基础 CG」解析可用性，并关联 core 池的壁纸 bundle。
inv = json.loads((AUD / "inventory.json").read_text(encoding="utf-8"))
wall_bundles = {}
for b in (inv.get("pools", {}).get("core", {}).get("bundles") or []):
    if "livewallpaper" in b.get("key", "").lower():
        wall_bundles[b.get("identity", "")] = b["key"]
ndr = json.loads((AUD / "non_dialog_refs.json").read_text(encoding="utf-8"))
lw = defaultdict(list)
for e in ndr:
    if e["family"] == "LiveWallpaperTable":
        lw[e["cg"]].append(e)

def base_of(name: str) -> tuple[str, str]:
    """(基础CG名, 变体)；无变体时变体为空。"""
    m = re.match(r"^(EventScene_.+?)_(mi|si)$", name)
    if m:
        return m.group(1), m.group(2)
    return name, ""

bases = {}
for cg, es in lw.items():
    base, variant = base_of(cg)
    b = bases.setdefault(base, {"refs": 0, "variants": set()})
    b["refs"] += len(es)
    b["variants"].add(variant or "base")

rows_out = []
for base, info in sorted(bases.items()):
    low = base.lower()
    ident = low[len("eventscene_"):]
    static = lib.get(low, "")
    dynamic = next((a for a in spine_atlas if a == low), "")
    rows_out.append({
        "基础CG名": base,
        "变体": "+".join(sorted(info["variants"])),
        "壁纸引用次数": info["refs"],
        "静态图": static,
        "动态CG": dynamic,
        "壁纸bundle": wall_bundles.get(ident, ""),
    })
CGI.mkdir(exist_ok=True)
with (CGI / "图鉴清单.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["基础CG名", "变体", "壁纸引用次数", "静态图", "动态CG", "壁纸bundle"])
    w.writeheader()
    for r in rows_out:
        w.writerow(r)
no_art = [r["基础CG名"] for r in rows_out if not r["静态图"] and not r["动态CG"]]
no_bundle = [r["基础CG名"] for r in rows_out if not r["壁纸bundle"]]
p("## 4. 游戏内图鉴（LiveWallpaperTable）")
p(f"- 壁纸引用的 CG 名 {len(lw)} 个（含 _mi/_si 变体），解析为基础 CG {len(bases)} 个 -> CG索引/图鉴清单.csv")
p(f"- 基础 CG 既无静态图也无动态模型：{len(no_art)} {no_art[:10]}")
p(f"- core 池无对应壁纸 bundle：{len(no_bundle)} {no_bundle[:10]}")
p("- 说明：壁纸的 spine 动态模型（livewallpaperprefabs bundle）本工程未提取，静态原图与剧情 CG 共用已全部入库。")
p()

(AUD / "final_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\nwritten", AUD / "final_report.md")
