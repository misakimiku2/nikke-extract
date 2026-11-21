"""Export the ScenarioMovieTable — chapter-end animations / PVs (CDN mp4+srt).

ScenarioMovieTable.mpk 的记录是变长的 [movie_key, movie_id, (lang?), mp4_url, srt_url]：
每部动画每种语言一行，key 形如 opening_pv01_zh-CN / ch18_end_en；
zh-CN 等语言的 mp4 常回退到 ko 版（URL 与 ko 相同），srt 字幕则是本语言。
没有官方中配的动画会直接引用 ko 视频——这里原样保留 URL，不做改写。

输出 CG索引/剧情动画清单.csv + .json：movie_id、语言、mp4、srt。
（视频本体在 CDN，不入库；这是「关于 CG 的一切」里影像一类的索引。）
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import locale_db  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / "staticdata"
OUT = BASE / "CG索引"

TOKEN = re.compile(rb"[ -~]{4,}")
URL = re.compile(r"^https?://\S+$")


def main() -> None:
    raw = (STATIC / "ScenarioMovieTable.mpk").read_bytes()
    toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]

    rows = []
    cur: dict | None = None
    for t in toks:
        if URL.match(t):
            if cur is None:
                continue
            if t.endswith(".srt"):
                cur["srt"] = t
            else:
                cur["mp4"] = t
            if cur["mp4"] and cur["srt"]:          # mp4+srt 齐了 = 一条记录完整
                rows.append(cur)
                cur = None
            continue
        if cur and cur["mp4"]:                     # URL 后的新 token = 下一条记录
            rows.append(cur)
            cur = None
        if cur is None:
            cur = {"key": "", "movie_id": "", "语言": "", "mp4": "", "srt": ""}
        m = re.match(r"^(.+?)_([a-z]{2}(?:-[A-Z]{2})?)$", t)
        if m and not cur["movie_id"]:
            cur["key"] = t
            cur["movie_id"] = m.group(1)
            cur["语言"] = m.group(2)
        elif not cur["movie_id"]:
            cur["movie_id"] = t
    if cur and cur["mp4"]:
        rows.append(cur)

    # movie_id -> 中文名（章节名，能对上 chNN_end 的挂到主线章）
    zh_stage = {}
    try:
        zh_stage = locale_db.load("Locale_Stage")
    except FileNotFoundError:
        pass

    def title_of(mid: str) -> str:
        m = re.match(r"^ch(\d+)_end$", mid)
        if m:
            n = int(m.group(1))
            name = zh_stage.get(f"chapter_name_{n - 1:02d}") or ""
            return f"第{n}章章末动画" + (f" · {name}" if name else "")
        return ""

    by_movie: dict[str, list] = {}
    for r in rows:
        by_movie.setdefault(r["movie_id"], []).append(r)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "剧情动画清单.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["movie_id", "归属/说明", "语言", "mp4", "srt"])
        for mid, rs in sorted(by_movie.items()):
            t = title_of(mid)
            for r in sorted(rs, key=lambda x: x["语言"]):
                w.writerow([mid, t, r["语言"], r["mp4"], r["srt"]])
    (OUT / "剧情动画清单.json").write_text(
        json.dumps({mid: {"说明": title_of(mid),
                          "语言行": rs} for mid, rs in sorted(by_movie.items())},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"movies {len(by_movie)} / language rows {len(rows)} -> {OUT / '剧情动画清单.csv'}")


if __name__ == "__main__":
    main()
