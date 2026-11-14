"""Render a 图文版 markdown into a standalone HTML page (preview only).

Usage: python build_story_html.py <md path>
"""
import html
import re
import sys
from pathlib import Path

CSS = """
:root{--bg:#0f1116;--fg:#e6e9ef;--dim:#98a1b3;--accent:#ffd60a;--line:#252a34}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:16px/1.85 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:40px 22px 120px}
h1{font-size:26px;margin:0 0 6px;color:var(--accent)}
h2{font-size:17px;margin:56px 0 18px;padding-bottom:8px;border-bottom:1px solid var(--line);color:#cfd6e4}
p{margin:10px 0}
.lead{color:var(--dim);font-size:13px;margin-bottom:28px}
img{display:block;width:100%;max-width:760px;height:auto;margin:26px auto 6px;
  border:1px solid var(--line);background:#0a0c10}
.cap{text-align:center;color:var(--dim);font-size:12px;margin:0 0 26px;letter-spacing:.02em}
strong{color:#fff}
code{background:#1a1e27;padding:1px 5px;border-radius:3px;font-size:13px}
"""


def convert(md: str) -> str:
    out, buf = [], []

    def flush():
        if buf:
            out.append("<p>" + "<br>".join(buf) + "</p>")
            buf.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if line.startswith("# "):
            flush(); out.append(f"<h1>{html.escape(line[2:])}</h1>"); continue
        if line.startswith("## "):
            flush(); out.append(f"<h2>{html.escape(line[3:])}</h2>"); continue
        if line.startswith("<!--"):
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", line)
        if m:
            flush()
            out.append(f'<img loading="lazy" src="{html.escape(m.group(2))}" alt="{html.escape(m.group(1))}">')
            continue
        if line.startswith("*▲"):
            flush()
            cap = line.strip("*").replace("`", "")
            out.append(f'<div class="cap">{html.escape(cap)}</div>')
            continue
        if line.startswith(">"):
            flush(); out.append(f'<div class="lead">{html.escape(line.lstrip("> ").strip())}</div>'); continue
        txt = html.escape(line)
        txt = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", txt)
        buf.append(txt)
    flush()
    return "\n".join(out)


def main():
    src = Path(sys.argv[1])
    md = src.read_text(encoding="utf-8")
    body = convert(md)
    page = (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(src.stem)}</title><style>{CSS}</style></head>"
            f'<body><div class="wrap">{body}</div></body></html>')
    dst = src.with_suffix(".html")
    dst.write_text(page, encoding="utf-8")
    print("written", dst, f"{dst.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
