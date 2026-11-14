/** Dump animation metadata for every exported Spine model. */
import fs from 'fs';
import path from 'path';
import * as spine from '@esotericsoftware/spine-core';

const root = process.argv[2] || '../模型';
const out = [];
const dirs = fs.readdirSync(root).filter(d => fs.statSync(path.join(root, d)).isDirectory());

for (const d of dirs) {
    const dir = path.join(root, d);
    const atlasFile = fs.readdirSync(dir).find(f => f.endsWith('.atlas'));
    const skelFile = fs.readdirSync(dir).find(f => f.endsWith('.skel'));
    if (!atlasFile || !skelFile) continue;
    try {
        const atlas = new spine.TextureAtlas(fs.readFileSync(path.join(dir, atlasFile), 'utf8'));
        for (const page of atlas.pages) page.texture = { getImage: () => ({ width: 1, height: 1 }) };
        const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
            .readSkeletonData(new Uint8Array(fs.readFileSync(path.join(dir, skelFile))));
        out.push({
            name: d,
            version: data.version,
            bones: data.bones.length,
            slots: data.slots.length,
            regions: atlas.regions.length,
            anims: data.animations.map(a => ({ name: a.name, duration: +a.duration.toFixed(3) })),
        });
    } catch (e) {
        out.push({ name: d, error: String(e).slice(0, 120) });
    }
}
console.log(JSON.stringify(out, null, 0));
