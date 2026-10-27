"""
Opens a source photo for the photo build as plain 8-bit sRGB — whatever the
phone, camera or app saved.

  open_rgb(path)    the photo, upright (camera rotation flag applied), RGB
  signature(path)   "" for an ordinary photo; otherwise what open_rgb has to
                    convert ("load1:icc", "load1:alpha+depth" …)

Used by tools/build-home-media.py (every photo slot) and tools/build-albums.py
(album photos and covers). Before this, both did `.convert("RGB")`, which:

  * drops the colour profile without converting: a photo straight from an
    iPhone (Display P3) came out visibly washed out — berry, mango and matcha
    photos most of all;
  * drops transparency without flattening: what's under the transparent
    pixels (often black) showed instead of white;
  * clips a 16-bit grayscale PNG to a blank white picture.

The conversions here only touch photos that need them. An ordinary photo —
RGB or grayscale, no profile or an sRGB one (Square's product photos carry
a compact sRGB profile, "c2") — goes through exactly the old
`exif_transpose(...).convert("RGB")`, pixel for pixel. That is why
signature() is "" for it and the photo fingerprints (src-img/*-manifest.json)
add it only when it isn't: the photos already built keep their fingerprints
and aren't rebuilt, while a photo that does need converting gets a fingerprint
that changes whenever this file's conversions change (LOADER_VERSION).
"""
import functools
import io

from PIL import Image, ImageCms, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

LOADER_VERSION = 1      # bump when a conversion below changes its output

_DEEP = {"I;16", "I;16B", "I;16L", "I;16N", "I", "F"}
_ALPHA = {"RGBA", "LA", "PA", "RGBa", "La"}
_SRGB = ImageCms.createProfile("sRGB")
# Mid-saturation colours: an sRGB-family profile maps them to themselves (±1
# rounding); Display P3, Adobe RGB, ProPhoto move them by 10+ levels.
_PATCHES = ((200, 100, 100), (100, 200, 100), (100, 100, 200), (230, 180, 60), (60, 160, 200),
            (128, 128, 128), (240, 240, 240), (30, 30, 30))


@functools.lru_cache(maxsize=64)
def _is_srgb(icc):
    """True when an embedded RGB profile is sRGB in all but name (so the
    pixels are already sRGB and nothing needs converting). A profile that
    can't be read is treated as sRGB — what the build always did with it."""
    try:
        prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if prof.profile.xcolor_space.strip() != "RGB":
            return False
        test = Image.frombytes("RGB", (len(_PATCHES), 1), bytes(c for p in _PATCHES for c in p))
        out = ImageCms.profileToProfile(test, prof, _SRGB, outputMode="RGB")
        return max(abs(a - b) for a, b in zip(test.tobytes(), out.tobytes())) <= 3
    except Exception:
        return True


def _needs_icc(mode, icc):
    if not icc:
        return False
    if mode == "CMYK":
        return True
    return mode in ("RGB", "RGBA") and not _is_srgb(icc)


def _transparent(im):
    return im.mode in _ALPHA or "transparency" in im.info


def signature(path):
    """What open_rgb converts for this photo ("" = nothing: the plain path)."""
    with Image.open(path) as im:
        mode, icc, transparent = im.mode, im.info.get("icc_profile"), _transparent(im)
    flat = "RGB" if transparent and mode != "CMYK" else mode       # what open_rgb converts the colour of
    parts = [name for name, on in (("depth", mode in _DEEP), ("alpha", transparent),
                                   ("icc", _needs_icc(flat, icc))) if on]
    return f"load{LOADER_VERSION}:" + "+".join(parts) if parts else ""


def _to_8bit(im):
    """A 16-bit (or 32-bit / float) grayscale photo as 8-bit grayscale,
    scaled — not clipped, which turns everything above 255 white."""
    import numpy as np
    a = np.asarray(im).astype(np.float64)
    if im.mode == "F":
        top = 1.0 if a.size and a.max() <= 1.0 else 255.0
    else:
        top = 65535.0 if im.mode.startswith("I;16") or (a.size and a.max() > 255) else 255.0
    return Image.fromarray(np.clip(np.rint(a * (255.0 / top)), 0, 255).astype(np.uint8), "L")


def open_rgb(path):
    """The photo as an upright 8-bit sRGB image (a new, loaded Image)."""
    with Image.open(path) as raw:
        icc = raw.info.get("icc_profile")
        mode = raw.mode
        im = ImageOps.exif_transpose(raw)
        im.load()
    if im.mode in _DEEP:
        im = _to_8bit(im)
    if _transparent(im):
        # flatten onto white, as /photo-prep does in the browser
        rgba = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba).convert("RGB")
        mode = "RGB" if mode != "CMYK" else mode
    if _needs_icc(mode, icc):
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if im.mode not in ("RGB", "CMYK"):
                im = im.convert("RGB")
            return ImageCms.profileToProfile(im, src, _SRGB, outputMode="RGB")
        except Exception:
            pass                      # an unusable profile: the plain conversion below
    return im.convert("RGB")
