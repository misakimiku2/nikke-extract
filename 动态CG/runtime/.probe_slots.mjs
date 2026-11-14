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
console.log('全部 slot 名:');
console.log(data.slots.map(s => s.name).join(', '));
