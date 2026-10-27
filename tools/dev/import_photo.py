"""Import a client photo (HEIC/PNG/JPEG) into the repo as a clean JPEG.

  python3 tools/dev/import_photo.py <src> <dest.jpg> [--max 6000] [--crop x0,y0,x1,y1]

Applies the camera orientation, converts to sRGB 8-bit, and drops ALL metadata
(phone photos carry GPS location), then saves a high-quality JPEG.
"""
import argparse
import pathlib

from PIL import Image, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dest")
ap.add_argument("--max", type=int, default=6000)
ap.add_argument("--crop", default="")
a = ap.parse_args()
with Image.open(a.src) as raw:
    im = ImageOps.exif_transpose(raw)
    icc = im.info.get("icc_profile")
    im = im.convert("RGB")
if icc:
    try:
        from PIL import ImageCms
        import io
        im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile("sRGB"), outputMode="RGB")
    except Exception:
        pass
if a.crop:
    im = im.crop(tuple(int(v) for v in a.crop.split(",")))
im.thumbnail((a.max, a.max), Image.LANCZOS)
pathlib.Path(a.dest).parent.mkdir(parents=True, exist_ok=True)
im.save(a.dest, "JPEG", quality=93, optimize=True, progressive=True, subsampling=0)  # no exif= -> metadata dropped
print(a.dest, im.size)
