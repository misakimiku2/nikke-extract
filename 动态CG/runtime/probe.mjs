import fs from 'fs';
import * as spine from '@esotericsoftware/spine-core';

const dir = '../样本/absolute_01';
const atlasText = fs.readFileSync(`${dir}/EventScene_absolute_01.atlas`, 'utf8');
const atlas = new spine.TextureAtlas(atlasText);
console.log('atlas pages:', atlas.pages.length, 'regions:', atlas.regions.length);

const skelBytes = fs.readFileSync(`${dir}/EventScene_absolute_01.skel`);
for (const page of atlas.pages) {
  page.texture = { getImage: () => ({ width: 2048, height: 2048 }) };
}
const binary = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas));
const data = binary.readSkeletonData(new Uint8Array(skelBytes));
console.log('skeleton name:', data.name);
console.log('version:', data.version);
console.log('width x height:', data.width, data.height);
console.log('bones:', data.bones.length, 'slots:', data.slots.length);
console.log('skins:', data.skins.length, 'animations:', data.animations.length);
for (const a of data.animations) console.log('  anim:', a.name, 'duration:', a.duration?.toFixed(3));
console.log('events:', data.events.length, 'ik:', data.ikConstraints.length, 'transform:', data.transformConstraints.length, 'path:', data.pathConstraints.length);
