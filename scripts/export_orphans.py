"""Catch-all export: scenario text rows that are NOT referenced by any DialogTable.

These belong to mini-game scenarios / text-adventure events / special chapter sequences
which use other tables (Event*ScenarioTable, etc.). Exports them so the text corpus is complete.
"""
import glob
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from text_clean import clean

BASE = Path(__file__).resolve().parents[1]
DEC = BASE / "decrypted"
OUT = BASE / "其他剧情" / "补充剧情文本"
ROOT_IDX = BASE / "其他剧情" / "00_总目录.md"

TABLES = [
    # scenario / narrative tables
    "Locale_MainScenario", "Locale_SubScenario", "Locale_NikkeEpisode",
    "Locale_Counseling", "Locale_SuddenMessage", "Locale_SuddenStory",
    "Locale_SideStory", "Locale_Memorial", "Locale_Lycoris", "Locale_SubQuest",
]
# Excluded on purpose (UI / names / descriptions, not narrative):
# Locale_Event, Locale_Trigger, Locale_MainQuest, Locale_Outpost
PLACEHOLDER = {"DNT", "none", "null", "-", ""}


def natkey(s):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def collect_used():
    used = defaultdict(set)
    for jf in glob.glob(str(BASE / "其他剧情" / "*" / "*_全量.json")):
        if "补充剧情文本" in jf:  # our own output, different schema
            continue
        for b in json.load(open(jf, encoding="utf-8")):
            for g in b["groups"]:
                for l in g["lines"]:
                    used[l["locale_table"]].add(l["key"])
    for jf in [BASE / "主线剧情" / "主线剧情_全量.json"]:
        for c in json.load(open(jf, encoding="utf-8"))["chapters"]:
            for s in c["sections"]:
                for l in s["lines"]:
                    used["Locale_MainScenario"].add(l["key"])
    d = json.load(open(BASE / "NIKKE_最新活动剧情_玛丽安_结构化.json", encoding="utf-8"))
    for c in d["chapters"]:
        for l in c["lines"]:
            used["Locale_MainScenario"].add(l["key"])
    return used


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    used = collect_used()
    dbmap = {}
    for p in DEC.glob("*.dec"):
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        for (t,) in c.execute("select name from sqlite_master where type='table'"):
            if t.startswith("Locale_"):
                dbmap[t] = str(p)
        c.close()

    rows = []
    all_rows = []
    for t in TABLES:
        if t not in dbmap:
            continue
        c = sqlite3.connect(f"file:{dbmap[t]}?mode=ro", uri=True)
        data = list(c.execute(f'SELECT "Key","zh-CN" FROM "{t}"'))
        c.close()
        orphan = [(k, v) for k, v in data
                  if k not in used[t]
                  # Korean dev placeholder already quarantined; do not let it flow back in
                  and not k.startswith("twoxtwolove_")
                  and not k.endswith("_title")
                  and k not in PLACEHOLDER
                  and v and v.strip() and v.strip() not in PLACEHOLDER
                  # drop stray Korean dev/QA stage directions
                  and not re.search(r"[가-힣]", v or "")]
        if not orphan:
            continue
        by_bk = defaultdict(list)
        for k, v in orphan:
            bk = re.sub(r"_\d+.*$", "", k) or k
            by_bk[bk].append((k, v))
        body = [f"# 补充剧情文本 · {t}", "",
                f"> 数据表 `{t}` 中未被任何对白表引用的正文，共 {len(orphan)} 条。",
                "> 多为活动小游戏剧情、文字冒险、章节特殊演出、短信选项等；按 key 自然顺序排列。",
                "> 这类文本没有独立的说话人字段，故不标注人名。", ""]
        for bk in sorted(by_bk):
            body += [f"## {bk}", ""]
            for k, v in sorted(by_bk[bk], key=lambda x: natkey(x[0])):
                body += [clean(v).strip(), ""]
            body += ["---", ""]
        safe = t + ".md"
        (OUT / safe).write_text("\n".join(body), encoding="utf-8")
        rows.append((t, len(by_bk), len(orphan), safe))
        all_rows.append({"table": t, "lines": [{"key": k, "zh-CN": clean(v)} for k, v in orphan]})

    (OUT / "补充剧情文本_全量.json").write_text(
        json.dumps(all_rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    idx = ["# 补充剧情文本 · 目录", "",
           f"> 共 {sum(r[2] for r in rows)} 条正文，来自 {len(rows)} 张本地化表。", "",
           "| 数据表 | 分组 | 正文条数 | 文件 |", "| --- | ---: | ---: | --- |"]
    for t, nb, nl, fn in rows:
        idx.append(f"| {t} | {nb} | {nl} | [{fn}]({fn}) |")
    idx += ["", "## 这是什么", "",
            "- 客户端里有一部分剧情不走 `XxxDialogTable`（例如活动小游戏剧情、文字冒险、章节特殊演出），",
            "  它们的正文只存在于本地化表中。本目录把这些文本按表 + 前缀分组全部兜底收录。",
            "- 这些正文按表 + 前缀分组全部兜底收录，可能混有选项分支或旁白；阅读时按分组名筛选即可。",
            "- 活动名称、任务条件、设施名等纯 UI 文案已排除，不在本目录内。",
            "- 没有独立说话人字段，不标注人名。", ""]
    (OUT / "00_目录.md").write_text("\n".join(idx), encoding="utf-8")

    total = sum(r[2] for r in rows)
    print(f"orphan rows={total} tables={len(rows)}")
    for t, nb, nl, fn in rows:
        print(f"  {t:24s} buckets={nb:4d} rows={nl:6d}")

    # patch root index
    p = ROOT_IDX
    txt = p.read_text(encoding="utf-8")
    extra_line = f"| 补充剧情文本 | {len(rows)} | {total} | 0 | [补充剧情文本/00_目录.md](补充剧情文本/00_目录.md) |"
    if "补充剧情文本/00_目录.md" not in txt:
        lines = txt.splitlines()
        for i, l in enumerate(lines):
            if l.startswith("| 短信与日常对话 |"):
                lines.insert(i + 1, extra_line)
                break
        txt = "\n".join(lines) + "\n"
    else:
        lines = [re.sub(r"^\| 补充剧情文本 \|.*$", extra_line, l) for l in txt.splitlines()]
        txt = "\n".join(lines) + "\n"
    if "补充剧情文本**收录" not in txt:
        txt = txt.replace(
            "- 本批 JSON 为控制体积只含 zh-CN + speaker/portrait；需要 en/ja 三语对照可再导。",
            "- 本批 JSON 为控制体积只含 zh-CN + speaker/portrait；需要 en/ja 三语对照可再导。\n"
            "- **补充剧情文本**收录了不经过对白表、只存在于本地化表中的正文（活动小游戏 / 文字冒险 / 章节特殊演出等），\n"
            "  作为兜底确保文本不遗漏；这类文本没有说话人字段。\n"
            "- 活动名称 / 任务条件 / 前哨基地设施名等 UI 文案不属于剧情，未收录。")
    nums = [int(m.group(1)) for m in
            re.finditer(r"^\| [^|]+ \| \d+ \| (\d+) \|", txt, re.M)]
    grand = sum(nums)
    txt = re.sub(r"共 \d+ 类 / \d+ 条文本[^\n]*。",
                 f"共 {len(nums)} 类 / {grand} 条文本，其中 235785 条带说话人。", txt)
    p.write_text(txt, encoding="utf-8")
    print("root index updated, grand total", grand)


if __name__ == "__main__":
    main()
