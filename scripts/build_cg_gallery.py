"""Build the human-facing CG index: thumbnails + a single-file HTML gallery.

Reads CG索引/剧情CG对照索引.csv, writes:
  CG索引/缩略图/<CG名>.webp   420px previews (referenced CGs only)
  CG索引/剧情CG索引.html      standalone gallery, no external JS/CSS
"""
from __future__ import annotations

import csv
import html
import json
import pathlib

from PIL import Image

BASE = pathlib.Path(__file__).resolve().parents[1]
IDX = BASE / "CG索引"
CSV_PATH = IDX / "剧情CG对照索引.csv"
THUMB = IDX / "缩略图"
HTML_OUT = IDX / "剧情CG索引.html"
THUMB_MAX = 480


def make_thumbs(rows):
    THUMB.mkdir(parents=True, exist_ok=True)
    names = {}
    made = skipped = missing = 0
    for r in rows:
        cg = r["CG名"]
        if cg in names:
            continue
        src = BASE / r["静态图"] if r["静态图"] else None
        dst = THUMB / (cg + ".webp")
        names[cg] = dst.name
        if dst.exists() and dst.stat().st_mtime >= (src.stat().st_mtime if src else 0):
            skipped += 1
            continue
        if not src or not src.exists():
            missing += 1
            names[cg] = ""
            continue
        try:
            im = Image.open(src)
            im.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            im.save(dst, "WEBP", quality=82, method=4)
            made += 1
        except Exception:
            missing += 1
            names[cg] = ""
    print(f"thumbs made {made} skipped {skipped} missing {missing}")
    return names


def main():
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    thumbs = make_thumbs(rows)

    entries = []
    for i, r in enumerate(rows):
        entries.append({
            "i": i,
            "cat": r["分类"],
            "act": r["活动/章节"],
            "actKey": r["活动键"],
            "sec": r["小节"],
            "secTitle": r["小节标题"],
            "line": int(r["行号"]),
            "who": r["说话人"],
            "text": r["台词"],
            "cg": r["CG名"],
            "thumb": thumbs.get(r["CG名"], ""),
            "full": r["静态图"].replace("\\", "/"),
            "dyn": r["动态CG"].replace("\\", "/"),
            "match": r["匹配"],
        })

    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    acts = sorted({e["act"] for e in entries})
    html_text = TEMPLATE.replace("/*__DATA__*/[]", payload) \
                       .replace("__ACTS__", json.dumps(acts, ensure_ascii=False)) \
                       .replace("__TOTAL__", str(len(entries))) \
                       .replace("__CGCOUNT__", str(len({e['cg'] for e in entries}))) \
                       .replace("__DYNCOUNT__", str(sum(1 for e in entries if e['dyn'])))
    HTML_OUT.write_text(html_text, encoding="utf-8")
    print("written", HTML_OUT, f"{HTML_OUT.stat().st_size/1024:.0f} KB, entries {len(entries)}")


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NIKKE 剧情 × CG 对照索引</title>
<style>
  :root{
    --bg:#111318; --panel:#181b22; --line:#2a2f3a; --fg:#e8eaef; --dim:#8b93a3;
    --accent:#ffd60a; --red:#e0484f; --green:#3fbf7f;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;display:flex;flex-direction:column}
  header{display:flex;align-items:center;gap:14px;padding:12px 18px;background:var(--accent);color:#141414;flex-wrap:wrap}
  header h1{font-size:16px;margin:0;font-weight:800;letter-spacing:.5px}
  header .stat{font-size:12px;font-weight:600;opacity:.72}
  header input{flex:1;min-width:200px;max-width:360px;margin-left:auto;padding:8px 12px;border:2px solid #141414;background:#fff;border-radius:0;font-size:13px;font-weight:600}
  header input:focus{outline:3px solid rgba(0,0,0,.15)}
  .layout{flex:1;display:flex;min-height:0}
  aside{width:260px;border-right:1px solid var(--line);overflow:auto;padding:10px 0;background:var(--panel)}
  aside .grp{padding:6px 16px;font-size:11px;color:var(--dim);letter-spacing:.08em;text-transform:uppercase}
  aside button{display:flex;justify-content:space-between;gap:8px;width:100%;padding:7px 16px;background:none;border:0;color:var(--fg);font:13px/1.3 inherit;text-align:left;cursor:pointer}
  aside button:hover{background:#20242d}
  aside button.on{background:#262b36;box-shadow:inset 3px 0 0 var(--accent)}
  aside button span{color:var(--dim);font-size:12px;flex:none}
  main{flex:1;overflow:auto;padding:16px 18px 60px}
  .bar{display:flex;gap:8px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
  .chip{padding:6px 12px;border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:999px;font-size:12px;cursor:pointer}
  .chip.on{background:var(--accent);color:#151515;border-color:var(--accent);font-weight:700}
  .count{color:var(--dim);font-size:12px;margin-left:auto}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:4px;overflow:hidden;cursor:pointer;transition:transform .12s,border-color .12s;display:flex;flex-direction:column}
  .card:hover{transform:translateY(-2px);border-color:#4a5262}
  .thumb{aspect-ratio:1/1;background:#0b0d11 center/cover no-repeat;width:100%;image-rendering:auto}
  .meta{padding:9px 11px 11px;display:flex;flex-direction:column;gap:4px}
  .meta .where{font-size:11px;color:var(--accent);font-weight:700;letter-spacing:.02em}
  .meta .name{font-size:12px;color:var(--dim);word-break:break-all}
  .meta .line{font-size:12.5px;color:var(--fg);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .meta .who{color:#a9b4c7;font-weight:700}
  .badges{display:flex;gap:6px;margin-top:2px}
  .b{font-size:10px;padding:1px 6px;border-radius:2px;background:#2a3140;color:#b9c3d4}
  .b.dyn{background:#2b2140;color:#c9a6ff}
  .b.approx{background:#3a2c18;color:#ffc266}
  .empty{color:var(--dim);padding:40px 0;text-align:center}
  .lb{position:fixed;inset:0;background:rgba(6,8,12,.94);display:none;flex-direction:column;z-index:50}
  .lb.on{display:flex}
  .lb .top{display:flex;align-items:center;gap:12px;padding:10px 16px;color:var(--fg);font-size:13px}
  .lb .top b{color:var(--accent)}
  .lb .top .sp{margin-left:auto;display:flex;gap:8px}
  .lb button{background:#20242d;color:var(--fg);border:1px solid var(--line);padding:6px 12px;cursor:pointer;border-radius:2px}
  .lb .body{flex:1;display:flex;align-items:center;justify-content:center;overflow:hidden;padding:0 16px 16px}
  .lb img{max-width:100%;max-height:100%;object-fit:contain;background:#0b0d11}
  .lb .cap{padding:0 18px 14px;color:var(--dim);font-size:12.5px}
  .lb .cap b{color:#dbe2ee;font-weight:600}
  @media (max-width:760px){aside{display:none}}
</style>
</head>
<body>
<header>
  <h1>NIKKE · 剧情 × CG 对照索引</h1>
  <div class="stat">__TOTAL__ 处出现 · __CGCOUNT__ 张 CG · __DYNCOUNT__ 处有动态版</div>
  <input id="q" placeholder="搜台词 / CG 名 / 章节…">
</header>
<div class="layout">
  <aside id="side"></aside>
  <main>
    <div class="bar" id="bar">
      <button class="chip on" data-cat="全部">全部</button>
      <button class="chip" data-cat="主线">主线</button>
      <button class="chip" data-cat="活动">活动</button>
      <button class="chip" data-cat="妮姬个人">妮姬个人</button>
      <button class="chip" id="dynOnly">只看动态 CG</button>
      <span class="count" id="count"></span>
    </div>
    <div class="grid" id="grid"></div>
  </main>
</div>
<div class="lb" id="lb">
  <div class="top"><b id="lbTitle"></b><span id="lbWhere"></span>
    <span class="sp"><button id="prev">← 上一张</button><button id="next">下一张 →</button><button id="close">关闭</button></span>
  </div>
  <div class="body"><img id="lbImg" alt=""></div>
  <div class="cap" id="lbCap"></div>
</div>
<script>
const DATA = /*__DATA__*/[];
const ACTS = __ACTS__;
let cat = '全部', act = null, q = '', dynOnly = false;
let shown = [];

const el = id => document.getElementById(id);
const esc = s => (s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function renderSide(){
  const counts = new Map();
  for (const e of DATA) if (cat === '全部' || e.cat === cat) counts.set(e.act, (counts.get(e.act)||0)+1);
  const acts = [...counts.keys()].sort((a,b)=> a.localeCompare(b,'zh'));
  const side = el('side');
  side.innerHTML = `<div class="grp">章节 / 活动（${acts.length}）</div>` +
    `<button class="${act===null?'on':''}" data-act="">全部 <span>${[...counts.values()].reduce((a,b)=>a+b,0)}</span></button>` +
    acts.map(a=>`<button class="${act===a?'on':''}" data-act="${esc(a)}">${esc(a)} <span>${counts.get(a)}</span></button>`).join('');
  side.querySelectorAll('button').forEach(b=>b.onclick=()=>{ act = b.dataset.act || null; renderSide(); renderGrid(); });
}

function filtered(){
  const kw = q.trim().toLowerCase();
  return DATA.filter(e =>
    (cat === '全部' || e.cat === cat) &&
    (!act || e.act === act) &&
    (!dynOnly || e.dyn) &&
    (!kw || (e.text + e.cg + e.act + e.secTitle + e.who).toLowerCase().includes(kw))
  );
}

function renderGrid(){
  shown = filtered();
  el('count').textContent = `${shown.length} / ${DATA.length} 处`;
  if (!shown.length){ el('grid').innerHTML = '<div class="empty">没有匹配的条目</div>'; return; }
  el('grid').innerHTML = shown.map((e,idx)=>`
    <div class="card" data-idx="${idx}">
      <div class="thumb" style="${e.thumb?`background-image:url('缩略图/${encodeURIComponent(e.thumb)}')`:'background:#151922'}"></div>
      <div class="meta">
        <div class="where">${esc(e.act)} · ${esc(e.secTitle || e.sec)} · 第${e.line}行</div>
        <div class="name">${esc(e.cg)}</div>
        <div class="line">${e.who?`<span class="who">${esc(e.who)}</span>：`:''}${esc(e.text)}</div>
        <div class="badges">${e.dyn?'<span class="b dyn">动态 CG</span>':''}${e.match==='近似'?'<span class="b approx">近似匹配</span>':''}</div>
      </div>
    </div>`).join('');
  el('grid').querySelectorAll('.card').forEach(c=>c.onclick=()=>openLb(+c.dataset.idx));
}

let lbIdx = 0;
function openLb(i){
  lbIdx = i; const e = shown[i];
  el('lbTitle').textContent = e.cg;
  el('lbWhere').textContent = `${e.act} · ${e.secTitle || e.sec} · 第${e.line}行${e.who?' · '+e.who:''}`;
  const img = el('lbImg');
  if (e.full) { img.src = '../' + encodeURI(e.full); img.style.display='block'; }
  else { img.removeAttribute('src'); img.style.display='none'; }
  el('lbCap').innerHTML = `<b>台词：</b>${esc(e.text)}` + (e.dyn?` &nbsp;·&nbsp; <b>动态版：</b>${esc(e.dyn)}`:'');
  el('lb').classList.add('on');
}
el('close').onclick = ()=> el('lb').classList.remove('on');
el('lb').onclick = ev => { if (ev.target === el('lb')) el('lb').classList.remove('on'); };
el('prev').onclick = ()=> openLb((lbIdx-1+shown.length)%shown.length);
el('next').onclick = ()=> openLb((lbIdx+1)%shown.length);
document.addEventListener('keydown', e=>{
  if (!el('lb').classList.contains('on')) return;
  if (e.key==='Escape') el('lb').classList.remove('on');
  if (e.key==='ArrowLeft') el('prev').click();
  if (e.key==='ArrowRight') el('next').click();
});

el('q').oninput = e => { q = e.target.value; renderGrid(); };
document.querySelectorAll('.chip[data-cat]').forEach(c=>c.onclick=()=>{
  document.querySelectorAll('.chip[data-cat]').forEach(x=>x.classList.remove('on'));
  c.classList.add('on'); cat = c.dataset.cat; act = null; renderSide(); renderGrid();
});
el('dynOnly').onclick = ()=>{ dynOnly = !dynOnly; el('dynOnly').classList.toggle('on', dynOnly); renderGrid(); };

renderSide(); renderGrid();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
