"""Export ALL remaining NIKKE scenario text (everything except main story 1-50 and the Marian event).

Categories:
  活动剧情            EventScenarioDialogTable.*           (excluding event_marian*)
  妮姬个人剧情        AttractiveScenarioDialogTable.*      -> Locale_NikkeEpisode
  咨询对话            AttractiveCounselDialogTable.*       -> Locale_Counseling
  支线剧情            ScenarioDialogTable.{d_subquest,re_d_subquest,d_contents,...}
  外传与前哨基地日常   ScenarioDialogTable.{d_ex_*,d_test_*}
  支线故事            SideStoryScenarioDialogTable / SideStorySpotDialogTable
  短信与日常对话       Messenger / FieldTalk / Balloon / Echo / Event*Dialog (single-file tables)

All inputs are local decrypted data; read-only, no game process access.
"""
import json
import re
import sqlite3
from collections import defaultdict, Counter
from pathlib import Path

from text_clean import clean, speaker_of

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
DEC = BASE / "decrypted"
OUT = BASE / "其他剧情"

TOKEN = re.compile(rb"[ -~]{4,}")
SAFE = re.compile(r'[\\/:*?"<>|]')
CATS = ["活动剧情", "妮姬个人剧情", "咨询对话", "支线剧情",
        "外传与前哨基地日常", "支线故事", "短信与日常对话"]


class LocaleStore:
    """Lazy loader: Locale_<Table> -> {key: zh-CN}."""
    def __init__(self):
        self.dbmap = {}
        for p in DEC.glob("*.dec"):
            try:
                c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
                for (t,) in c.execute("select name from sqlite_master where type='table'"):
                    if t.startswith("Locale_"):
                        self.dbmap[t] = str(p)
                c.close()
            except Exception:
                pass
        self.cache = {}
        self.missing = Counter()
        self.miss = Counter()

    def get(self, table, key):
        if table not in self.dbmap:
            self.missing[table] += 1
            return None
        if table not in self.cache:
            c = sqlite3.connect(f"file:{self.dbmap[table]}?mode=ro", uri=True)
            self.cache[table] = dict(c.execute(f'SELECT "Key","zh-CN" FROM "{table}"'))
            c.close()
        v = self.cache[table].get(key)
        if v is None:
            self.miss[table] += 1
        return v


def build_names():
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(
        (STATIC / "ScenarioCharacterSettingTable.mpk").read_bytes())]
    pairs = {}
    for i, s in enumerate(toks):
        m = re.match(r"^Locale_Character:([A-Za-z0-9_]+)_name", s)
        if m and i > 0:
            pairs[toks[i - 1]] = m.group(1)
    store = LocaleStore()
    names = {}
    for rid, key in pairs.items():
        v = store.get("Locale_Character", key + "_name")
        names[rid] = v or rid
    return names


def classify(fname):
    stem = fname[:-4]
    if "." in stem:
        table, group = stem.split(".", 1)
    else:
        table, group = stem, None
    if table == "EventScenarioDialogTable":
        if group and group.startswith("event_marian"):
            return None, None
        return "活动剧情", group
    if table == "AttractiveScenarioDialogTable":
        return "妮姬个人剧情", group
    if table == "AttractiveCounselDialogTable":
        return "咨询对话", group
    if table.startswith("SideStory"):
        return "支线故事", group
    if table == "ScenarioDialogTable":
        if group and (group.startswith("d_main_") or re.match(r"d_main_\d+af", group)):
            return None, None  # main story already exported
        if group and (group.startswith("d_ex_") or group.startswith("d_test_")):
            return "外传与前哨基地日常", group
        return "支线剧情", group
    return "短信与日常对话", None  # single-file tables have no group layout


def bucket_of(cat, key):
    if cat == "活动剧情":
        return re.sub(r"_(prologue|epilogue|intermission_\d+|\d+_[se]|\d+)$", "", key)
    if cat in ("妮姬个人剧情", "咨询对话", "外传与前哨基地日常", "支线剧情"):
        return re.sub(r"_\d+(_[se])?$", "", key)
    if cat == "支线故事":
        m = re.match(r"(s\d+)", key)
        return m.group(1) if m else key
    return key


def parse(path, group, names, store):
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    lines = []
    if group:
        id_re = re.compile(re.escape(group) + r"_(\d+)$")
        anchors = [(i, int(id_re.match(s).group(1)))
                   for i, (_, s) in enumerate(toks) if id_re.fullmatch(s)]
        spans = []
        for k, (i, n) in enumerate(anchors):
            j = anchors[k + 1][0] if k + 1 < len(anchors) else len(toks)
            spans.append((n, [s for _, s in toks[i:j]]))
    else:
        lk_idx = [i for i, (_, s) in enumerate(toks) if s.startswith("Locale_")]
        spans = []
        for k, i in enumerate(lk_idx):
            prev = lk_idx[k - 1] + 1 if k > 0 else 0
            spans.append((k + 1, [s for _, s in toks[prev:i + 1]]))

    for n, seg in spans:
        lk_i = next((i for i, s in enumerate(seg) if s.startswith("Locale_")), None)
        if lk_i is None:
            continue
        lk = seg[lk_i]
        if ":" not in lk:
            continue
        table, key = lk.split(":", 1)
        text = store.get(table, key)
        if text is None:
            continue
        pre = seg[2:lk_i] if group else seg[:lk_i]
        chars = [s for s in pre if s in names]
        speaker, sid = speaker_of(pre, names)
        pid = chars[0] if chars else None
        title = store.get(table, (group or "") + "_title") if group else None
        lines.append({
            "n": n, "key": key, "locale_table": table,
            "speaker": speaker, "speaker_id": sid,
            "portrait": names.get(pid) if pid else None, "portrait_id": pid,
            "zh-CN": clean(text), "title": title,
            "bucket": re.sub(r"_\d+$", "", key) if not group else None,
        })
    return lines


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = build_names()
    store = LocaleStore()

    buckets = defaultdict(lambda: defaultdict(list))  # cat -> bucket -> [(group, lines)]
    files = sorted(STATIC.glob("*DialogTable*.mpk"))
    print("dialog files:", len(files))
    skipped = 0
    for idx, f in enumerate(files):
        cat, key = classify(f.name)
        if cat is None:
            skipped += 1
            continue
        lines = parse(f, key, names, store)
        if not lines:
            continue
        if key is None:  # single-file table -> split by session key
            by_bk = defaultdict(list)
            for l in lines:
                by_bk[l["bucket"] or "misc"].append(l)
            for bk, sub in by_bk.items():
                # one markdown per source table; sessions become ## sections inside it
                buckets[cat][f.stem].append((bk, sub))
        else:
            buckets[cat][bucket_of(cat, key)].append((key, lines))
        if (idx + 1) % 1500 == 0:
            print(f"  parsed {idx+1}/{len(files)}")
    print("skipped (main story / marian):", skipped)

    summary = {}
    for cat in CATS:
        d = OUT / cat
        d.mkdir(exist_ok=True)
        cat_lines = cat_named = 0
        cat_json = []
        rows = []
        for bk in sorted(buckets[cat]):
            groups = sorted(buckets[cat][bk], key=lambda x: x[0])
            body = [f"# {cat} · {bk}", "",
                    "> NIKKE 剧情文本 · 简体中文（zh-CN）。**加粗前缀为说话人**；未标注的是旁白或无名字台词。", ""]
            bj = {"bucket": bk, "groups": []}
            b_lines = b_named = 0
            for g, lines in groups:
                b_lines += len(lines)
                b_named += sum(1 for l in lines if l["speaker"])
                title = next((l["title"] for l in lines if l["title"]), None)
                body += [f"## {g}" + (f" · {title}" if title else ""), "",
                         f"<!-- group: {g} -->", ""]
                for l in lines:
                    t = (l["zh-CN"] or "").strip()
                    if not t:
                        continue
                    body.append(f"**{l['speaker']}**：{t}" if l["speaker"] else t)
                    body.append("")
                bj["groups"].append({"group": g, "title": title, "lines": lines})
            body += ["---", ""]
            safe = SAFE.sub("_", bk) or "misc"
            fname = f"{safe}.md"
            (d / fname).write_text("\n".join(body), encoding="utf-8")
            cat_lines += b_lines
            cat_named += b_named
            cat_json.append(bj)
            rows.append((bk, len(groups), b_lines, b_named, fname))

        (d / f"{cat}_全量.json").write_text(
            json.dumps(cat_json, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        idx_md = [f"# {cat} · 目录", "",
                  f"> 共 {len(rows)} 卷 / {cat_lines} 条文本，其中 {cat_named} 条带说话人。", "",
                  "| 卷 | 剧情段 | 文本行 | 有名字 | 文件 |", "| --- | ---: | ---: | ---: | --- |"]
        for bk, ng, nl, nn, fn in rows:
            idx_md.append(f"| {bk} | {ng} | {nl} | {nn} | [{fn}]({fn}) |")
        idx_md += ["", f"结构化数据在 `{cat}_全量.json`。", ""]
        (d / "00_目录.md").write_text("\n".join(idx_md), encoding="utf-8")
        summary[cat] = (len(rows), cat_lines, cat_named)
        print(f"{cat:16s} buckets={len(rows):4d} lines={cat_lines:7d} named={cat_named:7d}")

    total_lines = sum(v[1] for v in summary.values())
    total_named = sum(v[2] for v in summary.values())
    root = ["# NIKKE 其他剧情全本 · 总目录", "",
            f"> 版本 `data/qa-261029-10b/579369` · 简体中文 · 共 {len(CATS)} 类 / "
            f"{total_lines} 条文本，其中 {total_named} 条带说话人。", "",
            "| 类别 | 卷数 | 文本行 | 有名字 | 入口 |", "| --- | ---: | ---: | ---: | --- |"]
    for cat in CATS:
        nb, nl, nn = summary[cat]
        root.append(f"| {cat} | {nb} | {nl} | {nn} | [{cat}/00_目录.md]({cat}/00_目录.md) |")
    root += ["", "## 说明", "",
             "- **已单独导出、此处不重复**：主线剧情第 1—50 章（`主线剧情/`）、最新活动「玛丽安」（`NIKKE_最新活动剧情_玛丽安_简中.md`）。",
             "- 说话人判定沿用主线规则：对白记录中 `localkey` 前出现两个角色 ID 才显示名字框，第二个为显示名；",
             "  只有一个 ID 的是画面立绘，属于旁白 / 无名字台词。JSON 中另存 `portrait` 字段。",
             "- 正文按 `Locale_MainScenario / SubScenario / NikkeEpisode / Counseling / SuddenStory / SuddenMessage / SideStory` 等表自动路由。",
             "- 短信、场地对话、气泡对话等单文件表没有分组布局，按文本出现顺序输出。",
             "- 本批 JSON 为控制体积只含 zh-CN + speaker/portrait；需要 en/ja 三语对照可再导。",
             "- 全部来源为本机静态数据，只读；未修改游戏、未读取进程内存。", ""]
    (OUT / "00_总目录.md").write_text("\n".join(root), encoding="utf-8")
    print(f"\nTOTAL lines={total_lines} named={total_named}")
    print("key lookup misses:", dict(store.miss))


if __name__ == "__main__":
    main()
