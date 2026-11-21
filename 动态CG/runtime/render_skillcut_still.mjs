// 批量重渲 skillcut 大招定格帧（单进程：一次加载骨架，采样选帧 + 成品输出）。
//
// 选帧规则：整条动画均匀采样，主指标取「彩色像素数」最多的一帧（人物与彩色
// 特效最完整），并列时依次比彩色占比（压掉白闪/烟雾帧，如 c017_01 的
// skillcut_1 后半段整屏白）与包围盒紧致度（人物更大）；整条动画都低彩色的
// 模型退回最大包围盒帧。
//
// 用法：node render_skillcut_still.mjs <dir> <base> <anim> <outPng> [samples] [size]
// stdout 末行：JSON {anim, time, colored, area, box, out}
import fs from 'fs';
import { createCanvas } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures, applySlotOverrides } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];
const animName = process.argv[4];
const outFile = process.argv[5];
const SAMPLES = parseInt(process.argv[6] || '16');
const SIZE = parseInt(process.argv[7] || '2048');

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
if (!track) {
    console.error('no such animation: ' + animName);
    process.exit(2);
}
const dur = Math.max(0.01, track.animation.duration);

const verts = new Array(4096).fill(0);

/** 把骨架摆到动画第 t 秒，返回 {box, area, opaque, colored}（附带渲小样统计彩色占比） */
function frameAt(t) {
    track.trackTime = t;
    state.update(0);
    state.apply(skeleton);
    applySlotOverrides(skeleton, base);
    skeleton.updateWorldTransform();

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
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
        } catch (e) { /* 个别 attachment 算不动就跳过 */ }
    }
    if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = data.width; maxY = data.height; }
    const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);

    // 160² 小样：统计不透明 / 彩色像素占比（彩色 = RGB 通道差明显，白闪帧接近 0）
    const S = 160;
    const scale = Math.min(S / bw, S / bh) * 0.98;
    const ox = (S - bw * scale) / 2 - minX * scale;
    const oy = (S + bh * scale) / 2 + minY * scale;
    const cv = createCanvas(S, S);
    const c = cv.getContext('2d');
    c.save();
    c.translate(ox, oy);
    c.scale(scale, -scale);
    const r = new SeamFreeRenderer(c);
    r.padWorld = 0.75 / scale;
    r.draw(skeleton);
    c.restore();
    const id = c.getImageData(0, 0, S, S).data;
    let opaque = 0, colored = 0;
    for (let i = 0; i < id.length; i += 4) {
        if (id[i + 3] < 64) continue;
        opaque++;
        const mx = Math.max(id[i], id[i + 1], id[i + 2]);
        const mn = Math.min(id[i], id[i + 1], id[i + 2]);
        if (mx - mn > 10) colored++;
    }
    return { t, box: [minX, minY, maxX, maxY], area: bw * bh, opaque, colored };
}

// 选帧：主指标 = 彩色像素数（人物+彩色特效最多的时刻）；并列 10% 内依次比
// 彩色占比（压掉白闪/烟雾帧）、包围盒面积（更紧致 = 人物更大）。整条动画
// 都是低彩色的模型（如白烟主导的大招）退化回最大包围盒帧。
const samples = [];
for (let i = 0; i < SAMPLES; i++) {
    samples.push(frameAt(dur * (i + 0.5) / SAMPLES));
}
const bestCount = Math.max(...samples.map((s) => s.colored));
let pool = samples.filter((s) => s.opaque > 0 && s.colored >= Math.max(1, bestCount * 0.9));
if (!pool.length) pool = samples.filter((s) => s.opaque > 0);
const best = (pool.length ? pool : samples).reduce((a, b) => {
    if (b.colored !== a.colored) return b.colored > a.colored ? b : a;
    if (Math.abs(b.colored / Math.max(1, b.opaque) - a.colored / Math.max(1, a.opaque)) > 0.02)
        return b.colored / Math.max(1, b.opaque) > a.colored / Math.max(1, a.opaque) ? b : a;
    return b.area < a.area ? b : a;
});

// 成品：回到选中帧，按该帧包围盒 auto-fit 输出 SIZE² 透明底 PNG
const f = frameAt(best.t);
const bw = Math.max(1, f.box[2] - f.box[0]), bh = Math.max(1, f.box[3] - f.box[1]);
const scale = Math.min(SIZE / bw, SIZE / bh) * 0.98;
const ox = (SIZE - bw * scale) / 2 - f.box[0] * scale;
const oy = (SIZE + bh * scale) / 2 + f.box[1] * scale;
const canvas = createCanvas(SIZE, SIZE);
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
    anim: animName,
    time: +best.t.toFixed(3),
    colored: +(best.colored / Math.max(1, best.opaque)).toFixed(2),
    area: Math.round(best.area),
    box: f.box.map((v) => Math.round(v)),
    out: outFile,
}));
