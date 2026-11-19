"""Export the SKY ON THE ROCK key-art layers as web-ready webp for the site.

    python scripts/export_skyontherock_layers.py

Writes into E:/test/nikke-web/public/event/skyontherock/, plus prints the CSS
block that positions every layer on the stage.  The stage is 3:4 (1080x1440) to
match the poster and the game's own canvas; positions come straight from
compose_skyontherock.py, so the animated hero and the flat poster line up.
"""
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "_update_check" / "skyontherock_ui"
WEB = Path(r"E:\test\nikke-web\public\event\skyontherock")

W, H = 1080, 1440
STAGE_CSS_W = 300       # the hero column is 300px wide; export at 2x for retina
K = STAGE_CSS_W * 2 / W

# slug -> (source image, on-stage left, top, width, quality)
LAYERS = {}


def add(slug: str, img: Image.Image, x: float, y: float, w: float, q: int = 88) -> None:
    LAYERS[slug] = (img, x, y, w, q)


def main() -> None:
    WEB.mkdir(parents=True, exist_ok=True)

    # sky: cover-fill
    sky = Image.open(SRC / "skyontherock_opening_bg.png").convert("RGBA")
    ss = max(W / sky.width, H / sky.height) * 1.06
    sky = sky.resize((round(sky.width * ss), round(sky.height * ss)), Image.LANCZOS)
    add("sky", sky, (W - sky.width) / 2, (H - sky.height) / 2, sky.width)

    for name, slug in [("skyontherock_opening_char_2", "char"), ("skyontherock_opening_char", "basket")]:
        add(slug, Image.open(SRC / f"{name}.png").convert("RGBA"), -299.3, -156.8, 1684)

    eff = Image.open(SRC / "skyontherock_opening_eff.png").convert("RGBA").crop((250, 10, 495, 275))
    eff = eff.resize((round(eff.width * 2.2), round(eff.height * 2.2)), Image.LANCZOS)
    add("flare", eff, 400, -60, eff.width, 86)

    logo = Image.open(SRC / "skyontherock_main_title_txt.png").convert("RGBA")
    ls = 320 / 488.0
    logo = logo.resize((round(logo.width * ls), round(logo.height * ls)), Image.LANCZOS)
    add("logo", logo, 300 - 11 * ls, 830 - 15 * ls, logo.width, 90)

    hal = Image.open(SRC / "skyontherock_main_deco_halftone.png").convert("RGBA")
    hal = hal.resize((round(hal.width * 1.1), round(hal.height * 1.1)), Image.LANCZOS)
    add("dots", hal, -110, H - 380, hal.width, 80)

    lines = []
    for slug, (img, x, y, w, q) in LAYERS.items():
        out_w = min(round(w * K), 900)
        im = img if out_w >= img.width else img.resize((out_w, round(img.height * out_w / img.width)), Image.LANCZOS)
        dst = WEB / f"{slug}.webp"
        im.save(dst, "WEBP", quality=q, method=6)
        print(f"{slug:<8} {im.size[0]:>4}x{im.size[1]:<4} {dst.stat().st_size / 1024:>4.0f} KB")
        lines.append(
            f".eh-{slug} {{ left: {x / W * 100:.2f}%; top: {y / H * 100:.2f}%; width: {w / W * 100:.2f}%; }}"
        )

    poster = Image.open(BASE / "_update_check" / "cover" / "skyontherock_card.png")
    poster.resize((720, 960), Image.LANCZOS).save(WEB / "poster.webp", "WEBP", quality=84, method=6)
    print("poster   720x960")

    print("\n/* stage 1080x1440 */")
    for ln in lines:
        print(ln)


if __name__ == "__main__":
    main()
