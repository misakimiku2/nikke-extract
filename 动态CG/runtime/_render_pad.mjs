/**
 * Render one Spine model to a still PNG (transparent background, seam-free).
 * Usage: node render_static.mjs <dir> <base> <out.png> [size] [time]
 * The atlas page image is read from the atlas' first line, so renamed sheets work.
 */
import fs from 'fs';
import path from 'path';
import { createCanvas } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures, applySlotOverrides } from './spine-seamfix.mjs';

// 少数模型（如芭比珑 c908、嚣嘈 c909）的 skel 引用了序列帧 arm_h_l01，
// 但客户端图集只打了基础帧 arm_h_l。缺帧时退回基础区域，否则整只模型会加载失败。
const origLoadSequence = spine.AtlasAttachmentLoader.prototype.loadSequence;
spine.AtlasAttachmentLoader.prototype.loadSequence = function (name, basePath, sequence) {
    const regions = sequence.regions;
    for (let i = 0; i < regions.length; i++) {
        const p = sequence.getPath(basePath, i);
        let region = this.atlas.findRegion(p);
        if (!region) region = this.atlas.findRegion(basePath);
        if (!region) throw new Error('Region not found in atlas: ' + p + ' (sequence: ' + name + ')');
        regions[i] = region;
    }
};

const dir = process.argv[2];
const base = process.argv[3];
const out = process.argv[4];
const size = parseInt(process.argv[5] || '2048');
const at = parseFloat(process.argv[6] || '1.2');

const atlasText = fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8');
const atlas = new spine.TextureAtlas(atlasText);
// 图集是 pma:true，Canvas2D 需要直通 alpha，否则半透明层（腮红/发光）会被乘两次 alpha。
// 双页 atlas 需要各页加载各自的贴图。
await prepareAtlasTextures(atlas, dir);
const pageName = atlas.pages[0]?.name || (base + '.png');

const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));

const sk = new spine.Skeleton(data);
if (data.defaultSkin) sk.setSkin(data.defaultSkin);
sk.setSlotsToSetupPose();

const st = new spine.AnimationState(new spine.AnimationStateData(data));
const anims = data.animations.map(a => a.name);
const intro = anims.find(a => /^intro/i.test(a));
const idle = anims.find(a => /^idle/i.test(a)) || anims[0];
if (idle) st.setAnimation(0, intro && anims.length > 1 ? intro : idle, true);
if (intro && idle) st.addAnimation(0, idle, true, 0);
st.update(at);
st.apply(sk);
// 与网页实时模型共用 spine_overrides.json：摘掉这张 CG 自带的暗角画框等装饰层
const hiddenCount = applySlotOverrides(sk, base);
sk.updateWorldTransform();

// stable framing: union of bounds sampled across the clip
const total = (intro ? (data.animations.find(a => a.name === intro)?.duration || 0) : 0)
    + (data.animations.find(a => a.name === idle)?.duration || 0.1);
const probe = Math.max(1 / 12, total / 40);
const st2 = new spine.AnimationState(new spine.AnimationStateData(data));
if (idle) st2.setAnimation(0, intro && anims.length > 1 ? intro : idle, true);
if (intro && idle) st2.addAnimation(0, idle, true, 0);
const sk2 = new spine.Skeleton(data);
if (data.defaultSkin) sk2.setSkin(data.defaultSkin);
sk2.setSlotsToSetupPose();
const verts = new Array(8192).fill(0);
let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
for (let t = 0; t <= total; t += probe) {
    if (t > 0) st2.update(probe);
    st2.apply(sk2);
    applySlotOverrides(sk2, base);
    sk2.updateWorldTransform();
    for (const slot of sk2.drawOrder) {
        const att = slot.getAttachment();
        if (!att?.computeWorldVertices) continue;
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
                minX = Math.min(minX, x); maxX = Math.max(maxX, x);
                minY = Math.min(minY, y); maxY = Math.max(maxY, y);
            }
        } catch (e) { /* skip odd layouts */ }
    }
}
if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = data.width; maxY = data.height; }

function frameTo(sizePx, box) {
    const bw = Math.max(1, box.maxX - box.minX), bh = Math.max(1, box.maxY - box.minY);
    const scale = Math.min(sizePx / bw, sizePx / bh) * 0.985;
    const ox = (sizePx - bw * scale) / 2 - box.minX * scale;
    const oy = (sizePx + bh * scale) / 2 + box.minY * scale;
    const canvas = createCanvas(sizePx, sizePx);
    const ctx = canvas.getContext('2d');
    const renderer = new SeamFreeRenderer(ctx);
    renderer.padWorld = 0.5 / scale;
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, -scale);
    renderer.draw(sk);
    ctx.restore();
    return { canvas, ctx, scale, ox, oy };
}

function alphaBox(ctx, sizePx) {
    const data = ctx.getImageData(0, 0, sizePx, sizePx).data;
    let x0 = sizePx, y0 = sizePx, x1 = -1, y1 = -1;
    for (let y = 0; y < sizePx; y++) {
        for (let x = 0; x < sizePx; x++) {
            if (data[(y * sizePx + x) * 4 + 3] > 8) {
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
                if (y < y0) y0 = y;
                if (y > y1) y1 = y;
            }
        }
    }
    return x1 < 0 ? null : { x0, y0, x1, y1 };
}

// pass 1: cheap probe to find the real (alpha) content bounds
const probePx = 384;
const pr = frameTo(probePx, { minX, minY, maxX, maxY });
const pb = alphaBox(pr.ctx, probePx);
let box = { minX, minY, maxX, maxY };
if (pb) {
    const wx = px => (px - pr.ox) / pr.scale;
    const wy = py => (pr.oy - py) / pr.scale;
    box = {
        minX: wx(pb.x0), maxX: wx(pb.x1),
        minY: wy(pb.y1), maxY: wy(pb.y0),
    };
}

// pass 2: final render framed to the real content
// 超采样：三角形扩张只能盖住大部分接缝，1px 的裂缝在缩小显示时会变成摩尔纹（脸上灰色网点）。
// 按 SS 倍分辨率渲染再降采样，接缝被平均掉。
const SS = Math.max(1, parseInt(process.env.SS || '2'));
const { canvas } = frameTo(size * SS, box);

let finalCanvas = canvas;
if (SS > 1) {
    finalCanvas = createCanvas(size, size);
    const fctx = finalCanvas.getContext('2d');
    fctx.imageSmoothingEnabled = true;
    fctx.imageSmoothingQuality = 'high';
    fctx.drawImage(canvas, 0, 0, size, size);
}

fs.writeFileSync(out, finalCanvas.toBuffer('image/png'));
console.log(JSON.stringify({
    model: base, page: pageName, bones: data.bones.length, slots: data.slots.length,
    anims, size, ss: SS, hiddenSlots: hiddenCount, out,
}));
