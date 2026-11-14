import fs from 'fs';
import path from 'path';
import { loadImage } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';

const dir = process.argv[2], base = process.argv[3];
const atlasText = fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8');
const pageName = atlasText.split(/\r?\n/).map(s => s.trim()).find(s => s && !s.includes(':')) || (base + '.png');
const atlas = new spine.TextureAtlas(atlasText);
const img = await loadImage(path.join(dir, pageName));
for (const page of atlas.pages) {
  page.setTexture(new spine.CanvasTexture(img));
  page.width = img.width; page.height = img.height;
}
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
  .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));

const bm = {}; let tinted = 0;
for (const s of data.slots) { const m = s.blendMode ?? 0; bm[m] = (bm[m] || 0) + 1; }
for (const s of data.slots) {
  const c = s.color;
  if (c && (Math.abs(c.r-1)>.01 || Math.abs(c.g-1)>.01 || Math.abs(c.b-1)>.01)) tinted++;
}
console.log('slot 总数:', data.slots.length);
console.log('blendMode 分布 (0=Normal 1=Add 2=Multiply 3=Screen):', bm);
console.log('带非白 tint 的 slot:', tinted);
let n = 0;
for (const s of data.slots) {
  const c = s.color;
  if (c && (Math.abs(c.r-1)>.01 || Math.abs(c.g-1)>.01 || Math.abs(c.b-1)>.01 || Math.abs(c.a-1)>.01)) {
    console.log(`  ${s.name}: rgb=(${c.r.toFixed(2)},${c.g.toFixed(2)},${c.b.toFixed(2)}) a=${c.a.toFixed(2)} blend=${s.blendMode ?? 0}`);
    if (++n >= 10) break;
  }
}
