import fs from 'fs';
import path from 'path';
import { loadImage } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';

const dir = process.argv[2], base = process.argv[3];
const atlasText = fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8');
const pageName = atlasText.split(/\r?\n/).map(s => s.trim()).find(s => s && !s.includes(':')) || (base + '.png');
const atlas = new spine.TextureAtlas(atlasText);
const img = await loadImage(path.join(dir, pageName));
for (const page of atlas.pages) { page.setTexture(new spine.CanvasTexture(img)); page.width = img.width; page.height = img.height; }
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
st.update(1.2); st.apply(sk);

let nonWhite = 0, semiAlpha = 0;
const list = [];
for (const s of sk.slots) {
  const c = s.color;
  const isW = Math.abs(c.r-1)<.01 && Math.abs(c.g-1)<.01 && Math.abs(c.b-1)<.01;
  if (!isW) { nonWhite++; if (list.length<14) list.push(`  ${s.data.name}: rgb=(${c.r.toFixed(2)},${c.g.toFixed(2)},${c.b.toFixed(2)}) a=${c.a.toFixed(2)}`); }
  if (Math.abs(c.a-1)>.01) semiAlpha++;
}
console.log('动画 1.2s 后：');
console.log('  slot 总数', sk.slots.length);
console.log('  非白 tint', nonWhite);
console.log('  非满 alpha', semiAlpha);
list.forEach(l=>console.log(l));
