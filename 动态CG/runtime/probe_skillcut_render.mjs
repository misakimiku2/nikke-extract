// 显式渲染指定动画（render.mjs 固定用 animNames[0]，会漏 skillcut_1）
import fs from 'fs';
import { createCanvas } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures, applySlotOverrides } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];
const animName = process.argv[4];
const time = parseFloat(process.argv[5]);
const outFile = process.argv[6];
const outW = parseInt(process.argv[7] || '900');
const outH = parseInt(process.argv[8] || '1200');

const atlas = new spine.TextureAtlas(fs.readFileSync(dir + '/' + base + '.atlas', 'utf8'));
await prepareAtlasTextures(atlas, dir);

const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(dir + '/' + base + '.skel')));
const skeleton = new spine.Skeleton(data);
if (data.defaultSkin) skeleton.setSkin(data.defaultSkin);
skeleton.setSlotsToSetupPose();

const state = new spine.AnimationState(new spine.AnimationStateData(data));
state.setAnimation(0, animName, true);
const track = state.getCurrent(0);
if (track) track.trackTime = time;
state.update(0);
state.apply(skeleton);
applySlotOverrides(skeleton, base);
skeleton.updateWorldTransform();

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
            n = 8;
            att.computeWorldVertices(slot, verts, 0, 2);
        } else continue;
        for (let i = 0; i < n; i += 2) {
            const x = verts[i], y = verts[i + 1];
            if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
        }
    } catch (e) { /* skip */ }
}
if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = data.width; maxY = data.height; }
const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
const scale = Math.min(outW / bw, outH / bh) * 0.98;
const ox = (outW - bw * scale) / 2 - minX * scale;
const oy = (outH + bh * scale) / 2 + minY * scale;

const canvas = createCanvas(outW, outH);
const ctx = canvas.getContext('2d');

ctx.save();
ctx.translate(ox, oy);
ctx.scale(scale, -scale);
const renderer = new SeamFreeRenderer(ctx);
renderer.padWorld = 0.75 / scale;
renderer.draw(skeleton);
ctx.restore();
fs.writeFileSync(outFile, canvas.toBuffer('image/png'));
console.log(JSON.stringify({
    anim: animName, time, box: [minX, minY, maxX, maxY].map(v => Math.round(v)),
    scale: +scale.toFixed(4), out: outFile
}));
