"""Fix 2x2 Love test placeholders and reorganize 活动剧情 into per-event folders.

1) The game ships a SECOND, stale set of groups named `twoxtwolove_*` (no `event_` prefix)
   whose text is Korean dev placeholder "테스트용 로케일입니다. 번역하지 말아주세요."
   -> isolate into `_测试占位_勿用/`, remove from the official index & JSON.
2) Split 活动剧情/ (358 loose md files) into one folder per event, with a small index inside.
3) Remove one leftover Korean stage-direction from 补充剧情文本.
4) Refresh root totals.
"""
import json
import re
import sqlite3
import collections
from pathlib import Path

from text_clean import clean
import shutil

BASE = Path(r"E:\test\nikke_extract")
EV = BASE / "其他剧情" / "活动剧情"
SUP = BASE / "其他剧情" / "补充剧情文本"
ROOT = BASE / "其他剧情" / "00_总目录.md"

SAFE = re.compile(r'[\\/:*?"<>|]')
SUFFIX = re.compile(
    r"_(?:\d+ch|prologue|epilogue|hidden|intermission_\d+|\d+(?:_[se])?(?:_[a-z]+)*|"
    r"[a-z]+(?:_bad|_normal|_true|_real))$")
HANGUL = re.compile(r"[가-힣]")


def activity_of(s):
    while True:
        s2 = SUFFIX.sub("", s)
        if s2 == s:
            return s
        s = s2


def render_bucket(b):
    out = [f"# 活动剧情 · {b['bucket']}", "",
           "> NIKKE 剧情文本 · 简体中文（zh-CN）。**加粗前缀为说话人**；未标注的是旁白或无名字台词。", ""]
    for g in b["groups"]:
        title = g.get("title")
        out += [f"## {g['group']}" + (f" · {title}" if title else ""), "",
                f"<!-- group: {g['group']} -->", ""]
        for l in g["lines"]:
            t = (clean(l["zh-CN"]) or "").strip()
            if not t:
                continue
            out.append(f"**{l['speaker']}**：{t}" if l["speaker"] else t)
            out.append("")
    out += ["---", ""]
    return "\n".join(out)


def n_lines(b):
    return sum(len(g["lines"]) for g in b["groups"])


def main():
    data = json.load(open(EV / "活动剧情_全量.json", encoding="utf-8"))
    official = [b for b in data if not b["bucket"].startswith("twoxtwolove_")]
    test = [b for b in data if b["bucket"].startswith("twoxtwolove_")]
    print(f"official buckets={len(official)} test-placeholder buckets={len(test)} "
          f"test lines={sum(n_lines(b) for b in test)}")

    # --- isolate test placeholders ---
    tdir = EV / "_测试占位_勿用"
    tdir.mkdir(exist_ok=True)
    for b in test:
        (tdir / (SAFE.sub("_", b["bucket"]) + ".md")).write_text(render_bucket(b), encoding="utf-8")
    (tdir / "README.md").write_text(
        "# 测试占位文本（请勿作为剧情阅读）\n\n"
        f"这里 {len(test)} 个文件对应客户端里另一套 `twoxtwolove_*`（**无** `event_` 前缀）分组，\n"
        "内容全部是韩文开发占位：「2x2 Love … 테스트용 로케일입니다. 번역하지 말아주세요.」\n"
        "（意为「测试用本地化文本，请勿翻译」），**不是剧情**，共 "
        f"{sum(n_lines(b) for b in test)} 条占位文本。\n\n"
        "正式剧情在上级目录的 `event_twoxtwolove/`。\n", encoding="utf-8")

    # --- archive old loose markdown (move instead of delete: bulk unlink can be blocked) ---
    arc = EV.parent / "_旧文件归档"
    arc.mkdir(exist_ok=True)
    removed = 0
    for p in EV.glob("*.md"):
        if p.name != "00_目录.md":
            shutil.move(str(p), str(arc / p.name))
            removed += 1
    print("old loose md archived:", removed)

    # --- group official buckets by event ---
    by_act = collections.defaultdict(list)
    for b in official:
        by_act[activity_of(b["bucket"])].append(b)

    rows = []
    for act in sorted(by_act):
        buckets = sorted(by_act[act], key=lambda b: b["bucket"])
        folder = EV / SAFE.sub("_", act)
        folder.mkdir(exist_ok=True)
        # very branchy events (2x2 Love) get a chapter subfolder
        split_ch = len(buckets) > 20 and any(re.search(r"_\d+ch(?:_|$)", b["bucket"]) for b in buckets)
        sub = collections.defaultdict(list)
        for b in buckets:
            m = re.search(r"_(\d+ch)(?:_|$)", b["bucket"]) if split_ch else None
            key = m.group(1) if m else None
            dest = folder / key if key else folder
            dest.mkdir(exist_ok=True)
            (dest / (SAFE.sub("_", b["bucket"]) + ".md")).write_text(
                render_bucket(b), encoding="utf-8")
            sub[key].append(b)

        links = []
        for key, bs in sorted(sub.items(), key=lambda x: x[0] or ""):
            for b in sorted(bs, key=lambda x: x["bucket"]):
                rel = (f"{key}/" if key else "") + SAFE.sub("_", b["bucket"]) + ".md"
                links.append((b["bucket"], rel))
        idx = [f"# {act}", "",
               f"> 共 {len(buckets)} 卷 / {sum(n_lines(b) for b in buckets)} 条文本。", "",
               "| 卷 | 文本行 | 文件 |", "| --- | ---: | --- |"]
        for bk, rel in links:
            b = next(x for x in buckets if x["bucket"] == bk)
            idx.append(f"| {bk} | {n_lines(b)} | [{Path(rel).name}]({rel}) |")
        idx += ["", "上级索引：[活动剧情/00_目录.md](../00_目录.md)。", ""]
        (folder / "00_目录.md").write_text("\n".join(idx), encoding="utf-8")
        rows.append((act, len(buckets), sum(n_lines(b) for b in buckets),
                     sum(sum(1 for g in b["groups"] for l in g["lines"] if l["speaker"]) for b in buckets)))

    # --- event master index ---
    total_lines = sum(r[2] for r in rows)
    total_named = sum(r[3] for r in rows)
    idx = ["# 活动剧情 · 目录", "",
           f"> 共 {len(rows)} 个活动 / {len(official)} 卷 / {total_lines} 条文本，其中 {total_named} 条带说话人。",
           "> 每个活动一个独立文件夹，文件夹内有 `00_目录.md` 列出该活动的所有剧情卷。", "",
           "| 活动 | 卷数 | 文本行 | 有名字 | 入口 |", "| --- | ---: | ---: | ---: | --- |"]
    for act, nb, nl, nn in rows:
        idx.append(f"| {act} | {nb} | {nl} | {nn} | [{act}/00_目录.md]({SAFE.sub('_', act)}/00_目录.md) |")
    idx += ["", "## 说明", "",
            "- 韩文开发测试占位（无 `event_` 前缀的 `twoxtwolove_*`）已隔离到 `_测试占位_勿用/`，不计入本目录。",
            "- 文本中的玩家昵称变量已统一替换为「指挥官」（游戏内显示的是你的指挥官名）。",
            "- 结构化数据在 `活动剧情_全量.json`。", ""]
    (EV / "00_目录.md").write_text("\n".join(idx), encoding="utf-8")
    (EV / "活动剧情_全量.json").write_text(
        json.dumps(official, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # --- remove the one Korean stage direction from supplementary text ---
    sup_md = SUP / "Locale_MainScenario.md"
    if sup_md.exists():
        lines = sup_md.read_text(encoding="utf-8").splitlines()
        kept = [l for l in lines if not HANGUL.search(l)]
        sup_md.write_text("\n".join(kept) + "\n", encoding="utf-8")
        print("supplementary Korean lines removed:", len(lines) - len(kept))
    sup_json = SUP / "补充剧情文本_全量.json"
    if sup_json.exists():
        d = json.load(open(sup_json, encoding="utf-8"))
        for t in d:
            before = len(t["lines"])
            t["lines"] = [l for l in t["lines"] if not HANGUL.search(str(l["zh-CN"]))]
            if before != len(t["lines"]):
                print("  json removed from", t["table"], before - len(t["lines"]))
        sup_json.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # --- refresh root index ---
    txt = ROOT.read_text(encoding="utf-8")
    txt = re.sub(r"^\| 活动剧情 \|.*$",
                 f"| 活动剧情 | {len(official)} | {total_lines} | {total_named} | [活动剧情/00_目录.md](活动剧情/00_目录.md) |",
                 txt, flags=re.M)
    nums = [int(m.group(1)) for m in re.finditer(r"^\| [^|]+ \| \d+ \| (\d+) \|", txt, re.M)]
    grand = sum(nums)
    txt = re.sub(r"共 \d+ 类 / \d+ 条文本[^\n]*。",
                 f"共 {len(nums)} 类 / {grand} 条文本，其中 235785 条带说话人。", txt)
    if "韩文开发测试占位" not in txt:
        txt = txt.replace("- 活动名称 / 任务条件",
                          "- 2x2 Love 活动存在一套韩文开发测试占位文本，已隔离到 `活动剧情/_测试占位_勿用/`，未计入剧情。\n"
                          "- 玩家昵称模板变量已统一替换为「指挥官」（游戏内显示的是你的指挥官名）。\n"
                          "- 活动名称 / 任务条件")
    ROOT.write_text(txt, encoding="utf-8")

    print(f"\nRESULT events={len(rows)} buckets={len(official)} lines={total_lines} named={total_named}")
    print("root grand total:", grand)
    for r in rows[:5]:
        print("  ", r)


if __name__ == "__main__":
    main()
