"""Compose SKY ON THE ROCK key art from the extracted UI layers.

    python scripts/compose_skyontherock.py

Layers come from the event UI bundle (see probe_bundle.py --id 15257):
  opening_bg     sky + clouds
  opening_char_2 balloon + Sky (key art)
  opening_char   basket rim + Shifty
  opening_eff    rainbow flare
  main_title_txt logo
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "_update_check" / "skyontherock_ui"
OUT = BASE / "_update_check" / "cover"
W, H = 1080, 1920


def load(name: str) -> Image.Image:
    return Image.open(SRC / f"{name}.png").convert("RGBA")


def fit(img: Image.Image, w: int | None = None, h: int | None = None) -> Image.Image:
    if w:
        r = w / img.width
    else:
        r = h / img.height
    return img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (W, H), (176, 214, 226, 255))

    # --- sky: crop the pale top band, then cover-crop
    bg = load("skyontherock_opening_bg")
    bg = bg.crop((0, 46, bg.width, bg.height))
    bg = bg.resize((round(H * 1.12 * bg.width / bg.height), round(H * 1.12)), Image.LANCZOS)
    canvas.alpha_composite(bg, ((W - bg.width) // 2, -60))

    # --- balloon + Sky
    char2 = load("skyontherock_opening_char_2")
    s = 1.45
    char2 = char2.resize((round(char2.width * s), round(char2.height * s)), Image.LANCZOS)
    canvas.alpha_composite(char2, (-109, 26))

    # --- rainbow flare in front of the balloon, top right
    eff = load("skyontherock_opening_eff")
    eff = eff.resize((1400, 1400), Image.LANCZOS).rotate(-10, expand=True, resample=Image.BICUBIC)
    canvas.alpha_composite(eff, (60, -120))

    # --- basket rim at the bottom, only the top edge shows
    char = load("skyontherock_opening_char")
    char = char.resize((1536, 1536), Image.LANCZOS)
    canvas.alpha_composite(char, (-228, 482))

    # --- logo
    logo = load("skyontherock_main_title_txt")
    logo = logo.resize((700, round(700 * logo.height / logo.width)), Image.LANCZOS)
    canvas.alpha_composite(logo, ((W - logo.width) // 2 - 6, 982))

    # --- halftone dots, bottom corners
    hal = load("skyontherock_main_deco_halftone")
    hal = hal.resize((420, 420), Image.LANCZOS)
    canvas.alpha_composite(hal, (-80, 1480))

    out = OUT / "skyontherock_full.png"
    canvas = canvas.crop((0, 40, W, H)).resize((W, H), Image.LANCZOS)
    canvas.convert("RGB").save(out, quality=95)
    print("saved", out, canvas.size)

    # 3:4 card crop, keep face + logo + basket rim
    ch = round(W * 4 / 3)
    top = min(max(0, 300), H - ch)
    card = canvas.crop((0, top, W, top + ch)).convert("RGB")
    card.save(OUT / "skyontherock_card.png", quality=95)
    print("saved card", card.size)

    # downscale previews
    canvas.convert("RGB").resize((540, 960), Image.LANCZOS).save(OUT / "preview.png")


if __name__ == "__main__":
    main()
