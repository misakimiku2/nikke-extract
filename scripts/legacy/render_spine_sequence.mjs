/**
 * Render a Spine animation to a PNG frame sequence (for ffmpeg -> WebM/WebP/GIF).
 *
 * Usage:
 *   node render_spine_sequence.mjs <modelDir> <base> <framesDir> [fps] [size] [seconds]
 *
 * Keeps one skeleton instance and advances it frame by frame so the exported
 * clip matches the runtime playback exactly.
 */
import fs from 'fs';
import path from 'path';
import { createCanvas, loadImage } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';

const dir = process.argv[2];
const base = process.argv[3];
const framesDir = process.argv[4];
const fps = parseInt(process.argv[5] || '30');
const size = parseInt(process.argv[6] || '900');
const maxSeconds = parseFloat(process.argv[7] || '0');   // 0 = full animation

fs.mkdirSync(framesDir, { recursive: true });

const atlas = new spine.TextureAtlas(fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8'));
const img = await loadImage(path.join(dir, base + '.png'));
for (const page of atlas.pages) {
    page.setTexture(new spine.CanvasTexture(img));
    page.width = img.width;
    page.height = img.height;
}

const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));
const skeleton = new spine.Skeleton(data);
if (data.defaultSkin) skeleton.setSkin(data.defaultSkin);
skeleton.setSlotsToSetupPose();

const stateData = new spine.AnimationStateData(data);
const state = new spine.AnimationState(stateData);
const anim = data.animations[0];
if (!anim) { console.error('no animation'); process.exit(2); }
state.setAnimation(0, anim.name, true);
state.update(0);
state.apply(skeleton);
skeleton.updateWorldTransform();

// bounding box over the whole clip so the camera never jitters
let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
const verts = new Array(4096).fill(0);
const total = maxSeconds > 0 ? Math.min(maxSeconds, anim.duration) : anim.duration;
const probeStep = 1 / 12;

for (let t = 0; t < total; t += probeStep) {
    state.update(t === 0 ? 0 : probeStep);
    state.apply(skeleton);
    skeleton.updateWorldTransform();
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
        } catch (e) { /* ignore odd vertex layouts */ }
    }
}
if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = data.width; maxY = data.height; }

const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
const scale = Math.min(size / bw, size / bh) * 0.98;
const ox = (size - bw * scale) / 2 - minX * scale;
const oy = (size + bh * scale) / 2 + minY * scale;

// restart from t=0 with a fresh state for deterministic frames
state.clearTracks();
state.setAnimation(0, anim.name, true);
state.update(0);
state.apply(skeleton);
skeleton.updateWorldTransform();

const canvas = createCanvas(size, size);
const ctx = canvas.getContext('2d');
const renderer = new spine.SkeletonRenderer(ctx);
renderer.triangleRendering = true;

const frameCount = Math.max(1, Math.round(total * fps));
const dt = 1 / fps;
for (let f = 0; f < frameCount; f++) {
    if (f > 0) {
        state.update(dt);
        state.apply(skeleton);
        skeleton.updateWorldTransform();
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, -scale);
    renderer.draw(skeleton);
    ctx.restore();
    const name = 'f' + String(f).padStart(5, '0') + '.png';
    fs.writeFileSync(path.join(framesDir, name), canvas.toBuffer('image/png'));
}
console.log(JSON.stringify({
    model: base, anim: anim.name, duration: +total.toFixed(3),
    fps, frames: frameCount, size,
    box: [minX, minY, maxX, maxY].map(v => Math.round(v))
}));
