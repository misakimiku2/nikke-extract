# -*- coding: utf-8 -*-
"""探针：c094 脸部灰边来源（源 PNG vs 构建后 webp，PMA 合法性统计）"""
import os
from PIL import Image

SRC = r"E:/test/nikke_extract/staging/spine_stand"
PUB = r"E:/test/nikke-web/public/spine_char"
OUT = r"E:/test/nikke_extract/staging/_probe_c094"
os.makedirs(OUT, exist_ok=True)

def stats(im, label):
    px = im.load()
    w, h = im.size
    dark = over = semi = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if 0 < a < 255:
                semi += 1
                m = max(r, g, b)
                if m > a: over += 1
                if m * 2 < a: dark += 1
    print(f"{label}: semi={semi} over(RGB>A)={over} dark(RGB<A/2)={dark}")
    return dark

def crop(im, box):
    return im.crop(box)

def show_pma_over_skin(im, path, scale=4):
    """按 PMA 混合叠在肤色上，模拟渲染结果"""
    w, h = im.size
    bg = (255, 228, 225)
    out = Image.new("RGB", (w, h))
    po, pi = out.load(), im.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pi[x, y]
            t = a / 255
            po[x, y] = (int(r + bg[0] * (1 - t)), int(g + bg[1] * (1 - t)), int(b + bg[2] * (1 - t)))
    out = out.resize((w * scale, h * scale), Image.NEAREST)
    out.save(path)

for name in ("c094_00", "c095_00"):
    for f in sorted(os.listdir(os.path.join(SRC, name))):
        if f.endswith(".png"):
            with Image.open(os.path.join(SRC, name, f)) as im:
                print(name, "SRC", f, im.size)
    for f in sorted(os.listdir(os.path.join(PUB, name))):
        if f.endswith(".webp"):
            with Image.open(os.path.join(PUB, name, f)) as im:
                print(name, "PUB", f, im.size)

# c094 第二页 nose（声明坐标 1949,1252,97,87）
with Image.open(os.path.join(PUB, "c094_00", "c094_00_2.webp")) as im:
    b2 = im.convert("RGBA")
with Image.open(os.path.join(SRC, "c094_00", "c094_00_2.png")) as im:
    s2 = im.convert("RGBA")
decl_h, act_h = 1398, s2.size[1]
sy = act_h / decl_h
nose_box = (1949, 1252, 1949 + 97, 1252 + 87)
nose_src_box = (1949, int(1252 * sy), 2046, int(1339 * sy))
stats(crop(b2, nose_box), "c094 PUB p2 nose")
stats(crop(s2, nose_src_box), "c094 SRC p2 nose")
show_pma_over_skin(crop(b2, nose_box), os.path.join(OUT, "c094_pub_nose.png"))
show_pma_over_skin(crop(s2, nose_src_box), os.path.join(OUT, "c094_src_nose.png"))

# c094 第二页 idle_eyeskin_d_l（644,1033,143,119）
box = (644, 1033, 644 + 143, 1033 + 119)
stats(crop(b2, box), "c094 PUB p2 eyeskin_d_l")
show_pma_over_skin(crop(b2, box), os.path.join(OUT, "c094_pub_eyeskin.png"))

# c094 第一页 idle_red_l（889,1143,170,100）
with Image.open(os.path.join(PUB, "c094_00", "c094_00.webp")) as im:
    b1 = im.convert("RGBA")
with Image.open(os.path.join(SRC, "c094_00", "c094_00.png")) as im:
    s1 = im.convert("RGBA")
box = (889, 1143, 889 + 170, 1143 + 100)
stats(crop(b1, box), "c094 PUB p1 idle_red_l")
stats(crop(s1, box), "c094 SRC p1 idle_red_l")
show_pma_over_skin(crop(b1, box), os.path.join(OUT, "c094_pub_red_l.png"))

# c095 nose（356,65,39,56）
with Image.open(os.path.join(PUB, "c095_00", "c095_00.webp")) as im:
    c5 = im.convert("RGBA")
box = (356, 65, 356 + 39, 65 + 56)
stats(crop(c5, box), "c095 PUB nose")
show_pma_over_skin(crop(c5, box), os.path.join(OUT, "c095_pub_nose.png"))

# 整页统计
stats(b2, "c094 PUB p2 whole")
stats(s2, "c094 SRC p2 whole")
stats(b1, "c094 PUB p1 whole")
print("done")