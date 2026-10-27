"""Slice a tall screenshot into viewable panels.  python3 tools/dev/slice.py <in.png> <out-prefix> <width> <panel-height>"""
import sys
from PIL import Image
src, prefix, w, seg = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
im = Image.open(src).convert("RGB"); im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
n = 0
for y in range(0, im.height, seg):
    n += 1; im.crop((0, y, w, min(im.height, y + seg))).save(f"{prefix}_{n}.jpg", quality=82)
print(n, "panels", im.size)
