/**
 * Sample the camera bone trajectory of a skillcut skeleton and find cut points.
 * Usage: node probe_camera.mjs <dir> <base> [anim]
 * Prints: animation list, camera bone name, translation jumps (t, distance).
 */
import fs from 'fs';
import path from 'path';
import * as spine from '@esotericsoftware/spine-canvas';
import { prepareAtlasTextures } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];
const wantAnim = process.argv[4] || '';

const atlasText = fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8');
const atlas = new spine.TextureAtlas(atlasText);
await prepareAtlasTextures(atlas, dir);
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));

console.log('animations:');
for (const a of data.animations) console.log(`  ${a.name}  ${a.duration.toFixed(2)}s`);

const sk = new spine.Skeleton(data);
if (data.defaultSkin) sk.setSkin(data.defaultSkin);
sk.setSlotsToSetupPose();

const cam = sk.bones.find(b => /^camera$/i.test(b.data.name)) || null;
if (!cam) { console.log('no camera bone; bones:', sk.bones.map(b => b.data.name).join(', ')); process.exit(0); }
console.log('camera bone found:', cam.data.name);

const anim = wantAnim
    ? data.animations.find(a => a.name === wantAnim)
    : data.animations.find(a => /^skillcut/i.test(a.name))
        || data.animations.reduce((m, a) => (a.duration > (m?.duration || 0) ? a : m), null);
console.log(`sampling: ${anim.name} (${anim.duration.toFixed(2)}s)`);

const st = new spine.AnimationState(new spine.AnimationStateData(data));
const track = st.setAnimation(0, anim.name, false);

const N = 480;
const pts = [];
for (let i = 0; i <= N; i++) {
    track.trackTime = (i / N) * anim.duration;
    st.update(0);
    st.apply(sk);
    sk.updateWorldTransform();
    pts.push([track.trackTime, cam.worldX, cam.worldY]);
}

// step sizes; a cut = translation jump far above the local median step
const steps = [];
for (let i = 1; i <= N; i++) {
    steps.push(Math.hypot(pts[i][1] - pts[i - 1][1], pts[i][2] - pts[i - 1][2]));
}
const med = [...steps].sort((a, b) => a - b)[Math.floor(steps.length / 2)];
console.log(`median step: ${med.toFixed(1)}`);

const cuts = [];
for (let i = 1; i <= N; i++) {
    if (steps[i - 1] > Math.max(med * 12, 120)) {
        cuts.push({ t: pts[i][0], d: steps[i - 1], from: pts[i - 1].slice(1), to: pts[i].slice(1) });
    }
}
// merge consecutive samples of the same jump
const merged = [];
for (const c of cuts) {
    const last = merged[merged.length - 1];
    if (last && c.t - last.t < anim.duration / N * 3) { last.d = Math.max(last.d, c.d); last.t = c.t; }
    else merged.push({ ...c });
}
console.log(`cut points: ${merged.length}`);
for (const c of merged) {
    console.log(`  t=${c.t.toFixed(3)}s (${(c.t / anim.duration * 100).toFixed(1)}%)  jump=${c.d.toFixed(0)}  (${c.from.map(v => v.toFixed(0))}) -> (${c.to.map(v => v.toFixed(0))})`);
}
// trajectory summary every 10%
for (let k = 0; k <= 10; k++) {
    const p = pts[Math.min(Math.floor(k / 10 * N), N)];
    console.log(`  t=${p[0].toFixed(2)}  x=${p[1].toFixed(0)}  y=${p[2].toFixed(0)}`);
}
