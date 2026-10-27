"""Labelled contact sheet for every image (and video, first frame) in a folder.

  python3 tools/dev/contact_sheet.py <folder> <out.jpg> [cols] [thumb]

Writes <out.jpg> plus <out.jpg>.json mapping each tag (#1, #2, ...) to its file.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

IMG = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif")
VID = (".mov", ".mp4", ".m4v")


def load(f):
    if f.suffix.lower() in VID:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as t:
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", "1", "-i", str(f), "-frames:v", "1", t.name], check=True)
            return Image.open(t.name).convert("RGB")
    return ImageOps.exif_transpose(Image.open(f)).convert("RGB")


def main():
    d, out = pathlib.Path(sys.argv[1]), sys.argv[2]
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    tw = int(sys.argv[4]) if len(sys.argv) > 4 else 340
    files = sorted(f for f in d.iterdir() if f.suffix.lower() in IMG + VID)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 20)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except OSError:
        font = small = ImageFont.load_default()
    rows = (len(files) + cols - 1) // cols
    th = tw + 24
    sheet = Image.new("RGB", (cols * tw, max(rows, 1) * th), (30, 30, 30))
    dr = ImageDraw.Draw(sheet)
    idx = {}
    for i, f in enumerate(files):
        tag = f"#{i + 1}"
        idx[tag] = str(f)
        im = load(f)
        W, H = im.size
        im.thumbnail((tw - 6, tw - 6))
        x0, y0 = (i % cols) * tw, (i // cols) * th
        sheet.paste(im, (x0 + (tw - im.width) // 2, y0 + (tw - im.height) // 2))
        dr.rectangle([x0 + 4, y0 + 4, x0 + 58, y0 + 28], fill=(0, 0, 0))
        dr.text((x0 + 8, y0 + 5), tag, fill=(255, 230, 80), font=font)
        kind = " VIDEO" if f.suffix.lower() in VID else ""
        dr.text((x0 + 6, y0 + tw + 3), f"{f.name[:30]} {W}x{H}{kind}", fill=(220, 220, 220), font=small)
    sheet.save(out, quality=82)
    pathlib.Path(out + ".json").write_text(json.dumps(idx, indent=1))
    print(out, len(files))


if __name__ == "__main__":
    main()
