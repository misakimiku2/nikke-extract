/**
 * Seam-free Canvas2D renderer for Spine 4.1 — with blend mode support.
 *
 * 修了两个问题：
 *
 * 1) 接缝：spine-canvas 用 clip + drawImage 逐个三角形绘制，每个 clip 边缘的抗锯齿
 *    会留下约 1px 的半透明裂缝，300 个三角形的网格看起来像一张线框网。
 *    解决：把三角形绕质心向外扩张 padWorld，让相邻三角形重叠盖住裂缝。
 *
 * 2) 混合模式丢失：上游 SkeletonRenderer.drawTriangles 里有
 *    `if (slot.data.blendMode != blendMode) blendMode = slot.data.blendMode;`
 *    但赋值之后没有对 ctx 做任何设置，等于所有 slot 都按 source-over 画。
 *    Spine 里的 Multiply / Screen 层（面部阴影、腮红、发光）因此变成灰色半透明块。
 *    解决：重写 drawTriangles，把 blendMode 映射到 canvas 的 globalCompositeOperation。
 */
import * as spine from '@esotericsoftware/spine-canvas';
import fs from 'fs';
import path from 'path';
import { createCanvas, loadImage } from '@napi-rs/canvas';

// BlendMode 枚举顺序：0 Normal / 1 Additive / 2 Multiply / 3 Screen
const BLEND_OPS = ['source-over', 'lighter', 'multiply', 'screen'];

/**
 * 按模型渲染覆盖配置（与网页实时模型共用同一份 JSON，单一真源）。
 * 默认读 nikke-web/public/data/spine_overrides.json，可用环境变量覆盖路径。
 * 用来隐藏原素材里观感不佳但游戏里确实存在的装饰切片，而不是去改 atlas/skel。
 */
const OVERRIDES_PATH = process.env.SPINE_OVERRIDES
    || 'E:/test/nikke-web/public/data/spine_overrides.json';
let _overrides = null;
function slotOverrides() {
    if (_overrides) return _overrides;
    try {
        _overrides = JSON.parse(fs.readFileSync(OVERRIDES_PATH, 'utf8')).models || {};
    } catch { _overrides = {}; }
    return _overrides;
}

/**
 * 离线单帧渲染用：把配置里指定的 slot 的 attachment 摘掉。
 * 用 setAttachment(null) 而不是改 color.a —— 包围盒探测循环靠
 * `slot.getAttachment()` 判断某个部件是否参与，摘掉后取景也不会被装饰层撑大。
 * 必须在每次 state.apply 之后调用（动画可能把 attachment 设回来）。
 */
export function applySlotOverrides(skeleton, modelName) {
    const rules = slotOverrides()[modelName]?.hiddenSlots || [];
    if (!rules.length) return 0;
    const exact = new Set(rules.filter(r => !(r.startsWith('/') && r.endsWith('/'))));
    const patterns = rules
        .filter(r => r.startsWith('/') && r.endsWith('/'))
        .map(r => { try { return new RegExp(r.slice(1, -1), 'i'); } catch { return null; } })
        .filter(Boolean);
    let n = 0;
    for (const slot of skeleton.slots) {
        const sn = String(slot.data?.name || '');
        if (exact.has(sn) || patterns.some(r => r.test(sn))) {
            slot.setAttachment(null);
            n++;
        }
    }
    return n;
}

/**
 * 把 pma:true 的图集贴图反预乘成 Canvas2D 能正确合成的「直通 alpha」贴图。
 *
 * 游戏导出的 .atlas 头部写了 pma:true，RGB 已经乘过 alpha（RGB <= A）。
 * Canvas2D 的 drawImage 一律按直通 alpha 处理，会把 RGB 再乘一次 alpha，
 * 于是半透明层被压暗：腮红变灰褐、发光层变灰圆斑、阴影层变灰方块。
 * 之前静态合成图里脸上的一圈圈灰圆点，根因就在这里。
 *
 * 反预乘：C = P * 255 / A。全透明像素直接归零，避免边缘渗色。
 * 返回的是 canvas，可以直接交给 spine.CanvasTexture / ctx.drawImage。
 */
export function unpremultiplyAtlas(img) {
    const cv = createCanvas(img.width, img.height);
    const c = cv.getContext('2d');
    c.drawImage(img, 0, 0);
    const id = c.getImageData(0, 0, img.width, img.height);
    const p = id.data;
    for (let i = 0; i < p.length; i += 4) {
        const a = p[i + 3];
        if (a === 0) { p[i] = p[i + 1] = p[i + 2] = 0; continue; }
        if (a === 255) continue;
        p[i]     = Math.min(255, Math.round(p[i]     * 255 / a));
        p[i + 1] = Math.min(255, Math.round(p[i + 1] * 255 / a));
        p[i + 2] = Math.min(255, Math.round(p[i + 2] * 255 / a));
    }
    c.putImageData(id, 0, 0);
    return cv;
}

/**
 * 逐页加载图集贴图。有些模型是双页 atlas（第二页通常是背景小图），
 * 老脚本把所有 page 都指向第一张贴图，背景会画成错的内容。
 */
export async function prepareAtlasTextures(atlas, dir) {
    for (const page of atlas.pages) {
        const img = unpremultiplyAtlas(await loadImage(path.join(dir, page.name)));
        page.setTexture(new spine.CanvasTexture(img));
        page.width = img.width;
        page.height = img.height;
    }
}

export class SeamFreeRenderer extends spine.SkeletonRenderer {
    triangleRendering = true;
    /** dilation in skeleton/world units (set to padPixels / scale) */
    padWorld = 0.6;

    drawTriangles(skeleton) {
        const ctx = this.ctx;
        const skelColor = skeleton.color;
        const order = skeleton.drawOrder;
        const color = this.tempColor;
        let currentBlend = -1;

        for (let i = 0; i < order.length; i++) {
            const slot = order[i];
            const att = slot.getAttachment();
            let vertices, triangles, texture;

            if (att instanceof spine.RegionAttachment) {
                vertices = this.computeRegionVertices(slot, att, false);
                triangles = spine.SkeletonRenderer.QUAD_TRIANGLES;
                texture = att.region.texture.getImage();
            } else if (att instanceof spine.MeshAttachment) {
                vertices = this.computeMeshVertices(slot, att, false);
                triangles = att.triangles;
                texture = att.region.texture.getImage();
            } else {
                continue;
            }
            if (!texture) continue;

            // *_shadow 层是半透明灰贴图，Unity 里由专用 shader 处理；
            // canvas 按 Normal 画就成了灰块。用 multiply 压暗底层才是它本来的作用。
            // SHADOW_MODE=skip 可改为直接跳过，=normal 恢复旧行为
            const isShadow = /_shadow$/i.test(slot.data.name);
            const shadowMode = process.env.SHADOW_MODE || 'skip';
            if (isShadow && shadowMode === 'skip') continue;

            const bm = isShadow && shadowMode === 'multiply' ? 2 : (slot.data.blendMode ?? 0);
            if (bm !== currentBlend) {
                currentBlend = bm;
                ctx.globalCompositeOperation = BLEND_OPS[bm] || 'source-over';
            }

            const sc = slot.color;
            const ac = att.color;
            color.set(
                skelColor.r * sc.r * ac.r,
                skelColor.g * sc.g * ac.g,
                skelColor.b * sc.b * ac.b,
                skelColor.a * sc.a * ac.a
            );
            ctx.globalAlpha = color.a;

            for (let j = 0; j < triangles.length; j += 3) {
                const t1 = triangles[j] * 8;
                const t2 = triangles[j + 1] * 8;
                const t3 = triangles[j + 2] * 8;
                this.drawTriangle(
                    texture,
                    vertices[t1], vertices[t1 + 1], vertices[t1 + 6], vertices[t1 + 7],
                    vertices[t2], vertices[t2 + 1], vertices[t2 + 6], vertices[t2 + 7],
                    vertices[t3], vertices[t3 + 1], vertices[t3 + 6], vertices[t3 + 7]
                );
            }
        }

        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
    }

    drawTriangle(img, x0, y0, u0, v0, x1, y1, u1, v1, x2, y2, u2, v2) {
        const ctx = this.ctx;
        const pad = this.padWorld;

        if (pad > 0) {
            const cx = (x0 + x1 + x2) / 3;
            const cy = (y0 + y1 + y2) / 3;
            const grow = (x, y) => {
                const dx = x - cx, dy = y - cy;
                const len = Math.hypot(dx, dy);
                if (len < 1e-6) return [x, y];
                const k = (len + pad) / len;
                return [cx + dx * k, cy + dy * k];
            };
            [x0, y0] = grow(x0, y0);
            [x1, y1] = grow(x1, y1);
            [x2, y2] = grow(x2, y2);
        }

        u0 *= img.width;
        v0 *= img.height;
        u1 *= img.width;
        v1 *= img.height;
        u2 *= img.width;
        v2 *= img.height;

        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.closePath();

        x1 -= x0; y1 -= y0;
        x2 -= x0; y2 -= y0;
        u1 -= u0; v1 -= v0;
        u2 -= u0; v2 -= v0;

        const det = 1 / (u1 * v2 - u2 * v1);
        const a = (v2 * x1 - v1 * x2) * det;
        const b = (v2 * y1 - v1 * y2) * det;
        const c = (u1 * x2 - u2 * x1) * det;
        const d = (u1 * y2 - u2 * y1) * det;
        const e = x0 - a * u0 - c * v0;
        const f = y0 - b * u0 - d * v0;

        ctx.save();
        // 图集里各部件零间隙紧贴，双线性插值会在 mesh 边界采到隔壁图块的像素
        // （脸上那些灰色圆斑就是邻块渗色）。关掉平滑采样，靠超采样消锯齿。
        ctx.imageSmoothingEnabled = false;
        ctx.transform(a, b, c, d, e, f);
        ctx.clip();
        ctx.drawImage(img, 0, 0);
        ctx.restore();
    }
}

export function createRenderer(ctx, pixelsPerUnit, padPixels = 0.6) {
    const r = new SeamFreeRenderer(ctx);
    r.padWorld = padPixels / Math.max(pixelsPerUnit, 1e-6);
    return r;
}
