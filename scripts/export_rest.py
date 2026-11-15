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
import glob
import json
import re
import sqlite3
from collections import defaultdict, Counter
from pathlib import Path

from text_clean import clean, record_type, speaker_of, speaker_of_type
import event_registry
import story_registry

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
DEC = BASE / "decrypted"
OUT = BASE / "其他剧情"

TOKEN = re.compile(rb"[ -~]{4,}")
SAFE = re.compile(r'[\\/:*?"<>|]')
CATS = ["活动剧情", "妮姬个人剧情", "咨询对话", "支线剧情",
        "外传与前哨基地日常", "支线故事", "短信与日常对话"]


def load_group_order():
    """Group.csv 的顺序就是游戏内的章节顺序，活动按它排序。"""
    order = {}
    for name in ("ScenarioDialog.Group.csv", "EventScenarioDialog.Group.csv",
                 "AttractiveScenarioDialog.Group.csv"):
        p = STATIC / name
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines()):
            g = line.strip()
            if g and g != "group_id":
                order.setdefault(g, i)
    return order


GROUP_ORDER = load_group_order()


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
        # 测试/占位、以及复刻（re_event_*）表不进剧情库，避免同一活动出现两份
        if group and (group.startswith("test_") or group.startswith("event_ani_test")
                      or group.startswith("re_event_") or group.startswith("re_d_contents_")):
            return None, None
        # 同一段剧情可能同时有 event_xxx 完整表和 xxx 残片表
        # （twoxtwolove 的 xxx 表只有 1~3 行）。有完整表时跳过残片，避免活动列表
        # 里出现一堆一句话的重复卡片。
        if group and not group.startswith("event_"):
            if glob.glob(str(STATIC / f"EventScenarioDialogTable.event_{glob.escape(group)}*.mpk")):
                return None, None
        return "活动剧情", group
    if table == "AttractiveScenarioDialogTable":
        return "妮姬个人剧情", group
    if table == "AttractiveCounselDialogTable":
        return "咨询对话", group
    if table.startswith("SideStory"):
        if group and group.startswith("sidestory_dummy"):
            return None, None
        return "支线故事", group
    if table == "ScenarioDialogTable":
        if group and (group.startswith("d_main_") or re.match(r"d_main_\d+af", group)):
            return None, None  # main story already exported
        # 复刻表与 d_subquest 重复，跳过避免同一段支线出现两份
        if group and group.startswith("re_d_subquest"):
            return None, None
        if group and (group.startswith("d_ex_") or group.startswith("d_test_")):
            return "外传与前哨基地日常", group
        return "支线剧情", group
    return "短信与日常对话", None  # single-file tables have no group layout


def bucket_of(cat, key):
    if cat == "活动剧情":
        return re.sub(r"_(prologue|epilogue|intermission_\d+|\d+_[se]|\d+)$", "", key)
    if cat == "支线剧情":
        # 支线任务按「同一委托的多章」聚合：d_subquest_1011/1012/1013 -> d_subquest_101
        parsed = story_registry.subquest_code(key)
        if parsed:
            return "d_subquest_" + parsed[0]
        return re.sub(r"_\d+(_[se])?$", "", key)
    if cat == "外传与前哨基地日常":
        # RED ASH 的 7 段外传（d_ex_redash_01_1 ...）合成一张卡
        if key.startswith("d_ex_redash"):
            return "d_ex_redash"
        return re.sub(r"_\d+(_[se])?$", "", key)
    if cat in ("妮姬个人剧情", "咨询对话"):
        return re.sub(r"_\d+(_[se])?$", "", key)
    if cat == "支线故事":
        m = re.match(r"(s\d+)", key)
        return m.group(1) if m else key
    return key


def parse(path, group, names, store):
    raw = path.read_bytes()
    toks = [(m.start(), m.end(), m.group().decode("ascii", "replace"))
            for m in TOKEN.finditer(raw)]
    lines = []

    def group_ok(tok, g):
        # 二进制长度字节会粘成 ASCII 后缀：event_xxx_01_s_1A
        return tok == g or (tok.startswith(g) and len(tok) <= len(g) + 2)

    def push(key, table, text, pre, n, group_start=None):
        chars = [s for s in pre if s in names]
        speaker, sid = speaker_of(pre, names)
        # 记录类型只认 0/1/2/4/5；活动表的 group 后两个 int 可能是 event id
        if group_start is not None:
            typ = record_type(raw, group, group_start)
            if typ in (0, 1, 2, 4, 5):
                by_type = speaker_of_type(typ)
                if by_type is not None:
                    speaker, sid = by_type
        pid = chars[0] if chars else None
        title = None
        if group:
            title = store.get(table, group + "_title")
            if title is None and table != "Locale_MainScenario":
                title = store.get("Locale_MainScenario", group + "_title")
        lines.append({
            "n": n, "key": key, "locale_table": table,
            "speaker": speaker, "speaker_id": sid,
            "portrait": names.get(pid) if pid else None, "portrait_id": pid,
            "zh-CN": clean(text), "title": title,
            "bucket": re.sub(r"_\d+$", "", key) if not group else None,
        })

    if group:
        # 以 Locale 标记为锚点：行 key 后面常粘着二进制字节（_1A），
        # 按「行 key + 数字」匹配会整段漏掉（NO CALLER ID 只剩几行就是这个原因）。
        for i, (_s, _e, t) in enumerate(toks):
            if not t.startswith("Locale_") or ":" not in t:
                continue
            table, key = t.split(":", 1)
            text = store.get(table, key)
            if text is None:
                continue
            gi = next((j for j in range(i - 1, max(-1, i - 80), -1)
                       if group_ok(toks[j][2], group)), None)
            if gi is None:
                continue
            pre = [x for _o, _e, x in toks[gi + 1:i]]
            m = re.search(r"_(\d+)$", key)
            n = int(m.group(1)) if m else len(lines) + 1
            push(key, table, text, pre, n, toks[gi][0])
    else:
        lk_idx = [i for i, (_o, _e, s) in enumerate(toks) if s.startswith("Locale_")]
        for k, i in enumerate(lk_idx):
            prev = lk_idx[k - 1] + 1 if k > 0 else 0
            lk = toks[i][2]
            if ":" not in lk:
                continue
            table, key = lk.split(":", 1)
            text = store.get(table, key)
            if text is None:
                continue
            pre = [x for _o, _e, x in toks[prev:i]]
            push(key, table, text, pre, k + 1)

    lines.sort(key=lambda x: x["n"])
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
        elif cat == "活动剧情":
            # 活动按「一个活动一个单元」聚合；group 只是活动里的章节。
            buckets[cat][event_registry.event_key_of(key)].append((key, lines))
        else:
            buckets[cat][bucket_of(cat, key)].append((key, lines))
        if (idx + 1) % 1500 == 0:
            print(f"  parsed {idx+1}/{len(files)}")
    print("skipped (main story / marian):", skipped)

    # 咨询会话标题反推「角色：皮肤」，给个人剧情卡当标题
    counsel_titles = {}
    for bk, groups in buckets["咨询对话"].items():
        slug = bk[len("d_counseling_"):] if bk.startswith("d_counseling_") else bk
        t = next((l["title"] for _g, ls in groups for l in ls if l["title"]), None)
        if t:
            counsel_titles[slug] = t
    counsel = story_registry.counsel_index(counsel_titles)

    def dominant_speaker(groups):
        """剧情里说话最多的人（排除指挥官与旁白），用于没有咨询可对照的单元。"""
        cnt = Counter()
        for _g, ls in groups:
            for l in ls:
                sp = l["speaker"]
                if sp and sp not in ("指挥官", "旁白"):
                    cnt[sp] += 1
        return cnt.most_common(1)[0][0] if cnt else None

    def unit_title(cat, bk, groups):
        if cat == "活动剧情":
            return event_registry.event_title_of(bk)
        if cat == "妮姬个人剧情":
            if bk.startswith("treasurestory_"):
                slug = bk[len("treasurestory_"):]
                name = (counsel.get(slug, (None, None))[0]
                        or dominant_speaker(groups) or story_registry.prettify(slug))
                return f"{name} · 宝物剧情"
            if bk.startswith("d_nikke_"):
                return story_registry.nikke_title(
                    bk[len("d_nikke_"):], counsel, dominant_speaker(groups))
            return bk
        if cat == "外传与前哨基地日常":
            if bk == "d_ex_redash":
                return "RED ASH · 外传"
            slug = bk[len("d_ex_"):] if bk.startswith("d_ex_") else bk
            return story_registry.outpost_title(slug, store.get)
        if cat == "支线剧情":
            if bk.startswith("d_subquest_"):
                return story_registry.subquest_title(bk[len("d_subquest_"):], store.get)
            raw = next((l["title"] for _g, ls in groups for l in ls if l["title"]), None)
            return story_registry.contents_title(bk, raw)
        if cat == "支线故事":
            first = next((l["title"] for _g, ls in groups for l in ls if l["title"]), None)
            return story_registry.series_title(first, bk)
        return bk

    def group_sort(g):
        parsed = story_registry.subquest_code(g)
        if parsed:
            _fam, code, se = parsed
            return (0, int(code), {"s": 0, "e": 2}.get(se, 1))
        # 同一章的前篇(_s)要排在后篇(_e)前
        return (1, re.sub(r"_(s|e)$",
                          lambda m: "_{" if m.group(1) == "s" else "_}", g))

    def sub_sort(k):
        if k.startswith("d_subquest_"):
            return (0, int(k[len("d_subquest_"):]))
        return (1, k)

    summary = {}
    for cat in CATS:
        d = OUT / cat
        d.mkdir(exist_ok=True)
        cat_lines = cat_named = 0
        cat_json = []
        rows = []
        if cat == "活动剧情":
            keys = sorted(buckets[cat], key=lambda k: min(
                (GROUP_ORDER.get(g, 10 ** 9) for g, _ in buckets[cat][k]), default=10 ** 9))
        elif cat == "支线剧情":
            keys = sorted(buckets[cat], key=sub_sort)
        else:
            keys = sorted(buckets[cat])

        for bk in keys:
            if cat == "活动剧情":
                groups = sorted(buckets[cat][bk], key=lambda x: GROUP_ORDER.get(x[0], 10 ** 9))
            else:
                groups = sorted(buckets[cat][bk], key=lambda x: group_sort(x[0]))
            event_title = unit_title(cat, bk, groups)
            # 支线故事的 b 分支段没有自己的标题，继承主段并标 B1/B2
            inherited = {}
            if cat == "支线故事":
                for g, ls in groups:
                    m = re.match(r"^(s\d+_\d+)$", g)
                    if m:
                        t = next((l["title"] for l in ls if l["title"]), None)
                        if t:
                            inherited[m.group(1)] = t
            body = [f"# {cat} · {event_title}", "",
                    "> NIKKE 剧情文本 · 简体中文（zh-CN）。**加粗前缀为说话人**；未标注的是旁白或无名字台词。", ""]
            bj = {"bucket": f"event_{bk}" if cat == "活动剧情" else bk,
                  "title": event_title, "groups": []}
            b_lines = b_named = 0
            for g, lines in groups:
                b_lines += len(lines)
                b_named += sum(1 for l in lines if l["speaker"])
                title = next((l["title"] for l in lines if l["title"]), None)
                if cat == "活动剧情":
                    title = event_registry.chapter_title(g, title)
                elif cat == "支线剧情":
                    title = story_registry.subquest_chapter(g, store.get) or title
                elif cat == "支线故事" and not title:
                    m = re.match(r"^(s\d+_\d+)_b(\d+)", g)
                    if m and m.group(1) in inherited:
                        title = f"{inherited[m.group(1)]}（B{m.group(2)}）"
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
