// 列出 skillcut 模型的动画名与时长（骨架是二进制 .skel，只能用 spine-canvas 读）。
// 用法：node probe_skillcut_info.mjs <dir> <base>   ->  stdout 一行 JSON
// 与 probe_skillcut_render.mjs 同一套加载方式；供 nikke-web/build/rerender_skillcut.py 消费。
import fs from 'fs';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures, applySlotOverrides } from './spine-seamfix.mjs';

const dir = process.argv[2];
const base = process.argv[3];

const atlas = new spine.TextureAtlas(fs.readFileSync(dir + '/' + base + '.atlas', 'utf8'));
await prepareAtlasTextures(atlas, dir);

const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
    .readSkeletonData(new Uint8Array(fs.readFileSync(dir + '/' + base + '.skel')));
const skeleton = new spine.Skeleton(data);
if (data.defaultSkin) skeleton.setSkin(data.defaultSkin);
skeleton.setSlotsToSetupPose();

// 应用渲染覆盖（与网页实时模型同一份 spine_overrides.json），让包围盒探测也排除装饰层
applySlotOverrides(skeleton, base);

const anims = data.animations.map((a) => ({ name: a.name, duration: +a.duration.toFixed(4) }));
console.log(JSON.stringify({ base, width: data.width, height: data.height, anims }));
void SeamFreeRenderer;
