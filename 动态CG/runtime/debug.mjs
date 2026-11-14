import fs from 'fs';
import { loadImage } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';

const dir = '../样本/absolute_01';
const base = 'EventScene_absolute_01';
const atlasPath = dir + '/' + base + '.atlas';
const pngPath = dir + '/' + base + '.png';
const skelPath = dir + '/' + base + '.skel';

const atlas = new spine.TextureAtlas(fs.readFileSync(atlasPath, 'utf8'));
const img = await loadImage(pngPath);
console.log('image', img.width, img.height, typeof img);
for (const p of atlas.pages) {
    p.texture = new spine.CanvasTexture(img);
    p.width = img.width;
    p.height = img.height;
}
console.log('page texture image?', !!atlas.pages[0].texture.getImage());
const r0 = atlas.regions[0];
console.log('region0', r0.name, r0.u, r0.v, r0.width, r0.height, 'page?', !!r0.page);

const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(skelPath)));
console.log('skins', data.skins.map(s => s.name), 'defaultSkin?', !!data.defaultSkin);
const sk = new spine.Skeleton(data);
console.log('skin after ctor', sk.skin && sk.skin.name);
if (data.defaultSkin) sk.setSkin(data.defaultSkin);
sk.setSlotsToSetupPose();
let withAtt = 0;
const sample = [];
for (const s of sk.slots) {
    const a = s.getAttachment();
    if (a) {
        withAtt++;
        if (sample.length < 5) sample.push([s.data.name, a.constructor.name]);
    }
}
console.log('slots with attachment', withAtt, '/', sk.slots.length, sample);
const a = sk.slots.find(s => s.getAttachment()).getAttachment();
console.log('sample attachment', a.constructor.name, 'region?', !!a.region,
    'u/v', a.u, a.v, 'renderObject?', !!a.region.renderObject,
    'page?', !!a.region.page, 'texture?', !!a.region.page.texture);
