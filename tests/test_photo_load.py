"""Opening source photos for the photo build (tools/photo_load.py): colour
profiles converted to sRGB, transparency flattened onto white, 16-bit
grayscale scaled — and every ordinary photo exactly as before, with the same
fingerprint."""
import struct

import pytest
from PIL import Image, ImageCms

import photo_load
from conftest import ROOT, load_tool

media = load_tool(ROOT / "tools" / "build-home-media.py", "media_for_load_tests")


def _s15(v):
    return struct.pack(">i", round(v * 65536))


def p3_icc():
    """A minimal ICC v2 display profile with Display P3's primaries (D50-
    adapted, as in Apple's profile) and a 2.2 gamma — what an iPhone photo
    carries, built here so the test runs anywhere."""
    def xyz(x, y, z):
        return b"XYZ " + b"\0" * 4 + _s15(x) + _s15(y) + _s15(z)
    curve = b"curv" + b"\0" * 4 + struct.pack(">I", 1) + struct.pack(">H", round(2.2 * 256)) + b"\0\0"
    text = b"Display P3 (test)\0"
    desc = (b"desc" + b"\0" * 4 + struct.pack(">I", len(text)) + text + b"\0" * 4 + b"\0" * 4
            + b"\0\0" + b"\0" + b"\0" * 67)
    tags = [(b"desc", desc), (b"wtpt", xyz(0.9642, 1.0, 0.8249)), (b"rXYZ", xyz(0.5151, 0.2412, -0.0011)),
            (b"gXYZ", xyz(0.2919, 0.6922, 0.0419)), (b"bXYZ", xyz(0.1572, 0.0666, 0.7841)),
            (b"rTRC", curve), (b"gTRC", curve), (b"bTRC", curve), (b"cprt", b"text" + b"\0" * 4 + b"none\0")]
    table, body, offset = b"", b"", 128 + 4 + 12 * len(tags)
    for sig, data in tags:
        while len(data) % 4:
            data += b"\0"
        table += sig + struct.pack(">II", offset + len(body), len(data))
        body += data
    size = offset + len(body)
    header = (struct.pack(">I", size) + b"\0" * 4 + struct.pack(">I", 0x02100000) + b"mntrRGB XYZ "
              + b"\0" * 12 + b"acsp" + b"\0" * 24 + struct.pack(">I", 0)
              + _s15(0.9642) + _s15(1.0) + _s15(0.8249) + b"\0" * 48)
    assert len(header) == 128
    return header + struct.pack(">I", len(tags)) + table + body


PATCH = (200, 100, 100)        # a berry red


def tagged(tmp_path, icc, name="p3.jpg", color=PATCH):
    f = tmp_path / name
    Image.new("RGB", (64, 48), color).save(f, "JPEG", quality=95, icc_profile=icc)
    return f


def test_a_display_p3_photo_is_converted_not_washed_out(tmp_path):
    f = tagged(tmp_path, p3_icc())
    assert photo_load.signature(f) == "load1:icc"
    naive = Image.open(f).convert("RGB").getpixel((32, 24))
    good = photo_load.open_rgb(f).getpixel((32, 24))
    # P3's red is redder than sRGB's: the same numbers mean a more saturated
    # colour, so in sRGB the red goes up and the others down
    assert good[0] > naive[0] + 5 and good[1] < naive[1] - 3 and good[2] < naive[2]


def test_srgb_photos_are_left_exactly_as_they_were(tmp_path):
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    for f in (tagged(tmp_path, srgb, "srgb.jpg"), tagged(tmp_path, None, "plain.jpg")):
        assert photo_load.signature(f) == ""
        with Image.open(f) as raw:
            assert photo_load.open_rgb(f).tobytes() == raw.convert("RGB").tobytes()


def test_transparency_is_flattened_onto_white(tmp_path):
    im = Image.new("RGBA", (10, 10), (0, 0, 0, 0))            # fully transparent black
    im.putpixel((5, 5), (30, 120, 40, 255))
    f = tmp_path / "logo.png"
    im.save(f)
    assert "alpha" in photo_load.signature(f)
    out = photo_load.open_rgb(f)
    assert out.mode == "RGB" and out.getpixel((0, 0)) == (255, 255, 255) and out.getpixel((5, 5)) == (30, 120, 40)


def test_16_bit_grayscale_is_scaled_not_clipped_to_white(tmp_path):
    im = Image.new("I;16", (8, 8), 32768)
    f = tmp_path / "gray16.png"
    im.save(f)
    assert Image.open(f).mode.startswith("I")
    assert "depth" in photo_load.signature(f)
    v = photo_load.open_rgb(f).getpixel((0, 0))
    assert 120 <= v[0] <= 135 and v[0] == v[1] == v[2]        # mid-grey, not 255


def test_the_photo_build_uses_it(tmp_path, monkeypatch):
    """End to end through build-home-media's make_slot: the P3 photo's built
    file has the converted colour, and its fingerprint carries the loader."""
    f = tagged(tmp_path, p3_icc(), color=PATCH)
    big = tmp_path / "big.jpg"
    Image.open(f).resize((1200, 900)).save(big, "JPEG", quality=95, icc_profile=p3_icc())
    monkeypatch.setattr(media, "OUT", tmp_path / "out")
    job = {"src": "x", "aspect": "4:3", "widths": "thumb", "max_width": None, "focal": [0.5, 0.5], "zoom": 1.0,
           "edit": {}}
    made, _ = media.make_slot("events/test", job, big)
    built = Image.open(tmp_path / "out" / "events" / f"test-{max(made)}.jpg").convert("RGB")
    r, g, b = built.getpixel((built.width // 2, built.height // 2))
    assert r > PATCH[0] + 5 and g < PATCH[1] - 3
    plain = tmp_path / "plain.jpg"
    Image.open(big).convert("RGB").save(plain, "JPEG", quality=95)
    assert media.fingerprint(job, big) != media.fingerprint(job, plain)


@pytest.mark.parametrize("mode", ["L", "P", "CMYK"])
def test_other_ordinary_modes_are_unchanged(tmp_path, mode):
    im = Image.new("RGB", (16, 16), (120, 160, 90)).convert(mode)
    f = tmp_path / f"m.{'jpg' if mode in ('L', 'CMYK') else 'png'}"
    im.save(f)
    assert photo_load.signature(f) == ""
    with Image.open(f) as raw:
        assert photo_load.open_rgb(f).tobytes() == raw.convert("RGB").tobytes()


def test_unreadable_profiles_fall_back_to_the_plain_conversion(tmp_path):
    f = tagged(tmp_path, b"not a profile at all" * 8, "junk.jpg")
    assert photo_load.signature(f) == ""
    with Image.open(f) as raw:
        assert photo_load.open_rgb(f).tobytes() == raw.convert("RGB").tobytes()
