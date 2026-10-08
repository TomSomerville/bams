"""Rework the BAMS logo set through local ComfyUI (Qwen Image 2.1 turbo, edit mode).

Each job feeds one of the supplied logo files to Qwen 2.1 as a reference image
and asks for a crisp, higher-res redraw (and, for the lockups, the new tagline
"Bad Ass Media Server"). Laptop first, like VibeMMO's tools/comfy.py; the
laptop's builds of the same weights are aliased by filename in HOSTS.

    python tools/brand_art/rework.py render --out <dir> [--seeds 3] [--only logo,icon] [--host laptop]
    python tools/brand_art/rework.py finalize <dir> --logo 2 --wordmark-dark 1 --wordmark-light 3 --icon 1

`render` writes <dir>/<job>_<n>.png candidates. `finalize` takes the picked
candidate of each job and writes branding/logo/* and web/public/brand/*:
transparent cut-outs come from the black-background renders (alpha keyed off
black, colour un-premultiplied, so the glow survives).
"""

import argparse
import io
import math
import random
import sys
import time
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "branding" / "logo"
WEB = ROOT / "web" / "public"

HOSTS = {
    "laptop": {"url": "http://192.168.1.2:8188", "models": {
        "qwen3vl_8b_int8_convrot.safetensors": "qwen3vl_8b_w4a8.safetensors",
    }},
    "desktop": {"url": "http://127.0.0.1:8188", "models": {}},
}

TAGLINE = "Bad Ass Media Server"
SHARP = "Render it sharp and crisp at high resolution with clean, smooth vector-like edges."
KEEP = ('Keep the glowing play-button icon with its speed lines and the gradient "BAMS" lettering '
        "(cyan, blue, violet, magenta, orange) exactly as they are.")


def tagline(color: str) -> str:
    return (f'Change the small tagline under the "BAMS" lettering so it reads exactly "{TAGLINE}", '
            f"in the same clean {color} sans-serif font at the same size, centered under \"BAMS\".")


# name -> (reference builder, prompt, resolution). Resolution sets the output
# size: the encoder's latent matches the (resized) first reference.
def ref_logo() -> Image.Image:
    return Image.open(LOGO / "bams-logo-dark.webp").convert("RGB")


def pad(im: Image.Image, bg: tuple, aspect: float, margin: float) -> Image.Image:
    """Centre `im` on a bg canvas of the given aspect with `margin` (fraction) around it."""
    w, h = im.size
    cw, ch = w * (1 + 2 * margin), h * (1 + 2 * margin)
    if cw / ch < aspect:
        cw = ch * aspect
    else:
        ch = cw / aspect
    canvas = Image.new("RGB", (round(cw), round(ch)), bg)
    rgba = im.convert("RGBA")
    canvas.paste(rgba, ((canvas.width - w) // 2, (canvas.height - h) // 2), rgba)
    return canvas


JOBS = {
    "logo": (ref_logo,
             f"Edit this logo. {tagline('light grey')} {KEEP} Keep the dark charcoal background "
             f"with its soft glow. {SHARP}", 1280),
    "wordmark-dark": (lambda: pad(Image.open(LOGO / "bams-wordmark-transparent.png"), (0, 0, 0), 3.0, 0.12),
                      f"Edit this logo. {tagline('light grey')} {KEEP} Place it on a solid pure black "
                      f"background. {SHARP}", 1280),
    "wordmark-light": (lambda: pad(Image.open(LOGO / "bams-wordmark.png"), (255, 255, 255), 3.0, 0.12),
                       f"Edit this logo. {tagline('dark grey')} {KEEP} Place it on a solid pure white "
                       f"background. {SHARP}", 1280),
    "icon": (lambda: pad(Image.open(LOGO / "bams-icon-transparent.png"), (0, 0, 0), 1.0, 0.14),
             "Redraw this play-button logo icon exactly: the same rounded triangle frame, inner play "
             "triangle, speed lines and cyan-blue-violet-magenta-orange gradient, centered on a solid "
             f"pure black background. {SHARP}", 1024),
}

TURBO_NODES = (1.0, 0.9375, 0.875, 0.75, 0.5, 0.25)  # Viggle's 6 student timesteps


def turbo_sigmas(w: int, h: int) -> str:
    """Same schedule as VibeMMO comfy.py turbo_sigmas()."""
    tokens = (h // 16) * (w // 16)
    mu = 0.5 + (0.9 - 0.5) * (tokens - 256) / (8192 - 256)
    e = math.exp(mu)
    return ", ".join(f"{e / (e + (1 / t - 1)):.6f}" for t in TURBO_NODES) + ", 0"


def out_size(ref: Image.Image, resolution: int) -> tuple[int, int]:
    """What TextEncodeQwenImage21 resizes the reference (and so the latent) to."""
    ratio = ref.width / ref.height
    return (max(32, round(math.sqrt(resolution * resolution * ratio) / 32) * 32),
            max(32, round(math.sqrt(resolution * resolution / ratio) / 32) * 32))


def graph(host: dict, image_name: str, prompt: str, resolution: int, seed: int, w: int, h: int) -> dict:
    m = host["models"]
    clip = "qwen3vl_8b_int8_convrot.safetensors"
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "Qwen-Image-2.1-viggle-turbo-v0.3-6step-int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": m.get(clip, clip), "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "20": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt, "negative_prompt": "",
            "resolution": resolution, "images.image_1": ["20", 0]}},
        "6": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["4", 0]}},
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "ManualSigmas", "inputs": {"sigmas": turbo_sigmas(w, h)}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["7", 0], "guider": ["6", 0], "sampler": ["8", 0], "sigmas": ["10", 0], "latent_image": ["4", 2]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": "bams-rework"}},
    }


def pick_host(force: str | None) -> dict:
    for name in [force] if force else list(HOSTS):
        h = HOSTS[name]
        try:
            requests.get(f"{h['url']}/system_stats", timeout=3).raise_for_status()
            return {**h, "name": name}
        except requests.RequestException:
            print(f"[rework] {name} ({h['url']}) not answering")
    sys.exit("[rework] no ComfyUI answering")


def upload(host: dict, im: Image.Image, name: str) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    r = requests.post(f"{host['url']}/upload/image", files={"image": (name, buf.getvalue(), "image/png")},
                      data={"overwrite": "true"}, timeout=60)
    r.raise_for_status()
    j = r.json()
    return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]


def run(host: dict, g: dict) -> bytes:
    r = requests.post(f"{host['url']}/prompt", json={"prompt": g}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"queue rejected (HTTP {r.status_code}):\n{r.text[:1500]}")
    pid = r.json()["prompt_id"]
    while True:
        h = requests.get(f"{host['url']}/history/{pid}", timeout=30).json()
        if pid in h:
            entry = h[pid]
            if entry.get("status", {}).get("status_str") == "error":
                raise RuntimeError(f"run failed: {str(entry['status'])[:1500]}")
            img = next(i for o in entry["outputs"].values() for i in o.get("images", []))
            q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                        "type": img.get("type", "output")})
            return requests.get(f"{host['url']}/view?{q}", timeout=120).content
        time.sleep(1)


def render(args) -> None:
    host = pick_host(args.host)
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = args.only.split(",") if args.only else list(JOBS)
    for job in jobs:
        build, prompt, res = JOBS[job]
        ref = build()
        ref.save(args.out / f"{job}_ref.png")
        name = upload(host, ref, f"bams_{job}_ref.png")
        w, h = out_size(ref, res)
        for n in range(1, args.seeds + 1):
            t = time.time()
            png = run(host, graph(host, name, prompt, res, random.randrange(2**63), w, h))
            (args.out / f"{job}_{n}.png").write_bytes(png)
            print(f"[rework] {host['name']}: {job}_{n}.png {w}x{h} in {time.time() - t:.0f}s")


# --- finalize -----------------------------------------------------------------

def cutout(im: Image.Image, lo: int = 14, hi: int = 70) -> Image.Image:
    """Transparent cut from a render on black: alpha ramps with brightness above
    the background level, and edge colour is un-premultiplied so glows keep
    their hue instead of going grey."""
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    corners = np.concatenate([a[:16, :16], a[:16, -16:], a[-16:, :16], a[-16:, -16:]]).reshape(-1, 3)
    a = np.clip(a - np.median(corners, axis=0), 0, 255)
    alpha = np.clip((a.max(axis=2) - lo) / (hi - lo), 0, 1)
    rgb = np.where(alpha[..., None] > 0, a / np.maximum(alpha[..., None], 1e-3), 0)
    out = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    return trim(Image.fromarray(out, "RGBA"))


def trim(im: Image.Image, pad_px: int = 4) -> Image.Image:
    alpha = np.asarray(im.getchannel("A"))
    ys, xs = np.nonzero(alpha > 8)
    box = (max(0, xs.min() - pad_px), max(0, ys.min() - pad_px),
           min(im.width, xs.max() + 1 + pad_px), min(im.height, ys.max() + 1 + pad_px))
    return im.crop(box)


def trim_on(im: Image.Image, bg: tuple, pad_px: int = 12) -> Image.Image:
    """Crop an opaque render to its content against a flat background colour."""
    a = np.asarray(im.convert("RGB"), dtype=np.int16)
    ys, xs = np.nonzero(np.abs(a - np.array(bg)).max(axis=2) > 24)
    box = (max(0, xs.min() - pad_px), max(0, ys.min() - pad_px),
           min(im.width, xs.max() + 1 + pad_px), min(im.height, ys.max() + 1 + pad_px))
    return im.crop(box)


def on_white(cut: Image.Image, pad_px: int = 10) -> Image.Image:
    bg = Image.new("RGBA", (cut.width + 2 * pad_px, cut.height + 2 * pad_px), (255, 255, 255, 255))
    bg.alpha_composite(cut, (pad_px, pad_px))
    return bg.convert("RGB")


def square(im: Image.Image, size: int) -> Image.Image:
    side = max(im.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(im, ((side - im.width) // 2, (side - im.height) // 2))
    return sq.resize((size, size), Image.LANCZOS)


def finalize(args) -> None:
    d = args.dir
    pick = lambda job, n: Image.open(d / f"{job}_{n}.png").convert("RGB")
    LOGO.mkdir(parents=True, exist_ok=True)

    pick("logo", args.logo).save(LOGO / "bams-logo-dark.webp", quality=92)

    wm_cut = cutout(pick("wordmark-dark", args.wordmark_dark))
    wm_cut.save(LOGO / "bams-wordmark-transparent.png", optimize=True)
    trim_on(pick("wordmark-light", args.wordmark_light), (255, 255, 255)).save(LOGO / "bams-wordmark.png", optimize=True)

    icon_cut = cutout(pick("icon", args.icon))
    icon_cut.save(LOGO / "bams-icon-transparent.png", optimize=True)
    on_white(icon_cut).save(LOGO / "bams-icon.png", optimize=True)

    # The web UI sits on a dark theme, so it gets the cut-outs, at sidebar-friendly widths.
    (WEB / "brand").mkdir(parents=True, exist_ok=True)
    wm_cut.resize((1000, round(1000 * wm_cut.height / wm_cut.width)), Image.LANCZOS).save(
        WEB / "brand" / "bams-wordmark.png", optimize=True)
    icon_cut.resize((600, round(600 * icon_cut.height / icon_cut.width)), Image.LANCZOS).save(
        WEB / "brand" / "bams-icon.png", optimize=True)
    square(icon_cut, 64).save(WEB / "favicon.png", optimize=True)
    for f in sorted(LOGO.glob("*")) + sorted((WEB / "brand").glob("*")) + [WEB / "favicon.png"]:
        print(f"[rework] {f.relative_to(ROOT)}  {Image.open(f).size}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--seeds", type=int, default=3, help="candidates per job")
    r.add_argument("--only", help=f"comma-separated jobs: {','.join(JOBS)}")
    r.add_argument("--host", choices=list(HOSTS), help="force one (default: laptop, then desktop)")
    f = sub.add_parser("finalize")
    f.add_argument("dir", type=Path)
    for job in JOBS:
        f.add_argument(f"--{job}", type=int, required=True, help=f"which {job}_<n>.png")
    args = p.parse_args()
    render(args) if args.cmd == "render" else finalize(args)


if __name__ == "__main__":
    main()
