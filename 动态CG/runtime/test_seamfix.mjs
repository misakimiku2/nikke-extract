/**
 * A/B test: stock canvas renderer vs seam-free renderer.
 * Usage: node test_seamfix.mjs <modelDir> <base> <time> <size> <outPrefix>
 */
import fs from 'fs';
import path from 'path';
import { createCanvas, loadImage } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];
const at = parseFloat(process.argv[4] || '1.2');
const size = parseInt(process.argv[5] || '900');
const out = process.argv[6] || './_ab';

const atlas = new spine.TextureAtlas(fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8'));
const img = await loadImage(path.join(dir, base + '.png'));
for (const page of atlas.pages) {
    page.setTexture(new spine.CanvasTexture(img));
    page.width = img.width;
    page.height = img.height;
}
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));

function pose() {
    const sk = new spine.Skeleton(data);
    if (data.defaultSkin) sk.setSkin(data.defaultSkin);
    sk.setSlotsToSetupPose();
    const st = new spine.AnimationState(new spine.AnimationStateData(data));
    const anims = data.animations.map(a => a.name);
    const intro = anims.find(a => /^intro/i.test(a));
    const idle = anims.find(a => /^idle/i.test(a)) || anims[0];
    const first = intro && anims.length > 1 ? intro : idle;
    st.setAnimation(0, first, true);
    if (intro && idle) st.addAnimation(0, idle, true, 0);
    st.update(at);
    st.apply(sk);
    sk.updateWorldTransform();
    return sk;
}

// bounds from setup-ish sampling
let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
const verts = new Array(8192).fill(0);
const sk0 = pose();
for (const slot of sk0.drawOrder) {
    const att = slot.getAttachment();
    if (!att || !att.computeWorldVertices) continue;
    try {
        if (att instanceof spine.MeshAttachment) {
            const n = att.worldVerticesLength;
            att.computeWorldVertices(slot, 0, n, verts, 0, 2);
            for (let i = 0; i < n; i += 2) {
                minX = Math.min(minX, verts[i]); maxX = Math.max(maxX, verts[i]);
                minY = Math.min(minY, verts[i + 1]); maxY = Math.max(maxY, verts[i + 1]);
            }
        }
    } catch (e) { }
}
if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = data.width; maxY = data.height; }
const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
const scale = Math.min(size / bw, size / bh) * 0.98;
const ox = (size - bw * scale) / 2 - minX * scale;
const oy = (size + bh * scale) / 2 + minY * scale;

function render(useFix) {
    const canvas = createCanvas(size, size);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#1b1f27';
    ctx.fillRect(0, 0, size, size);
    const r = useFix ? new SeamFreeRenderer(ctx) : new spine.SkeletonRenderer(ctx);
    if (useFix) r.padWorld = 0.7 / scale;
    else r.triangleRendering = true;
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, -scale);
    r.draw(sk0);
    ctx.restore();
    return canvas;
}

const a = render(false), b = render(true);
fs.writeFileSync(`${out}_stock.png`, a.toBuffer('image/png'));
fs.writeFileSync(`${out}_fixed.png`, b.toBuffer('image/png'));
console.log(JSON.stringify({ model: base, scale: +scale.toFixed(3), cropNote: 'saved stock/fixed' }));
