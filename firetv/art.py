"""Make the Fire TV app's launcher icon and banner from the BAMS logo (branding/logo). Run again after the logo changes:

    python firetv/art.py        (needs Pillow)

Writes app/src/main/res/mipmap-*/ic_launcher.png (square) and drawable-*/banner.png (16:9, with the wordmark):
Fire TV and Android TV launchers show the banner, settings and app lists the icon.
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
LOGO = HERE.parent / "branding" / "logo"
RES = HERE / "app" / "src" / "main" / "res"
BG = (15, 18, 22, 255)  # the TV app's --bg


def fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """`img` scaled to fit inside w x h, keeping its shape."""
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def on_bg(img: Image.Image, w: int, h: int, box: float) -> Image.Image:
    """`img` centred on the background, filling `box` of the canvas."""
    canvas = Image.new("RGBA", (w, h), BG)
    art = fit(img, round(w * box), round(h * box))
    canvas.alpha_composite(art, ((w - art.width) // 2, (h - art.height) // 2))
    return canvas.convert("RGB")


def main() -> None:
    icon = Image.open(LOGO / "bams-icon-transparent.png").convert("RGBA")
    word = Image.open(LOGO / "bams-wordmark-transparent.png").convert("RGBA")
    for density, size in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        out = RES / f"mipmap-{density}" / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        on_bg(icon, size, size, 0.78).save(out, optimize=True)
    for density, (w, h) in {"xhdpi": (320, 180), "xxxhdpi": (640, 360)}.items():
        out = RES / f"drawable-{density}" / "banner.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        on_bg(word, w, h, 0.82).save(out, optimize=True)
    print("written under", RES)


if __name__ == "__main__":
    main()
