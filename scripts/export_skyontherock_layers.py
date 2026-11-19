"""Export the SKY ON THE ROCK key-art layers as web-ready webp for the site.

    python scripts/export_skyontherock_layers.py

Writes into E:/test/nikke-web/public/event/skyontherock/
"""
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "_update_check" / "skyontherock_ui"
WEB = Path(r"E:\test\nikke-web\public\event\skyontherock")

LAYERS = [
    ("skyontherock_opening_bg", "sky", 768, 82),
    ("skyontherock_opening_char_2", "char", 1024, 90),
    ("skyontherock_opening_char", "basket", 1100, 86),
    ("skyontherock_opening_eff", "flare", 640, 86),
    ("skyontherock_main_title_txt", "logo", 720, 90),
    ("skyontherock_main_deco_halftone", "dots", 220, 80),
]


def main() -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    for name, slug, width, quality in LAYERS:
        src = Image.open(SRC / f"{name}.png").convert("RGBA")
        if src.width != width:
            src = src.resize((width, round(src.height * width / src.width)), Image.LANCZOS)
        dst = WEB / f"{slug}.webp"
        src.save(dst, "WEBP", quality=quality, method=6)
        print(f"{slug:<8} {src.size}  {dst.stat().st_size / 1024:.0f} KB")

    # flat poster (3:4) as the no-animation fallback
    poster = Image.open(BASE / "_update_check" / "cover" / "skyontherock_card.png")
    poster = poster.resize((720, 960), Image.LANCZOS)
    out = WEB / "poster.webp"
    poster.save(out, "WEBP", quality=84, method=6)
    print(f"poster   720x960  {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
