"""Build a single-file HTML viewer for the exported NIKKE Spine dynamic CGs.

The Spine runtime (spine-canvas IIFE) is inlined, so the result is one .html
with zero external dependencies. Two load paths:
  * served over http(s): reads <model_dir>/<name>/{name}.atlas|.skel|.png
  * opened via file://: falls back to a folder picker / drag & drop
"""
import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parents[1]
MODELS = BASE / "动态CG" / "模型"
RUNTIME = BASE / "动态CG" / "_spine-canvas.min.js"
OUT = BASE / "动态CG" / "查看器.html"

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NIKKE 动态 CG 查看器</title>
<style>
  :root{
    --bg:#11131a; --panel:#1b1e28; --panel2:#242835; --line:#000;
    --ink:#f2f4f8; --muted:#8b93a7; --accent:#ffd23f; --accent2:#ff5c8a;
    --ok:#4ade80;
  }
  *{box-sizing:border-box}
  html,body{height:100%;margin:0}
  body{
    background:var(--bg); color:var(--ink);
    font:14px/1.5 "Segoe UI","Microsoft YaHei",system-ui,sans-serif;
    display:flex; flex-direction:column; overflow:hidden;
  }
  header{
    display:flex; align-items:center; gap:14px; padding:10px 14px;
    background:var(--accent); color:#111; border-bottom:3px solid var(--line);
  }
  header h1{font-size:15px; margin:0; letter-spacing:.5px; font-weight:800}
  header .sp{flex:1}
  .btn{
    border:2px solid var(--line); background:var(--panel2); color:var(--ink);
    padding:6px 12px; border-radius:6px; cursor:pointer; font-weight:700; font-size:13px;
    box-shadow:3px 3px 0 var(--line); transition:transform .06s, box-shadow .06s;
  }
  .btn:hover{transform:translate(-1px,-1px); box-shadow:4px 4px 0 var(--line)}
  .btn:active{transform:translate(2px,2px); box-shadow:1px 1px 0 var(--line)}
  .btn.on{background:var(--ok); color:#08210f}
  .btn.tiny{padding:3px 8px; font-size:12px; box-shadow:2px 2px 0 var(--line)}
  main{flex:1; display:flex; min-height:0}
  aside{
    width:260px; min-width:200px; background:var(--panel);
    border-right:3px solid var(--line); display:flex; flex-direction:column;
  }
  aside .tools{padding:8px; border-bottom:2px solid var(--line); display:flex; gap:6px; flex-wrap:wrap}
  aside input[type=search]{
    flex:1; min-width:100px; background:var(--panel2); border:2px solid var(--line);
    color:var(--ink); border-radius:5px; padding:5px 8px; font-size:12px;
  }
  #list{flex:1; overflow:auto}
  #list button{
    display:block; width:100%; text-align:left; background:none; border:0;
    border-bottom:1px solid #2c3040; color:var(--ink); padding:8px 10px;
    cursor:pointer; font-size:12px; font-family:inherit;
  }
  #list button:hover{background:var(--panel2)}
  #list button.sel{background:var(--accent); color:#111; font-weight:700}
  #stage{flex:1; position:relative; min-width:0; background:#0c0e14}
  canvas{display:block; width:100%; height:100%}
  .hud{
    position:absolute; left:12px; top:12px; font-size:12px; color:var(--muted);
    background:rgba(12,14,20,.72); padding:6px 10px; border-radius:6px;
    border:1px solid #2c3040; pointer-events:none; max-width:70%;
  }
  .empty{
    position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
    flex-direction:column; gap:10px; color:var(--muted); text-align:center; padding:20px;
  }
  .empty b{color:var(--ink)}
  footer{
    background:var(--panel); border-top:3px solid var(--line);
    padding:8px 14px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;
  }
  footer .grp{display:flex; align-items:center; gap:6px}
  footer label{font-size:12px; color:var(--muted)}
  input[type=range]{accent-color:var(--accent); width:120px}
  #tl{flex:1; min-width:160px}
  #time{font-variant-numeric:tabular-nums; font-size:12px; color:var(--muted); min-width:92px}
  .pill{
    font-size:11px; padding:2px 7px; border-radius:99px; border:1px solid #39405a;
    color:var(--muted);
  }
  .pill.live{color:#08210f; background:var(--ok); border-color:var(--ok); font-weight:700}
  @media (max-width:820px){ aside{width:180px} }
</style>
</head>
<body>
<header>
  <h1>NIKKE · 动态 CG</h1>
  <span class="pill" id="mode">载入中</span>
  <span class="sp"></span>
  <button class="btn tiny" id="pick">选择模型文件夹</button>
  <input id="dir" type="file" webkitdirectory multiple hidden>
</header>
<main>
  <aside>
    <div class="tools">
      <input id="q" type="search" placeholder="筛选模型…">
      <button class="btn tiny" id="prev" title="上一个 (↑)">↑</button>
      <button class="btn tiny" id="next" title="下一个 (↓)">↓</button>
    </div>
    <div id="list"></div>
  </aside>
  <div id="stage">
    <canvas id="cv"></canvas>
    <div class="empty" id="empty">
      <b>还没有载入模型</b>
      <span>直接拖入一个模型文件夹（含 .png / .atlas / .skel），<br>或点右上角选择导出目录 <code>动态CG\模型</code>。<br>通过 http 打开时会自动加载内置清单。</span>
    </div>
    <div class="hud" id="hud"></div>
  </div>
</main>
<footer>
  <div class="grp">
    <button class="btn tiny" id="play">⏸ 暂停</button>
    <button class="btn tiny" id="fit">适配</button>
  </div>
  <div class="grp">
    <input type="range" id="tl" min="0" max="1000" value="0">
    <span id="time">0.00 / 0.00 s</span>
  </div>
  <div class="grp">
    <label>动画</label>
    <select id="anim" class="btn tiny" style="box-shadow:none;padding:3px 6px"></select>
  </div>
  <div class="grp">
    <label>速度</label>
    <input type="range" id="speed" min="10" max="200" value="100" style="width:90px">
    <span class="pill" id="speedv">1.00×</span>
  </div>
  <div class="grp">
    <label>缩放</label>
    <input type="range" id="zoom" min="20" max="300" value="100" style="width:90px">
  </div>
  <div class="grp">
    <button class="btn tiny" id="bgmode">背景：深色</button>
    <button class="btn tiny" id="shot">导出当前帧</button>
  </div>
</footer>
<script>/*__RUNTIME__*/</script>
<script>
const MANIFEST = /*__MANIFEST__*/ [];
const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
const hud = document.getElementById('hud');
const emptyBox = document.getElementById('empty');
const listEl = document.getElementById('list');
const qEl = document.getElementById('q');
const tlEl = document.getElementById('tl');
const timeEl = document.getElementById('time');
const speedEl = document.getElementById('speed');
const speedV = document.getElementById('speedv');
const zoomEl = document.getElementById('zoom');
const modeEl = document.getElementById('mode');

let models = [];            // {name, folder, base}
let cur = null;             // loaded model
let skeleton = null, state = null, animStateData = null;
let playing = true, speed = 1, zoom = 1, bgMode = 0;
let box = null;             // cached bounds
const dpr = Math.min(2, window.devicePixelRatio || 1);
const renderer = new spine.SkeletonRenderer(ctx);
renderer.triangleRendering = true;

/* Seam fix: spine-canvas clips + drawImages per triangle, and Canvas AA on each
   clip edge leaves a ~1px crack, which makes every mesh look like a wireframe
   net. Dilate each triangle about its centroid by a sub-pixel pad so neighbours
   overlap and cover the cracks. */
(function installSeamFix() {
  const proto = spine.SkeletonRenderer.prototype;
  if (!proto || proto.__seamFix) return;
  proto.__seamFix = true;
  proto.drawTriangle = function (img, x0, y0, u0, v0, x1, y1, u1, v1, x2, y2, u2, v2) {
    const c = this.ctx, pad = this.padWorld || 0;
    if (pad > 0) {
      const cx = (x0 + x1 + x2) / 3, cy = (y0 + y1 + y2) / 3;
      const g = (x, y) => {
        const dx = x - cx, dy = y - cy, l = Math.hypot(dx, dy);
        if (l < 1e-6) return [x, y];
        const k = (l + pad) / l;
        return [cx + dx * k, cy + dy * k];
      };
      [x0, y0] = g(x0, y0); [x1, y1] = g(x1, y1); [x2, y2] = g(x2, y2);
    }
    u0 *= img.width; v0 *= img.height;
    u1 *= img.width; v1 *= img.height;
    u2 *= img.width; v2 *= img.height;
    c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.lineTo(x2, y2); c.closePath();
    x1 -= x0; y1 -= y0; x2 -= x0; y2 -= y0;
    u1 -= u0; v1 -= v0; u2 -= u0; v2 -= v0;
    const det = 1 / (u1 * v2 - u2 * v1);
    const a = (v2 * x1 - v1 * x2) * det, b = (v2 * y1 - v1 * y2) * det;
    const cc = (u1 * x2 - u2 * x1) * det, d = (u1 * y2 - u2 * y1) * det;
    const e = x0 - a * u0 - cc * v0, f = y0 - b * u0 - d * v0;
    c.save(); c.transform(a, b, cc, d, e, f); c.clip(); c.drawImage(img, 0, 0); c.restore();
  };
})();

function setMode(text, live) {
  modeEl.textContent = text;
  modeEl.classList.toggle('live', !!live);
}

/* ---------- model list ---------- */
function renderList() {
  const q = qEl.value.trim().toLowerCase();
  listEl.innerHTML = '';
  const shown = models.filter(m => !q || m.name.toLowerCase().includes(q));
  for (const m of shown) {
    const b = document.createElement('button');
    b.textContent = m.name;
    b.dataset.name = m.name;
    if (cur && cur.name === m.name) b.classList.add('sel');
    b.onclick = () => loadModel(m);
    listEl.appendChild(b);
  }
  hud.textContent = shown.length ? `${shown.length} 个模型` : '';
}

/* ---------- loading ---------- */
async function loadModel(m) {
  cur = null; skeleton = null; box = null;
  emptyBox.style.display = 'none';
  setMode('载入 ' + m.name);
  try {
    const atlasText = await readText(m, '.atlas');
    const skelBuf = await readBuffer(m, '.skel');
    const pageName = atlasText.split(/\r?\n/).map(x => x.trim())
      .find(x => x && !x.includes(':')) || (m.base + '.png');
    const img = await readImageFile(m, pageName);

    const atlas = new spine.TextureAtlas(atlasText);
    for (const page of atlas.pages) {
      page.setTexture(new spine.CanvasTexture(img));
      page.width = img.width; page.height = img.height;
    }
    const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
      .readSkeletonData(new Uint8Array(skelBuf));
    skeleton = new spine.Skeleton(data);
    if (data.defaultSkin) skeleton.setSkin(data.defaultSkin);
    skeleton.setSlotsToSetupPose();

    animStateData = new spine.AnimationStateData(data);
    state = new spine.AnimationState(animStateData);
    const anims = data.animations.map(a => a.name);
    cur = { name: m.name, data, anims, duration: data.animations[0]?.duration || 0 };
    buildAnimSelect(anims);

    // Game-style playback: play intro once, then loop idle if both exist.
    const intro = anims.find(a => /^intro/i.test(a));
    const idle = anims.find(a => /^idle/i.test(a)) || anims[0];
    playAnim(intro && anims.length > 1 ? intro : idle, intro ? idle : null);
    playing = true;
    document.getElementById('play').textContent = '⏸ 暂停';
    // pose the skeleton first, otherwise every bone world transform is identity
    // and the bounding box (and therefore the camera fit) is wrong.
    state.update(0);
    state.apply(skeleton);
    skeleton.updateWorldTransform();
    computeBox();
    resize();
    fitView();
    setMode(`${m.name} · ${anims.join('/') || '无动画'}`, true);
    [...listEl.children].forEach(b => b.classList.toggle('sel', b.dataset.name === m.name));
    document.getElementById('tl').max = Math.max(1, Math.round(cur.duration * 1000));
    hud.textContent = `${data.bones.length} 骨骼 · ${data.slots.length} 插槽 · ${anims.length} 动画 · ${cur.duration.toFixed(2)}s`;
  } catch (e) {
    console.error(e);
    setMode('载入失败');
    hud.textContent = '载入失败：' + e.message;
  }
}

async function readText(m, ext) { return await (await fetch(m.folder + m.base + ext)).text(); }
async function readBuffer(m, ext) { return await (await fetch(m.folder + m.base + ext)).arrayBuffer(); }
async function readImageFile(m, file) {
  const blob = await (await fetch(m.folder + file)).blob();
  const url = URL.createObjectURL(blob);
  try { return await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; }); }
  finally { setTimeout(() => URL.revokeObjectURL(url), 5000); }
}
async function readImage(m, ext) {
  const blob = await (await fetch(m.folder + m.base + ext)).blob();
  const url = URL.createObjectURL(blob);
  try { return await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; }); }
  finally { setTimeout(() => URL.revokeObjectURL(url), 5000); }
}

/* ---------- view ---------- */
function buildAnimSelect(anims) {
  const sel = document.getElementById('anim');
  sel.innerHTML = '';
  for (const a of anims) {
    const o = document.createElement('option');
    o.value = a; o.textContent = a;
    sel.appendChild(o);
  }
  sel.disabled = anims.length < 2;
}

function playAnim(name, chainTo) {
  if (!state || !cur) return;
  const entry = state.setAnimation(0, name, true);
  if (chainTo) state.addAnimation(0, chainTo, true, 0);
  const def = cur.data.animations.find(a => a.name === name);
  cur.duration = def?.duration || 1;
  document.getElementById('anim').value = name;
  document.getElementById('tl').max = Math.max(1, Math.round(cur.duration * 1000));
  document.getElementById('tl').value = 0;
}

function computeBox() {
  if (!skeleton) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const verts = new Array(4096).fill(0);
  for (const slot of skeleton.drawOrder) {
    const att = slot.getAttachment();
    if (!att || !att.computeWorldVertices) continue;
    let n = 0;
    try {
      if (att instanceof spine.MeshAttachment) {
        n = att.worldVerticesLength;
        att.computeWorldVertices(slot, 0, n, verts, 0, 2);
      } else if (att instanceof spine.RegionAttachment) {
        n = 8; att.computeWorldVertices(slot, verts, 0, 2);
      } else continue;
      for (let i = 0; i < n; i += 2) {
        const x = verts[i], y = verts[i + 1];
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
    } catch (e) {}
  }
  if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = cur.data.width; maxY = cur.data.height; }
  box = { minX, minY, maxX, maxY };
}

let view = { scale: 1, ox: 0, oy: 0 };
function fitView() {
  if (!box) return;
  const W = cv.clientWidth, H = cv.clientHeight;
  const bw = Math.max(1, box.maxX - box.minX), bh = Math.max(1, box.maxY - box.minY);
  const s = Math.min(W / bw, H / bh) * 0.96 * zoom;
  view.scale = s;
  view.ox = (W - bw * s) / 2 - box.minX * s;
  view.oy = (H + bh * s) / 2 + box.minY * s;
}

/* ---------- loop ---------- */
let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (cur && state && skeleton) {
    if (playing) {
      state.update(dt * speed);
      state.apply(skeleton);
      skeleton.updateWorldTransform();
    }
  }
  paint();
  requestAnimationFrame(frame);
}

function paint() {
  const W = cv.width, H = cv.height;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (bgMode === 0) { ctx.fillStyle = '#0c0e14'; ctx.fillRect(0, 0, W, H); }
  else if (bgMode === 1) { ctx.fillStyle = '#20242c'; ctx.fillRect(0, 0, W, H); }
  else ctx.clearRect(0, 0, W, H);

  if (cur && skeleton) {
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.translate(view.ox, view.oy);
    ctx.scale(view.scale, -view.scale);
    renderer.padWorld = 0.8 / Math.max(1e-6, view.scale * dpr);
    renderer.draw(skeleton);
    ctx.restore();
  }
  if (cur && state.getCurrent(0)) {
    const t = state.getCurrent(0).trackTime || 0;
    tlEl.value = Math.min(1000, Math.round(t / Math.max(cur.duration, 0.001) * 1000));
    timeEl.textContent = `${t.toFixed(2)} / ${cur.duration.toFixed(2)} s`;
  }
}

function resize() {
  cv.width = Math.round(cv.clientWidth * dpr);
  cv.height = Math.round(cv.clientHeight * dpr);
  fitView();
}
window.addEventListener('resize', resize);

/* ---------- controls ---------- */
document.getElementById('play').onclick = (e) => {
  playing = !playing;
  e.target.textContent = playing ? '⏸ 暂停' : '▶ 播放';
};
document.getElementById('fit').onclick = () => { zoom = 1; zoomEl.value = 100; fitView(); };
document.getElementById('prev').onclick = () => step(-1);
document.getElementById('next').onclick = () => step(1);
function step(d) {
  if (!models.length) return;
  const i = Math.max(0, models.findIndex(m => cur && m.name === cur.name));
  const j = (i + d + models.length) % models.length;
  loadModel(models[j]);
}
document.getElementById('anim').onchange = (e) => { playAnim(e.target.value, null); playing = true;
  document.getElementById('play').textContent = '⏸ 暂停'; };
speedEl.oninput = () => { speed = speedEl.value / 100; speedV.textContent = speed.toFixed(2) + '×'; };
zoomEl.oninput = () => { zoom = zoomEl.value / 100; fitView(); };
tlEl.oninput = () => {
  if (!cur || !state) return;
  const t = tlEl.value / 1000 * cur.duration;
  state.getCurrent(0).trackTime = t;
  state.getCurrent(0).animationLast = -1;
  state.apply(skeleton); skeleton.updateWorldTransform();
};
document.getElementById('bgmode').onclick = (e) => {
  bgMode = (bgMode + 1) % 3;
  e.target.textContent = '背景：' + ['深色', '浅灰', '透明'][bgMode];
};
document.getElementById('shot').onclick = () => {
  const a = document.createElement('a');
  a.download = (cur ? cur.name : 'frame') + '.png';
  a.href = cv.toDataURL('image/png');
  a.click();
};
qEl.oninput = renderList;
window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code === 'Space') { e.preventDefault(); document.getElementById('play').click(); }
  if (e.code === 'ArrowUp') { e.preventDefault(); step(-1); }
  if (e.code === 'ArrowDown') { e.preventDefault(); step(1); }
  if (e.key === 'f') document.getElementById('fit').click();
});

/* ---------- folder picking / drag & drop ---------- */
document.getElementById('pick').onclick = () => document.getElementById('dir').click();
function addModelFile(groups, prefix, f, name) {
  let base, ext, isPage = false;
  if (name.endsWith('.spine.png')) { ext = '.png'; base = name.slice(0, -10); isPage = true; }
  else { ext = name.slice(name.lastIndexOf('.')); base = name.slice(0, name.lastIndexOf('.')); }
  if (!['.png', '.atlas', '.skel'].includes(ext)) return;
  const key = prefix + base;
  if (!groups.has(key)) groups.set(key, { base, files: {} });
  const g = groups.get(key);
  if (ext === '.png') {
    if (isPage || !g.files['.png']) g.files['.png'] = f;
  } else g.files[ext] = f;
}

document.getElementById('dir').onchange = async (e) => {
  const files = [...e.target.files];
  const groups = new Map();
  for (const f of files) {
    const rel = f.webkitRelativePath || f.name;
    const dir = rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/')) : '';
    addModelFile(groups, dir, f, f.name);
  }
  const out = [];
  for (const [k, g] of groups) {
    if (!g.files['.atlas'] || !g.files['.skel'] || !g.files['.png']) continue;
    const urls = {};
    for (const ext of ['.png', '.atlas', '.skel']) urls[ext] = URL.createObjectURL(g.files[ext]);
    out.push({
      name: g.base,
      base: g.base + '',
      folder: '',
      _urls: urls
    });
  }
  if (!out.length) { hud.textContent = '没有找到完整的三件套（.png/.atlas/.skel）'; return; }
  models = out;
  // patch fetch-based loader to use blob URLs
  for (const m of models) { m.folder = '__blob__' + m.name + '__'; }
  const origFetch = window.fetch;
  window.fetch = (u, o) => {
    if (typeof u === 'string' && u.startsWith('__blob__')) {
      const mm = models.find(x => u.startsWith('__blob__' + x.name + '__'));
      if (mm) {
        const ext = u.slice(u.lastIndexOf('.'));
        return origFetch(mm._urls[ext], o);
      }
    }
    return origFetch(u, o);
  };
  renderList();
  setMode('本地文件夹', true);
  await loadModel(models[0]);
};

document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', async (e) => {
  e.preventDefault();
  const items = [...(e.dataTransfer?.items || [])];
  const files = [];
  async function walk(entry, path) {
    if (entry.isFile) {
      const f = await new Promise((res, rej) => entry.file(res, rej));
      f._path = path + f.name;
      files.push(f);
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const entries = await new Promise(res => reader.readEntries(res));
      for (const en of entries) await walk(en, path + entry.name + '/');
    }
  }
  for (const it of items) {
    const entry = it.webkitGetAsEntry && it.webkitGetAsEntry();
    if (entry) await walk(entry, '');
  }
  if (!files.length) return;
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(new File([f], f.name));
  // reuse folder handler by synthesising webkitRelativePath
  const groups = new Map();
  for (const f of files) {
    const rel = f._path || f.name;
    const dir = rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/') + 1) : '';
    addModelFile(groups, dir, f, f.name);
  }
  const out = [];
  for (const [k, g] of groups) {
    if (!g.files['.atlas'] || !g.files['.skel'] || !g.files['.png']) continue;
    const urls = {};
    for (const ext of ['.png', '.atlas', '.skel']) urls[ext] = URL.createObjectURL(g.files[ext]);
    out.push({ name: g.base, base: g.base, folder: '', _urls: urls });
  }
  if (!out.length) { hud.textContent = '拖入的文件夹里没有完整三件套'; return; }
  models = out;
  for (const m of models) m.folder = '__blob__' + m.name + '__';
  const origFetch2 = window.fetch;
  window.fetch = (u, o) => {
    if (typeof u === 'string' && u.startsWith('__blob__')) {
      const mm = models.find(x => u.startsWith('__blob__' + x.name + '__'));
      if (mm) return origFetch2(mm._urls[u.slice(u.lastIndexOf('.'))], o);
    }
    return origFetch2(u, o);
  };
  renderList();
  setMode('拖入的文件夹', true);
  await loadModel(models[0]);
});

/* ---------- boot ---------- */
resize();
renderList();
if (MANIFEST.length) {
  models = MANIFEST.map(m => ({
    name: m.name,
    base: m.name,
    folder: m.folder
  }));
  renderList();
  setMode('内置清单', true);
  // deep link: 查看器.html?model=EventScene_Marian_01  (also accept ?m=)
  const qs = new URLSearchParams(location.search);
  const want = (qs.get('model') || qs.get('m') || '').toLowerCase();
  const hit = want && models.find(x => x.name.toLowerCase() === want);
  loadModel(hit || models[0]);
} else {
  setMode('等待载入', false);
}
requestAnimationFrame(frame);
</script>
</body>
</html>
"""


def main():
    runtime = RUNTIME.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    cg_root = BASE / "CG"
    manifest = []
    for atlas in sorted(cg_root.rglob("*.atlas")):
        rel = atlas.parent.relative_to(BASE).as_posix()
        manifest.append({"name": atlas.stem, "folder": "../" + rel + "/"})
    models = [m["name"] for m in manifest]
    html = HTML.replace("/*__RUNTIME__*/", runtime).replace(
        "/*__MANIFEST__*/ []", json.dumps(manifest, ensure_ascii=False)
    )
    OUT.write_text(html, encoding="utf-8")
    print("models", len(models), "size", round(len(html) / 1024, 1), "KB ->", OUT)


if __name__ == "__main__":
    main()
