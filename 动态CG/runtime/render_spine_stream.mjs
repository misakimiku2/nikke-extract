/**
 * Stream rendered Spine frames as a PNG sequence to stdout (no temp files).
 * Diagnostics go to stderr so stdout stays a clean image2pipe stream.
 *
 * Usage: node render_spine_stream.mjs <modelDir> <base> [fps] [size]
 */
import fs from 'fs';
import path from 'path';
import { createCanvas } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures, applySlotOverrides } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];
const fps = parseInt(process.argv[4] || '20');
const size = parseInt(process.argv[5] || '640');

const atlas = new spine.TextureAtlas(fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8'));
await prepareAtlasTextures(atlas, dir);

const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));
const skeleton = new spine.Skeleton(data);
if (data.defaultSkin) skeleton.setSkin(data.defaultSkin);
skeleton.setSlotsToSetupPose();
applySlotOverrides(skeleton, base);

const stateData = new spine.AnimationStateData(data);
const state = new spine.AnimationState(stateData);
const anims = data.animations.map(a => a.name);
if (!anims.length) { console.error('no animation'); process.exit(2); }

// Prefer intro -> idle chaining, else first animation.
const pick = (re) => anims.find(a => re.test(a));
const intro = pick(/^intro/i);
const idle = pick(/^idle/i) || anims[0];
const first = intro && anims.length > 1 ? intro : idle;
state.setAnimation(0, first, true);
if (intro && idle) state.addAnimation(0, idle, true, 0);

// Sample the whole clip for a stable camera.
const total = (intro ? (data.animations.find(a => a.name === intro)?.duration || 0) : 0)
    + (data.animations.find(a => a.name === idle)?.duration || 0.1);

let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
const verts = new Array(4096).fill(0);
const probe = Math.max(1 / 12, total / 48);
const st2 = new spine.AnimationState(new spine.AnimationStateData(data));
st2.setAnimation(0, first, true);
if (intro && idle) st2.addAnimation(0, idle, true, 0);
const sk2 = new spine.Skeleton(data);
if (data.defaultSkin) sk2.setSkin(data.defaultSkin);
sk2.setSlotsToSetupPose();
for (let t = 0; t <= total; t += probe) {
    if (t > 0) st2.update(probe);
    st2.apply(sk2);
    applySlotOverrides(sk2, base);
    sk2.updateWorldTransform();
    for (const slot of sk2.drawOrder) {
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
        } catch (e) { /* ignore odd vertex layouts */ }
    }
}
if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = data.width; maxY = data.height; }

const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
const scale = Math.min(size / bw, size / bh) * 0.98;
const ox = (size - bw * scale) / 2 - minX * scale;
const oy = (size + bh * scale) / 2 + minY * scale;

const canvas = createCanvas(size, size);
const ctx = canvas.getContext('2d');
const renderer = new SeamFreeRenderer(ctx);
// sub-pixel dilation in world units: ~0.75 device px closes the clip-AA cracks
renderer.padWorld = 0.75 / scale;

const frames = Math.max(1, Math.round(total * fps));
const dt = 1 / fps;
for (let f = 0; f < frames; f++) {
    if (f > 0) {
        state.update(dt);
        state.apply(skeleton);
        applySlotOverrides(skeleton, base);
        skeleton.updateWorldTransform();
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, -scale);
    renderer.draw(skeleton);
    ctx.restore();
    const buf = canvas.toBuffer('image/png');
    if (!process.stdout.write(buf)) {
        await new Promise(r => process.stdout.once('drain', r));
    }
}
console.error(JSON.stringify({
    model: base, anim: first + (intro && idle ? '+' + idle : ''),
    duration: +total.toFixed(3), fps, frames, size
}));
