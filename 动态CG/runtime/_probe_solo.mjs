import fs from 'fs';
import path from 'path';
import { createCanvas } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures, applySlotOverrides } from './spine-seamfix.mjs';

const base = process.argv[2] || 'c094_00';
const dir = 'E:/test/nikke-web/public/spine_char/' + base;
const OUT = 'E:/test/nikke_extract/staging/_probe_c094';

const atlas = new spine.TextureAtlas(fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8'));
await prepareAtlasTextures(atlas, dir);
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
  .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));
const sk = new spine.Skeleton(data);
if (data.defaultSkin) sk.setSkin(data.defaultSkin);
sk.setSlotsToSetupPose();
const st = new spine.AnimationState(new spine.AnimationStateData(data));
st.setAnimation(0, 'idle', true);
st.update(1.2); st.apply(sk);
applySlotOverrides(sk, base);
sk.updateWorldTransform();

const targets = sk.drawOrder.filter(s => /head|nose|red|eyeskin/.test(s.data.name) && s.getAttachment());
const saved = sk.drawOrder.map(s => s.getAttachment());
for (let i = 0; i < sk.drawOrder.length; i++) {
  const t = sk.drawOrder[i];
  const att = saved[i];
  if (!targets.includes(t) || !att || !att.computeWorldVertices) continue;
  const verts = new Array(att.worldVerticesLength || 8192).fill(0);
  att.computeWorldVertices(t, 0, att.worldVerticesLength, verts, 0, 2);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < att.worldVerticesLength; i += 2) {
    minX = Math.min(minX, verts[i]); maxX = Math.max(maxX, verts[i]);
    minY = Math.min(minY, verts[i + 1]); maxY = Math.max(maxY, verts[i + 1]);
  }
  const w = maxX - minX, h = maxY - minY;
  if (w <= 0 || h <= 0) continue;
  const size = 512;
  const scale = (size - 40) / Math.max(w, h);
  const canvas = createCanvas(size, size);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffe4e1';
  ctx.fillRect(0, 0, size, size);
  for (let j = 0; j < sk.drawOrder.length; j++) sk.drawOrder[j].setAttachment(j === i ? saved[j] : null);
  sk.updateWorldTransform();
  const renderer = new SeamFreeRenderer(ctx);
  ctx.save();
  ctx.translate(size / 2 - (minX + w / 2) * scale, size / 2 + (minY + h / 2) * scale);
  ctx.scale(scale, -scale);
  renderer.draw(sk);
  ctx.restore();
  fs.writeFileSync(path.join(OUT, `solo_${base}_${t.data.name.replace(/\//g, '_')}.png`), canvas.toBuffer('image/png'));
}
for (let i = 0; i < sk.drawOrder.length; i++) sk.drawOrder[i].setAttachment(saved[i]);
console.log('rendered', targets.map(t => t.data.name).join(', '));