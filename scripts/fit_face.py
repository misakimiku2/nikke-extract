"""Fit the character layer to the game screenshot by matching her face.

    python scripts/fit_face.py

Colour thresholds were too blunt (the tan balloon reads as skin, the pale sky
reads as hair).  A face patch is unique enough that plain normalised
cross-correlation nails the transform: crop a square around her face in the
sprite, sweep scales, take the best match in the screenshot.

The returned scale/offset applies to the whole char_2 layer (balloon + Sky).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "_update_check" / "skyontherock_ui"
SHOT = Path(r"C:\Users\Miku\.workbuddy\clipboard-images\clipboard-2026-11-19T11-20-53-416Z-4a6252f6.jpg")
OUT = BASE / "_update_check" / "_layers_prev"

# face centre in sprite pixels (1024 canvas) and the half-size of the patch
FACE = (486, 352)
HALF = 92


def main() -> None:
    shot = cv2.imread(str(SHOT))
    img = cv2.imread(str(SRC / "skyontherock_opening_char_2.png"), cv2.IMREAD_UNCHANGED)
    cx, cy = FACE
    patch = img[cy - HALF : cy + HALF, cx - HALF : cx + HALF, :3]
    cv2.imwrite(str(OUT / "_face_patch.png"), patch)

    best = None
    for s in np.arange(1.2, 2.6, 0.02):
        w = int(round(patch.shape[1] * s))
        if w >= shot.shape[1]:
            continue
        p = cv2.resize(patch, (w, w), interpolation=cv2.INTER_CUBIC)
        res = cv2.matchTemplate(shot, p, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if best is None or mx > best[0]:
            best = (mx, s, loc)
    mx, s, (x, y) = best
    print(f"face match score={mx:.4f} scale={s:.2f} box=({x},{y}) size={int(patch.shape[1]*s)}")

    # sprite-space face centre -> screenshot space
    fx = x + HALF * s
    fy = y + HALF * s
    print(f"face centre on screen: ({fx:.1f},{fy:.1f})   sprite face centre: ({cx},{cy})")
    ox = fx - cx * s
    oy = fy - cy * s
    print(f"layer placement: scale={s:.3f} x={ox:.1f} y={oy:.1f} size={1024*s:.0f}")

    # overlay proof
    lay = cv2.resize(img[:, :, :3], None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    a = cv2.resize(img[:, :, 3], None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    h, w = lay.shape[:2]
    canvas = shot.astype(np.float32).copy()
    x0, y0 = int(round(ox)), int(round(oy))
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    dw, dh = min(w - sx0, canvas.shape[1] - dx0), min(h - sy0, canvas.shape[0] - dy0)
    if dw > 0 and dh > 0:
        sub = lay[sy0 : sy0 + dh, sx0 : sx0 + dw].astype(np.float32)
        al = a[sy0 : sy0 + dh, sx0 : sx0 + dw][:, :, None]
        canvas[dy0 : dy0 + dh, dx0 : dx0 + dw] = canvas[dy0 : dy0 + dh, dx0 : dx0 + dw] * (1 - al) + sub * al
    blend = (shot.astype(np.float32) * 0.45 + canvas * 0.55).astype(np.uint8)
    cv2.imwrite(str(OUT / "_char_overlay.png"), canvas.astype(np.uint8))
    cv2.imwrite(str(OUT / "_char_blend.png"), blend)


if __name__ == "__main__":
    main()
