#!/usr/bin/env python3
"""
Refreshes the web masters in src-img/ from the private full-resolution archive.

  python3 tools/make-web-masters.py --from ../layers-photos [--dry-run]

This repository is the public demo of the Layers site, so it does not carry the
camera originals. Those live in the private repo meni-gottesman/layers-photos
(same folder layout: originals/, albums/<NN-slug>/). This script writes a copy
of each one into src-img/ scaled so its long edge is at most 4096 px (page
photos) or 3200 px (album photos) — larger than anything the site serves
(2560 px), so the built site looks the same as one built from the originals.

A master is only rewritten when the archive copy is newer or the size cap would
change it, so re-running is cheap and doesn't churn git. Files that already fit
under the cap are copied byte-for-byte. Metadata is dropped (phone photos carry
GPS); the colour profile is converted to sRGB first.

Page photos can opt out of the cap when a crop needs more pixels: list them in
KEEP_FULL below (compare the widths in src-img/media-manifest.json before and after a run).
"""
import argparse
import io
import json
import pathlib
import shutil
import sys

from PIL import Image, ImageCms, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src-img"
CAPS = {"originals": 4096, "albums": 3200}
KEEP_FULL = {"originals/runners-waving-midrun.jpg"}   # zoomed full-width crop (Story) needs > 4096 px
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def master(src: pathlib.Path, cap: int) -> bytes | None:
    """Encoded web master for src, or None when src already fits (copy as-is)."""
    with Image.open(src) as raw:
        if max(raw.size) <= cap and src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            return None
        im = ImageOps.exif_transpose(raw)
        icc = im.info.get("icc_profile")
        im = im.convert("RGB")
    if icc:
        try:
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                           ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:
            pass
    im.thumbnail((cap, cap), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=93, optimize=True, progressive=True, subsampling=0)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--from", dest="archive", required=True, help="path to a checkout of layers-photos")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    archive = pathlib.Path(a.archive).resolve()
    if not (archive / "originals").is_dir():
        sys.exit(f"error: {archive} doesn't look like the layers-photos archive (no originals/)")

    written = copied = same = 0
    for group, cap in CAPS.items():
        for src in sorted((archive / group).rglob("*")):
            if not src.is_file() or src.suffix.lower() not in EXTS:
                continue
            rel = src.relative_to(archive)
            dest = SRC / rel
            if dest.suffix.lower() == ".heic":
                dest = dest.with_suffix(".jpg")
            if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
                with Image.open(dest) as d:
                    if max(d.size) <= cap or str(rel) in KEEP_FULL:
                        same += 1
                        continue
            data = None if str(rel) in KEEP_FULL else master(src, cap)
            print(f"  {'copy ' if data is None else 'scale'}  {rel}")
            if a.dry_run:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if data is None:
                shutil.copy2(src, dest)
                copied += 1
            else:
                dest.write_bytes(data)
                written += 1
    print(f"\n{written} scaled, {copied} copied, {same} already current"
          + (" (dry run — nothing written)" if a.dry_run else ""))
    if not a.dry_run and (written or copied):
        print("Next: python3 tools/build.py  (rebuilds only the photos that changed)")


if __name__ == "__main__":
    main()
