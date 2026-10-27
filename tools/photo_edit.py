"""
Photo finishing for the site — a small, deterministic retouch pipeline.

Every published photo goes through the same steps, driven by the slot's
"edit" recipe (tuned.edit in src-img/slot-specs.json, or the default retouch
in tools/build-home-media.py; all keys optional):

  rotate      degrees, + = counter-clockwise (straighten a horizon/verticals)
  wb          0–1  automatic white balance strength (shades-of-grey on midtones)
  temp, tint  manual balance after auto: temp + = warmer, tint + = more magenta
  exposure    stops (+/-), applied in linear light
  levels      0–1  auto black/white point strength (percentile based)
  shadows     0–1  lift shadows;   highlights 0–1  recover highlights
  contrast    -1–1 gentle S-curve around mid-grey
  vibrance    -1–1 saturation boost weighted toward muted colours
  saturation  -1–1 flat saturation change
  denoise     0–10 chroma+luma noise reduction at output size (needs OpenCV)
  sharpen     0–2  output sharpening multiplier (1 = default for the size)

After the recipe, a light house grade is applied so photos from five
different cameras read as one set: a touch of warmth, slightly softened
blacks, and restrained oranges (indoor light pushes skin and the counter
orange). house: 0 turns it off.
"""
import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2
except ImportError:          # denoise becomes a no-op without OpenCV
    cv2 = None


def _to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _to_srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _luma(x):
    return x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722


def _soft_clip(x, knee=0.92):
    """Roll highlights off smoothly instead of hard-clipping at 1.0."""
    over = x > knee
    y = x.copy()
    y[over] = knee + (1 - knee) * np.tanh((x[over] - knee) / (1 - knee))
    return y


def _auto_wb_gains(lin, strength):
    l = _luma(lin)
    sat = lin.max(-1) - lin.min(-1)
    m = (l > 0.02) & (l < 0.85) & (sat < 0.6 * lin.max(-1) + 1e-6)
    px = lin[m] if m.sum() > 1000 else lin.reshape(-1, 3)
    p = 6.0                                  # shades-of-grey (Minkowski p-norm)
    means = np.power(np.mean(np.power(px, p), axis=0), 1 / p) + 1e-6
    gains = means.mean() / means
    gains = 1 + strength * (gains - 1)
    return np.clip(gains / gains[1], 0.82, 1.22)


def _s_curve(x, k):
    """k>0 adds contrast, k<0 flattens; pivots on 0.5, keeps 0 and 1 fixed."""
    if abs(k) < 1e-3:
        return x
    smooth = x * x * (3 - 2 * x)             # smoothstep: a gentle S through (0.5, 0.5)
    return np.clip(x + k * (smooth - x), 0, 1)


def finish(im: Image.Image, e: dict) -> Image.Image:
    """Tone/colour recipe on an RGB PIL image (call on the crop, before resizing)."""
    e = e or {}
    if e.get("rotate"):
        w, h = im.size
        r = im.rotate(e["rotate"], resample=Image.BICUBIC, expand=False)
        # crop away the wedges the rotation introduced
        a = abs(np.radians(e["rotate"]))
        cw = int((w * np.cos(a) - h * np.sin(a)))
        ch = int((h * np.cos(a) - w * np.sin(a)))
        cw, ch = max(cw, w // 2), max(ch, h // 2)
        im = r.crop(((w - cw) // 2, (h - ch) // 2, (w - cw) // 2 + cw, (h - ch) // 2 + ch))
    x = np.asarray(im, dtype=np.float32) / 255.0
    lin = _to_lin(x)

    gains = np.ones(3, np.float32)
    if e.get("wb", 0.6):
        gains *= _auto_wb_gains(lin, e.get("wb", 0.6))
    t, g = e.get("temp", 0.0), e.get("tint", 0.0)
    gains *= np.array([1 + t * 0.12, 1 - g * 0.08, 1 - t * 0.12], np.float32)
    # Highlight protection: blown areas (pendant globes, windows) carry no colour
    # information, so a white-balance shift would tint them cyan or orange.
    # Fade the colour correction out as a pixel approaches clipping.
    peak = x.max(-1, keepdims=True)
    protect = np.clip((peak - 0.86) / 0.12, 0, 1)
    protect = protect * protect * (3 - 2 * protect)
    lin = lin * (1 + (gains - 1) * (1 - protect))
    lin = lin * (2.0 ** e.get("exposure", 0.0))
    x = _to_srgb(_soft_clip(lin))
    x = np.clip(x, 0, 1)

    lv = e.get("levels", 0.6)
    if lv:
        l = _luma(x)
        bp = min(np.percentile(l, 0.4), 0.07) * lv
        wp = 1 - (1 - max(np.percentile(l, 99.6), 0.88)) * lv
        x = np.clip((x - bp) / max(wp - bp, 0.3), 0, 1)

    sh, hl = e.get("shadows", 0.0), e.get("highlights", 0.0)
    if sh or hl:
        l = _luma(x)[..., None] + 1e-5
        nl = l + sh * 0.35 * np.power(1 - l, 3) * l ** 0.5 - hl * 0.35 * np.power(l, 3)
        x = np.clip(x * (nl / l), 0, 1)

    x = _s_curve(x, e.get("contrast", 0.08))

    v, s = e.get("vibrance", 0.06), e.get("saturation", 0.0)
    if v or s:
        l = _luma(x)[..., None]
        sat = (x.max(-1) - x.min(-1))[..., None]
        k = 1 + s + v * (1 - np.clip(sat * 1.6, 0, 1))
        x = np.clip(l + (x - l) * k, 0, 1)

    house = e.get("house", 1.0)
    if house:
        l = _luma(x)[..., None]
        # restrain hot oranges (hue ~20-45deg) a little
        r, gg, b = x[..., 0:1], x[..., 1:2], x[..., 2:3]
        orange = np.clip((r - b) * 2 - np.abs(gg - (r + b) / 2) * 3, 0, 1) * np.clip((r - gg) * 4, 0, 1)
        x = l + (x - l) * (1 - 0.10 * house * orange)
        # warm, slightly matte: lift deepest blacks, warm the shadows a hair
        lift = 0.018 * house
        x = x * (1 - lift) + lift
        warm = np.array([1.0 + 0.012 * house, 1.0, 1.0 - 0.02 * house], np.float32)
        x = x * (1 - (1 - l) * 0.5) + (x * warm) * ((1 - l) * 0.5)
        x = np.clip(x, 0, 1)

    return Image.fromarray((x * 255 + 0.5).astype(np.uint8))


def output(im: Image.Image, width: int, height: int, e: dict, full_width: int) -> Image.Image:
    """Resize to a delivery size, then denoise and sharpen for that size."""
    e = e or {}
    r = im.resize((width, height), Image.LANCZOS)
    dn = e.get("denoise", 0)
    if dn and cv2 is not None:
        # noise shrinks as we downscale; scale strength by the reduction factor
        k = max(0.35, min(1.0, width / max(full_width, 1)))
        a = cv2.cvtColor(np.asarray(r), cv2.COLOR_RGB2BGR)
        a = cv2.fastNlMeansDenoisingColored(a, None, h=float(dn) * k, hColor=float(dn) * 1.4 * k,
                                            templateWindowSize=7, searchWindowSize=21)
        r = Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
    sm = e.get("sharpen", 1.0)
    if sm:
        # smaller outputs need a finer, stronger touch; big ones a gentle one
        radius = 0.55 if width <= 720 else 0.75 if width <= 1440 else 0.95
        pct = int((70 if width <= 720 else 60 if width <= 1440 else 50) * sm)
        r = r.filter(ImageFilter.UnsharpMask(radius=radius, percent=pct, threshold=2))
    return r
