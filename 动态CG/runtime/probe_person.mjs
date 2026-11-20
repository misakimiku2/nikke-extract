/**
 * Sample visible-content bounds over the skillcut animation.
 * Usage: node probe_person.mjs <dir> <base>
 */
import fs from 'fs';
import path from 'path';
import * as spine from '@esotericsoftware/spine-canvas';
import { prepareAtlasTextures } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];
const atlasText = fs.readFileSync(path.join(dir, base + '.atlas'), 'utf8');
const atlas = new spine.TextureAtlas(atlasText);
await prepareAtlasTextures(atlas, dir);
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, base + '.skel'))));
const sk = new spine.Skeleton(data);
if (data.defaultSkin) sk.setSkin(data.defaultSkin);
sk.setSlotsToSetupPose();
const anim = data.animations.find(a => /^skillcut/i.test(a.name)) || data.animations[0];
const st = new spine.AnimationState(new spine.AnimationStateData(data));
const track = st.setAnimation(0, anim.name, false);

const bounds = (skeleton) => {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const slot of skeleton.slots) {
        if (!slot.bone.active || slot.attachment == null) continue;
        const vb = slot.getAttachmentVertices();
        if (!vb || vb.length < 4) continue;
        // world coords of quad/vertices
        for (let i = 0; i + 1 < vb.length; i += 2) {
            const wx = vb[i], wy = vb[i + 1];
            // apply slot world transform roughly: attachment vertices are already world? use skeleton bounds API instead
        }
        break;
    }
    return null;
};

// use spine's own getBounds per time sample
const offset = new spine.Vector2();
const size = new spine.Vector2();
console.log('t  width  height');
for (let i = 0; i <= 20; i++) {
    const t = (i / 20) * anim.duration;
    track.trackTime = t;
    st.update(0);
    st.apply(sk);
    sk.updateWorldTransform();
    sk.getBounds(offset, size, []);
    console.log(`${t.toFixed(2)}  ${size.x.toFixed(0)}  ${size.y.toFixed(0)}  (x=${offset.x.toFixed(0)}, y=${offset.y.toFixed(0)})`);
}
