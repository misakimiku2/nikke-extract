"""Export the COMPLETE NIKKE main story (chapters 1-50) with speaker names.

All data is local & read-only. Layout:
  ScenarioDialog.Group.csv          -> ordered d_main_* groups (771)
  ScenarioDialogTable.<group>.mpk   -> per-line speaker / portrait ids
  Locale_MainScenario (zh-CN/en/ja) -> dialogue text
  Locale_Stage / ScenarioCharacterSettingTable -> chapter & character names

Outputs to 主线剧情/ : per-chapter .md, a combined .md, an index .md, and a full .json.

CG 转场：记录携带的 `EventScene_*` token 会被保留——JSON 行内有 `cg` 字段
（只在 CG 变化的行上），Markdown 在对应台词前插入 `🖼 CG` 标记并链接成品图。
"""
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import cg_refs
import locale_db
from text_clean import clean, record_type, speaker_of, speaker_of_type

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
OUT = BASE / "主线剧情"
# NKDB 解密文件名是内容 hash，游戏更新会变——按表名动态定位（2026-11-19 刷新时旧 hash 全部失效）
LOCALE_MAIN = locale_db.find("Locale_MainScenario")
LOCALE_CHAR = locale_db.find("Locale_Character")
LOCALE_STAGE = locale_db.find("Locale_Stage")
GROUP_CSV = STATIC / "ScenarioDialog.Group.csv"

TOKEN = re.compile(rb"[ -~]{4,}")
SAFE = re.compile(r'[\\/:*?"<>|]')


def build_names():
    toks = [m.group().decode("ascii", "replace")
            for m in TOKEN.finditer((STATIC / "ScenarioCharacterSettingTable.mpk").read_bytes())]
    pairs = {}
    for i, s in enumerate(toks):
        m = re.match(r"^Locale_Character:([A-Za-z0-9_]+)_name", s)
        if m and i > 0:
            pairs[toks[i - 1]] = m.group(1)
    conn = sqlite3.connect(f"file:{LOCALE_CHAR}?mode=ro", uri=True)
    names = {}
    for rid, key in pairs.items():
        row = conn.execute('SELECT "zh-CN" FROM "Locale_Character" WHERE "Key"=?',
                           (key + "_name",)).fetchone()
        names[rid] = row[0] if row and row[0] else rid
    conn.close()
    return names


def chapter_titles():
    d = locale_db.load("Locale_Stage")
    # chapter 1 -> chapter_name_00, chapter 50 -> chapter_name_49
    return {n: (d.get(f"chapter_name_{n-1:02d}") or "") for n in range(1, 51)}


def load_texts():
    conn = sqlite3.connect(f"file:{LOCALE_MAIN}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return {r["Key"]: r for r in conn.execute(
        'SELECT "Key","zh-CN","en","ja" FROM "Locale_MainScenario"')}


def norm_group(g):
    """d_main_26_1_s -> d_main_26_01_s（表内 line key 偶尔用一位段号）。"""
    return re.sub(r"^(d_main_\d+_)(\d+)(?=_|$)",
                  lambda m: m.group(1) + m.group(2).zfill(2), g)


def chapter_block(g):
    """d_main_02af_05 -> d_main_02af；d_main_26_01_s -> d_main_26。"""
    m = re.match(r"^(d_main_\d+(?:af)?)", g)
    return m.group(1) if m else g


# CSV 里登记过的段落都有自己的表文件；没登记、但和当前表同章节的 group
# （如 d_main_02af_05/06 写在 d_main_02af_04.mpk 里）需要一起收进来。
CSV_GROUPS = {norm_group(l.strip()) for l in GROUP_CSV.read_text(encoding="utf-8-sig").splitlines()
              if l.strip().startswith("d_main_")}


def parse_group(group, names, texts, spine=None, bg_names=None, static_cg=None):
    path = STATIC / f"ScenarioDialogTable.{group}.mpk"
    raw = path.read_bytes()
    toks = [(m.start(), m.group().decode("ascii", "replace")) for m in TOKEN.finditer(raw)]
    # 表名用两位段号（d_main_26_01_s），表内 line key 偶尔用一位（d_main_26_1_s_1），
    # 直接按组名拼正则会让整章匹配不到、全部退化成 locale_fill 补全（丢说话人）。
    # 统一补零后再比对；同章节但没有独立表文件的嵌入 group 也一并收进来。
    want = norm_group(group)
    block = chapter_block(want)
    anchors = []
    for i, (o, s) in enumerate(toks):
        m = re.fullmatch(r"(.+)_(\d+)", s)
        if not m:
            continue
        # 只认「行 key + group」这一对：group 字段本身也以 _NN 结尾，
        # 不加这个判断会把 group 当成锚点，把每条记录切碎、说话人全丢。
        if i + 1 >= len(toks) or norm_group(toks[i + 1][1]) != want:
            continue
        ng = norm_group(m.group(1))
        if ng == want or (ng not in CSV_GROUPS and chapter_block(ng) == block):
            anchors.append(o)
    lines = []
    prev_cg = None
    pending_cg = ()          # 无台词记录携带的 CG 顺延到下一条有台词的记录
    cur_bg = ()              # 剧情背景随记录持续，直到下一条背景 token
    prev_bg = prev_fx = None  # 已落字段的背景/特效状态（转场判定基准）
    pending_bg = pending_fx = ()
    for n, start in enumerate(anchors, start=1):
        k = n - 1
        end = anchors[k + 1] if k + 1 < len(anchors) else len(raw)
        seg = [(o, s) for o, s in toks if start <= o < end]
        # 字面 EventScene token + 演出位 id 间接引用的动态 CG（位 id → spine 模型）
        cgs = cg_refs.merge_cgs(
            cg_refs.collect_cgs(raw, start, end),
            cg_refs.collect_movie_cgs(raw, start, end))
        bgs = cg_refs.collect_bgs(raw, start, end, bg_names or set())
        fxs = cg_refs.collect_fx(raw, start, end)
        if bgs:
            cur_bg = bgs
        lk = next((i for i, (_o, s) in enumerate(seg) if s.startswith("Locale_MainScenario:")), None)
        if lk is None:
            pending_cg = cgs or pending_cg
            pending_bg = bgs or pending_bg
            pending_fx = fxs or pending_fx
            continue
        key = seg[lk][1][len("Locale_MainScenario:"):]
        pre = [s for _o, s in seg[2:lk]]
        chars = [s for s in pre if s in names]
        speaker, sid = speaker_of(pre, names)
        # 记录类型优先：type=4 是指挥官台词，type=5 是玩家选项。
        # 后期章节的指挥官台词只有立绘 ID、没有 Self 标记，靠类型才能补上名字。
        gi = next((j for j in range(lk - 1, -1, -1)
                   if norm_group(seg[j][1]) == norm_group(group)), None)
        typ = record_type(raw, seg[gi][1], seg[gi][0]) if gi is not None else None
        by_type = speaker_of_type(typ)
        if by_type is not None:
            speaker, sid = by_type
        pid = chars[0] if chars else None
        r = texts.get(key)
        if r is None:
            pending_cg = cgs or pending_cg
            pending_bg = bgs or pending_bg
            pending_fx = fxs or pending_fx
            continue
        eff_cg = cgs or pending_cg
        pending_cg = ()
        eff_bg = bgs or pending_bg
        pending_bg = ()
        eff_fx = fxs or pending_fx
        pending_fx = ()
        line = {
            "n": n, "key": key,
            "speaker": speaker,
            "speaker_id": sid,
            "portrait": names.get(pid) if pid else None,
            "portrait_id": pid,
            "zh-CN": clean(r["zh-CN"]), "en": r["en"], "ja": r["ja"],
        }
        # 只在 CG 发生变化（含首次出现）的行上记录，与对照索引的转场口径一致
        if cg_refs.changed(prev_cg, eff_cg):
            line["cg"] = list(eff_cg)
            prev_cg = eff_cg
        # 动态 CG 解析：token 是 spine 模型名或其 X_bg 背景板时，同时给出
        # 模型名(cgd)与应铺背景(cgb)，剧情阅读器才能「模型+背景」完整呈现
        if spine:
            for t in eff_cg:
                dyn = cg_refs.resolve_dynamic(t, spine, static_cg or {}, cur_bg)
                if dyn:
                    line["cgd"], line["cgb"] = dyn
                    break
        # 背景/特效变化行：`bg` 含 black/none 等场景切换信号，`fx` 是叠加特效层
        if eff_bg and cg_refs.changed(prev_bg, eff_bg):
            line["bg"] = list(eff_bg)
            prev_bg = eff_bg
        if eff_fx and cg_refs.changed(prev_fx, eff_fx):
            line["fx"] = list(eff_fx)
            prev_fx = eff_fx
        lines.append(line)
    return lines


def fmt_lines(lines, static_cg, dynamic_cg):
    out = []
    for l in lines:
        t = (l["zh-CN"] or "").strip()
        if not t and not l.get("bg") and not l.get("fx") and not l.get("cg"):
            continue
        if l.get("bg") or l.get("fx"):
            out += cg_refs.scene_marker_md(l.get("bg"), l.get("fx"), static_cg)
        if l.get("cg"):
            out += cg_refs.marker_md(l["cg"], static_cg, dynamic_cg,
                                     model=l.get("cgd", ""), bg=l.get("cgb", ""))
        if not t:
            continue
        out.append(f"**{l['speaker']}**：{t}" if l["speaker"] else t)
        out.append("")
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = build_names()
    titles = chapter_titles()
    texts = load_texts()
    static_cg, dynamic_cg = cg_refs.load_cg_library()
    spine_models = cg_refs.load_spine_models()
    bg_names = cg_refs.load_bg_names()

    groups = [l.strip() for l in GROUP_CSV.read_text(encoding="utf-8-sig").splitlines()
              if l.strip().startswith("d_main_")]
    by_ch = defaultdict(list)
    for g in groups:
        m = re.match(r"d_main_(\d+)", g)
        if m:
            by_ch[int(m.group(1))].append(g)

    all_chapters = []
    combined = []
    total_lines = total_named = 0
    speakers = set()

    for ch in sorted(by_ch):
        title = titles.get(ch, "")
        ch_lines = []
        body = [
            f"# 第 {ch} 章 · {title}" if title else f"# 第 {ch} 章",
            "",
            "> NIKKE 主线剧情 · 简体中文（zh-CN）。**加粗前缀为说话人**；未标注的为旁白或无名字台词。",
            "",
        ]
        for idx, g in enumerate(by_ch[ch], 1):
            lines = parse_group(g, names, texts, spine_models, bg_names, static_cg)
            ch_lines.extend(lines)
            label = g[len("d_main_"):]
            body += [f"## 段落 {idx:02d} · {label}", "", f"<!-- group: {g} -->", ""]
            body += fmt_lines(lines, static_cg, dynamic_cg)
        body.append("---")
        body.append("")

        safe = SAFE.sub("_", title) if title else f"第{ch:02d}章"
        fname = f"第{ch:02d}章_{safe}.md"
        (OUT / fname).write_text("\n".join(body), encoding="utf-8")
        combined.extend(body)

        n_named = sum(1 for l in ch_lines if l["speaker"])
        speakers.update(l["speaker"] for l in ch_lines if l["speaker"])
        total_lines += len(ch_lines)
        total_named += n_named
        all_chapters.append({
            "chapter": ch, "title": title, "groups": len(by_ch[ch]),
            "lines": len(ch_lines), "named": n_named,
            "file": fname,
            "sections": [{"group": g, "lines": None} for g in by_ch[ch]],
        })
        print(f"ch {ch:02d} {title[:10]:12s} groups={len(by_ch[ch]):3d} lines={len(ch_lines):5d} named={n_named:5d}")

    # combined markdown
    (OUT / "主线剧情_全本.md").write_text("\n".join(combined), encoding="utf-8")

    # full json (compact to keep size reasonable)
    full = {"version": "data/qa-261029-10b/579369", "locale": "zh-CN",
            "scope": "main story chapters 1-50", "chapters": []}
    # second pass for full line data (kept separate to avoid holding everything twice)
    for item in all_chapters:
        sections = []
        for g in by_ch[item["chapter"]]:
            sections.append({"group": g, "lines": parse_group(g, names, texts, spine_models, bg_names, static_cg)})
        full["chapters"].append({k: item[k] for k in ("chapter", "title", "groups", "lines", "named", "file")}
                                | {"sections": sections})
    (OUT / "主线剧情_全量.json").write_text(
        json.dumps(full, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # index
    idx = [
        "# NIKKE 主线剧情全本（第 1—50 章）",
        "",
        f"> 版本 `data/qa-261029-10b/579369` · 简体中文 · 共 {len(all_chapters)} 章 / "
        f"{len(groups)} 个剧情段落 / {total_lines} 条文本，其中 {total_named} 条带说话人、{len(speakers)} 个不同角色。",
        "> **加粗前缀为说话人**；未标注名字的段落是旁白或无名字台词（游戏内不显示名字框），",
        "> JSON 中另存 `portrait` 字段标出画面立绘角色。",
        "",
        "| 章 | 章节名 | 段落 | 文本行 | 有名字 | 文件 |",
        "| ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for it in all_chapters:
        idx.append(f"| {it['chapter']} | {it['title']} | {it['groups']} | {it['lines']} | "
                   f"{it['named']} | [{it['file']}]({it['file']}) |")
        idx += ["", "## 说明", "",
            "- 每章一个 Markdown 文件；`主线剧情_全本.md` 是 50 章合并版，便于全文检索。",
            "- `主线剧情_全量.json` 含 zh-CN / en / ja 三语、`speaker` / `speaker_id` / `portrait` / `portrait_id`。",
            "- CG 转场：`cg` 字段 / `🖼 CG` 标记只出现在**画面切换到新 CG 的那一行**；",
            "  同一张 CG 持续显示的后续行不再重复标注，CG 离屏（切下一张或结束）即停止。",
            "- 说话人判定：对白表记录中 `localkey` 前出现两个角色 ID 才显示名字框，第二个为显示名；",
            "  只有一个 ID 的是画面立绘，属于旁白 / 无名字台词。",
            "- 数据来源全部为本机静态数据，未修改游戏、未读取进程内存。", "",
            "## 范围与顺序", "",
            "- 本目录收录**主线战役第 1—50 章**（`d_main_*` 全部 771 个剧情段落），含第 50 章的 `af` 后日谈。",
            "- 数据表中已预留第 51 章章节名「崛起」（`Locale_Stage:chapter_name_50`），但**尚无任何剧情文本**，故未收录。",
            "- 段落顺序沿用客户端 `ScenarioDialog.Group.csv` 的数据表顺序；第 50 章的 `af` 后日谈插在正章段落之间，与游戏内解锁顺序一致。",
            "- **未包含**：EX 外传 / 支线任务剧情 / Side Story / 活动剧情（含已单独导出的「玛丽安」活动）。", ""]
    (OUT / "00_主线剧情目录.md").write_text("\n".join(idx), encoding="utf-8")

    print(f"\nTOTAL chapters={len(all_chapters)} groups={len(groups)} lines={total_lines} "
          f"named={total_named} speakers={len(speakers)}")
    for p in ["00_主线剧情目录.md", "主线剧情_全本.md", "主线剧情_全量.json"]:
        print(" ", p, (OUT / p).stat().st_size)


if __name__ == "__main__":
    main()
