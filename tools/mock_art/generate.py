"""Generate placeholder posters/backdrops for the prototype's fictional catalog.

Uses the local ComfyUI pipeline through VibeMMO's driver (tools/comfy.py, Qwen
Image turbo). Every title is made up, so the art is ours to use. Output goes to
web/public/mock/{posters,backdrops}/<id>.webp.

    python tools/mock_art/generate.py            # everything
    python tools/mock_art/generate.py --only neon-tide,signal-lost
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "web" / "src" / "mock" / "catalog.json"
OUT = ROOT / "web" / "public" / "mock"
COMFY = Path.home() / "Documents" / "VibeMMO" / "tools" / "comfy.py"

POSTER_SIZE, POSTER_OUT = "832x1216", (400, 585)
BACKDROP_SIZE, BACKDROP_OUT = "1344x768", (1600, 914)


def poster_prompt(item: dict) -> str:
    kind = "movie" if item["type"] == "movie" else "TV series"
    return (f'Professional {kind} poster for a fictional {kind} titled "{item["title"]}", '
            f'the title "{item["title"]}" in large stylish clean letters near the bottom, '
            f'{item["art"]["poster"]}, high quality key art, no other text')


def backdrop_prompt(item: dict) -> str:
    return f'{item["art"]["backdrop"]}, cinematic film still, high detail, no text'


def render(jobs: list[tuple[str, str]], size: str, out_size: tuple[int, int], dest: Path) -> None:
    if not jobs:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "prompts.txt").write_text("\n".join(p for _, p in jobs), encoding="utf-8")
        subprocess.run([sys.executable, str(COMFY), "--file", str(tmp / "prompts.txt"),
                        "--workflow", "qwen", "--no-style", "--batch", "1", "--size", size,
                        "--prefix", "art", "--out", str(tmp / "png")], check=True)
        dest.mkdir(parents=True, exist_ok=True)
        for i, (item_id, _) in enumerate(jobs, 1):
            im = Image.open(tmp / "png" / f"art_{i:03d}_0.png").convert("RGB")
            im.resize(out_size, Image.LANCZOS).save(dest / f"{item_id}.webp", quality=82)
            print(f"[mock_art] {dest.name}/{item_id}.webp")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated item ids")
    args = p.parse_args()
    items = json.loads(CATALOG.read_text(encoding="utf-8"))["items"]
    if args.only:
        want = set(args.only.split(","))
        items = [i for i in items if i["id"] in want]
    render([(i["id"], poster_prompt(i)) for i in items], POSTER_SIZE, POSTER_OUT, OUT / "posters")
    render([(i["id"], backdrop_prompt(i)) for i in items if i["art"].get("backdrop")],
           BACKDROP_SIZE, BACKDROP_OUT, OUT / "backdrops")


if __name__ == "__main__":
    main()
