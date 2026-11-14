"""Repair root index after a Markdown formatter rewrote the table, and move the
Korean test-placeholder quarantine OUTSIDE the story corpus."""
import json
import re
import shutil
from pathlib import Path

BASE = Path(r"E:\test\nikke_extract")
OUT = BASE / "其他剧情"
EV = OUT / "活动剧情"
QUAR = BASE / "_测试占位_勿用"
ROOT = OUT / "00_总目录.md"

CATS = ["活动剧情", "妮姬个人剧情", "咨询对话", "支线剧情",
        "外传与前哨基地日常", "支线故事", "短信与日常对话", "补充剧情文本"]


def stats(cat):
    d = json.load(open(OUT / cat / f"{cat}_全量.json", encoding="utf-8"))
    if cat == "补充剧情文本":
        return len(d), sum(len(t["lines"]) for t in d), 0
    lines = sum(len(g["lines"]) for b in d for g in b["groups"])
    named = sum(1 for b in d for g in b["groups"] for l in g["lines"] if l["speaker"])
    return len(d), lines, named


def main():
    # 1) move quarantine out of the story corpus
    old = EV / "_测试占位_勿用"
    if old.exists():
        if QUAR.exists():
            shutil.rmtree(QUAR)
        shutil.move(str(old), str(QUAR))
        print("quarantine moved ->", QUAR)
    readme = QUAR / "README.md"
    if readme.exists():
        t = readme.read_text(encoding="utf-8")
        t = t.replace("正式剧情在上级目录的 `event_twoxtwolove/`。",
                      "正式剧情在 `../其他剧情/活动剧情/event_twoxtwolove/`。")
        readme.write_text(t, encoding="utf-8")

    # 2) fix event index wording
    ev_idx = EV / "00_目录.md"
    if ev_idx.exists():
        t = ev_idx.read_text(encoding="utf-8")
        t = t.replace("已隔离到 `_测试占位_勿用/`", "已移出剧情库，隔离到 `../../_测试占位_勿用/`")
        ev_idx.write_text(t, encoding="utf-8")

    # 3) rebuild root index from JSON (ignore whatever the formatter did)
    st = {c: stats(c) for c in CATS}
    grand = sum(v[1] for v in st.values())
    named_total = sum(v[2] for v in st.values())
    lines = [
        "# NIKKE 其他剧情全本 · 总目录",
        "",
        f"> 版本 `data/qa-261029-10b/579369` · 简体中文 · 共 {len(CATS)} 类 / "
        f"{grand} 条文本，其中 {named_total} 条带说话人。",
        "",
        "| 类别 | 卷数 | 文本行 | 有名字 | 入口 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for c in CATS:
        nb, nl, nn = st[c]
        lines.append(f"| {c} | {nb} | {nl} | {nn} | [{c}/00_目录.md]({c}/00_目录.md) |")
    lines += [
        "", "## 说明", "",
        "- **已单独导出、此处不重复**：主线剧情第 1—50 章（`../主线剧情/`）、最新活动「玛丽安」（`../NIKKE_最新活动剧情_玛丽安_简中.md`）。",
        "- 活动剧情已按活动拆成独立子文件夹，每个文件夹内有 `00_目录.md`。",
        "- 说话人判定：对白记录中 `localkey` 前出现两个角色 ID 才显示名字框，第二个为显示名；",
        "  只有一个 ID 的是画面立绘，属于旁白 / 无名字台词。JSON 中另存 `portrait` 字段。",
        "- 正文按 `Locale_MainScenario / SubScenario / NikkeEpisode / Counseling / SuddenStory / SuddenMessage / SideStory` 等表自动路由。",
        "- 短信、场地对话、气泡对话等单文件表没有分组布局，按文本出现顺序输出。",
        "- **补充剧情文本**收录不经过对白表、只存在于本地化表中的正文（活动小游戏 / 文字冒险 / 章节特殊演出等），",
        "  作为兜底确保文本不遗漏；这类文本没有说话人字段。",
        "- 2x2 Love 活动有一套韩文开发测试占位文本，已移出剧情库隔离到 `../_测试占位_勿用/`，不计入以上统计。",
        "- 玩家昵称模板变量已统一替换为「指挥官」（游戏内显示的是你的指挥官名）。",
        "- 活动名称 / 任务条件 / 前哨基地设施名等纯 UI 文案不属于剧情，未收录。",
        "- 本批 JSON 为控制体积只含 zh-CN + speaker/portrait；需要 en/ja 三语对照可再导。",
        "- 全部来源为本机静态数据，只读；未修改游戏、未读取进程内存。", "",
    ]
    ROOT.write_text("\n".join(lines), encoding="utf-8")

    print("\n=== corrected stats ===")
    for c in CATS:
        print(f"  {c:16s} buckets={st[c][0]:4d} lines={st[c][1]:7d} named={st[c][2]:7d}")
    print("  GRAND TOTAL", grand, "named", named_total)


if __name__ == "__main__":
    main()
