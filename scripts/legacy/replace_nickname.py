"""Replace the player-nickname template variable with 指挥官 across all deliverables.

Run this as the LAST step after any export_* / fix_* script.
"""
from pathlib import Path

BASE = Path(r"E:\test\nikke_extract")
VAR = "{AccountData.NickName}"
REPL = "指挥官"

FIXES = {
    "其他剧情/00_总目录.md": [
        ("- `指挥官` 是玩家昵称模板变量（游戏内会替换成你的指挥官名），保留原始写法。",
         "- 玩家昵称模板变量已统一替换为「指挥官」（游戏内显示的是你的指挥官名）。"),
    ],
    "其他剧情/活动剧情/00_目录.md": [
        ("- 文本中的 `指挥官` 是游戏运行时的**玩家昵称变量**，中文客户端会替换成你的指挥官名；此处保留原始写法。",
         "- 文本中的玩家昵称变量已统一替换为「指挥官」（游戏内显示的是你的指挥官名）。"),
    ],
}


def main():
    md = sorted(BASE.rglob("*.md"))
    js = sorted(BASE.rglob("*.json"))
    total = 0
    touched = []
    for p in md + js:
        try:
            t = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        n = t.count(VAR)
        if not n:
            continue
        p.write_text(t.replace(VAR, REPL), encoding="utf-8")
        total += n
        touched.append((n, p))
    print(f"replaced {VAR} -> {REPL}: {total} occurrences in {len(touched)} files")
    for n, p in sorted(touched, reverse=True)[:8]:
        print(f"  {n:>4}  {p.relative_to(BASE)}")

    for rel, pairs in FIXES.items():
        p = BASE / rel
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        for old, new in pairs:
            if old in t:
                t = t.replace(old, new)
                print("index note updated:", rel)
        p.write_text(t, encoding="utf-8")

    # verify
    left = []
    for p in md + js:
        try:
            if VAR in p.read_text(encoding="utf-8"):
                left.append(p)
        except UnicodeDecodeError:
            pass
    print("remaining occurrences in md/json:", len(left))
    for p in left[:5]:
        print("  ", p)


if __name__ == "__main__":
    main()
