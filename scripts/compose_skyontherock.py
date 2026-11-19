"""Compose SKY ON THE ROCK key art from the extracted UI layers.

    python scripts/compose_skyontherock.py

Layers come from the event UI bundle (see probe_bundle.py --id 15257):
  opening_bg     sky + clouds
  opening_char_2 balloon + Sky (key art)
  opening_char   basket rim + Shifty
  opening_eff    prism + rainbow
  main_title_txt logo

Placement is measured, not guessed.  fit_face.py matched Sky's face against a
screenshot of the running event lobby and got scale 1.50 at (-273,-113) with a
0.975 correlation; dragging the basket layer onto the screenshot with that same
transform lines up the rim, the weave and Shifty with no double image, so both
art layers share it.

  screenshot  985x1343, of which the client area is 985x1313 (30px title bar)
  canvas      1080x1440 -- the game renders 3:4, which is also the card ratio

Everything below is in poster pixels.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "_update_check" / "skyontherock_ui"
OUT = BASE / "_update_check" / "cover"

W, H = 1080, 1440
K = W / 985.0            # screenshot px -> poster px
TITLE = 30               # window title bar height

# art layers (char_2 + basket), measured in screenshot space
ART_S, ART_X, ART_Y = 1.50, -273.0, -113.0

# logo: ink box measured on the reference, sprite ink starts at (11,15)
LOGO_INK = (300.0, 830.0, 320.0)   # x, y, ink width
LOGO_INK_W = 488.0                 # ink width inside the 512-wide sprite
LOGO_INK_X, LOGO_INK_Y = 11.0, 15.0


def load(name: str) -> Image.Image:
    return Image.open(SRC / f"{name}.png").convert("RGBA")


def scale(img: Image.Image, s: float) -> Image.Image:
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def screen_blend(base: Image.Image, top: Image.Image, x: int, y: int, strength: float = 1.0) -> Image.Image:
    """Screen-blend top onto base at (x, y), top's alpha acting as the mix mask."""
    bw, bh = base.size
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(bw, x + top.width), min(bh, y + top.height)
    if x2 <= x1 or y2 <= y1:
        return base
    sx, sy = x1 - x, y1 - y
    sub = top.crop((sx, sy, sx + (x2 - x1), sy + (y2 - y1)))
    b = np.asarray(base.crop((x1, y1, x2, y2)).convert("RGB")).astype(np.float32)
    t = np.asarray(sub.convert("RGB")).astype(np.float32)
    a = np.asarray(sub.getchannel("A")).astype(np.float32)[:, :, None] / 255.0 * strength
    scr = 255.0 - (255.0 - b) * (255.0 - t) / 255.0
    base.paste(Image.fromarray((b * (1 - a) + scr * a).clip(0, 255).astype("uint8")), (x1, y1))
    return base


def cloud_front(base: Image.Image, sky: Image.Image, p1: tuple[float, float], p2: tuple[float, float],
                feather: float, origin: tuple[int, int]) -> Image.Image:
    """Paste a copy of the sky back over everything, masked to one side of p1-p2.

    The game hides the basket's near edge behind a cloud.  Rather than cut a
    cloud out of the sky texture (it has no alpha of its own), reuse the whole
    sky layer and fade it in along the diagonal the reference shows.
    """
    ox, oy = origin
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = (p2[1] - p1[1]), -(p2[0] - p1[0])          # normal, points bottom-left
    d = (xx - p1[0]) * nx + (yy - p1[1]) * ny
    d /= float(np.hypot(nx, ny))
    mask = Image.fromarray((d / feather * 255).clip(0, 255).astype("uint8"))
    # the sky is bigger than the canvas, so align it to the canvas before pasting
    aligned = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    aligned.paste(sky, (ox, oy))
    base.paste(aligned, (0, 0), mask)
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (W, H), (168, 210, 224, 255))

    # --- sky: cover-fill, nudged so the clouds sit like the reference
    sky = load("skyontherock_opening_bg")
    sky = scale(sky, max(W / sky.width, H / sky.height) * 1.06)
    sky_xy = ((W - sky.width) // 2, (H - sky.height) // 2)
    canvas.alpha_composite(sky, sky_xy)

    art_s = ART_S * K
    art_x = ART_X * K
    art_y = (ART_Y - TITLE) * K

    char2 = scale(load("skyontherock_opening_char_2"), art_s)
    canvas.alpha_composite(char2, (round(art_x), round(art_y)))

    basket = scale(load("skyontherock_opening_char"), art_s)
    canvas.alpha_composite(basket, (round(art_x), round(art_y)))

    # --- foreground cloud, bottom left: the basket's near edge is behind it
    canvas = cloud_front(canvas, sky.copy(), (330.0, 1440.0), (150.0, 980.0), 130.0, sky_xy)

    # --- prism + rainbow, upper right.  The eff sprite is mostly a soft vignette;
    # only its 250..495 / 10..275 corner holds the arc, and the game blends that
    # additively, so screen-blend the crop instead of alpha-compositing the whole
    # sheet (which would just fog the balloon).
    eff = load("skyontherock_opening_eff").crop((250, 10, 495, 275))
    eff = scale(eff, 2.2)
    canvas = screen_blend(canvas, eff, 400, -60, 0.95)

    # --- logo
    ls = LOGO_INK[2] / LOGO_INK_W
    logo = scale(load("skyontherock_main_title_txt"), ls)
    canvas.alpha_composite(logo, (round(LOGO_INK[0] - LOGO_INK_X * ls), round(LOGO_INK[1] - LOGO_INK_Y * ls)))

    # --- halftone dots, bottom left
    hal = scale(load("skyontherock_main_deco_halftone"), 1.1)
    canvas.alpha_composite(hal, (-110, H - 380))

    out = OUT / "skyontherock_full.png"
    canvas.convert("RGB").save(out, quality=95)
    print("saved", out, canvas.size)

    # the card is the same 3:4 ratio, so no crop is needed
    canvas.convert("RGB").save(OUT / "skyontherock_card.png", quality=95)
    canvas.convert("RGB").resize((540, 720), Image.LANCZOS).save(OUT / "preview.png")


if __name__ == "__main__":
    main()
