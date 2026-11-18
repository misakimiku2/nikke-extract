// 双轨叠加渲染：主段(角色) + 副段(背景/特效)，验证分层动画合成
import fs from 'fs';
import { createCanvas } from '@napi-rs/canvas';
import * as spine from '@esotericsoftware/spine-canvas';
import { SeamFreeRenderer, prepareAtlasTextures } from './spine-seamfix.mjs';
const [dir, base, animMain, animBg, timeStr, outFile] = process.argv.slice(2);
const time = parseFloat(timeStr);
const atlas = new spine.TextureAtlas(fs.readFileSync(dir+'/'+base+'.atlas','utf8'));
await prepareAtlasTextures(atlas, dir);
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas)).readSkeletonData(new Uint8Array(fs.readFileSync(dir+'/'+base+'.skel')));
const skeleton = new spine.Skeleton(data);
if (data.defaultSkin) skeleton.setSkin(data.defaultSkin);
skeleton.setSlotsToSetupPose();
const state = new spine.AnimationState(new spine.AnimationStateData(data));
state.setAnimation(0, animMain, true);
state.setAnimation(1, animBg, true);
state.getCurrent(0).trackTime = time;
state.getCurrent(1).trackTime = time;
state.update(0); state.apply(skeleton); skeleton.updateWorldTransform();
let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
const verts=new Array(4096).fill(0);
for (const slot of skeleton.drawOrder) {
  const att=slot.getAttachment(); if(!att||!att.computeWorldVertices) continue;
  let n=0;
  try {
    if(att instanceof spine.MeshAttachment){n=att.worldVerticesLength;att.computeWorldVertices(slot,0,n,verts,0,2);}
    else if(att instanceof spine.RegionAttachment){n=8;att.computeWorldVertices(slot,verts,0,2);}
    else continue;
    for(let i=0;i<n;i+=2){const x=verts[i],y=verts[i+1];if(!Number.isFinite(x)||!Number.isFinite(y))continue;
      if(x<minX)minX=x;if(x>maxX)maxX=x;if(y<minY)minY=y;if(y>maxY)maxY=y;}
  }catch(e){}
}
const W=800,H=800, bw=Math.max(1,maxX-minX),bh=Math.max(1,maxY-minY);
const scale=Math.min(W/bw,H/bh)*0.96;
const ox=(W-bw*scale)/2-minX*scale, oy=(H+bh*scale)/2+minY*scale;
const canvas=createCanvas(W,H),ctx=canvas.getContext('2d');
ctx.fillStyle='#eee';ctx.fillRect(0,0,W,H);
ctx.save();ctx.translate(ox,oy);ctx.scale(scale,-scale);
const renderer=new SeamFreeRenderer(ctx);renderer.padWorld=0.75/scale;renderer.draw(skeleton);
ctx.restore();
fs.writeFileSync(outFile,canvas.toBuffer('image/png'));
console.log(JSON.stringify({animMain,animBg,time,box:[minX,minY,maxX,maxY].map(v=>Math.round(v)),out:outFile}));
