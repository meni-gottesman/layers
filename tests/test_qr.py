"""Print QR codes (tools/qr.py): each PNG decodes — with OpenCV, as a phone
would — to the right address, is 1024 px with a white quiet zone of at least
4 modules, and the SVGs are scalable and match."""
import io
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import pytest
from PIL import Image

import content as C
import qr
from conftest import ROOT, edit, seed_root

EXPECTED = {"menu": "https://layerssuperfoodbar.com/menu",
            "order": "https://layerssuperfoodbar.square.site",
            "links": "https://layerssuperfoodbar.com/links"}


def decode(png_bytes):
    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    text, points, _ = cv2.QRCodeDetector().detectAndDecode(img)
    return text


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("qr")
    r = qr.build(C.load_all(seed_root()), out)
    return out, r


def test_targets_from_the_content():
    assert qr.targets(C.load_all(seed_root())) == EXPECTED


@pytest.mark.parametrize("name", EXPECTED)
def test_png_decodes_to_its_address(built, name):
    out, _ = built
    data = (out / f"{name}.png").read_bytes()
    assert decode(data) == EXPECTED[name]


@pytest.mark.parametrize("name", EXPECTED)
def test_png_size_colours_and_quiet_zone(built, name):
    out, _ = built
    im = Image.open(out / f"{name}.png").convert("RGB")
    assert im.size == (1024, 1024)
    assert set(c for _, c in im.getcolors()) == {qr.PAPER, qr.INK}           # dark ink on white, nothing else
    n = qr.make(EXPECTED[name]).symbol_size(scale=1, border=qr.BORDER)[0]
    margin = (1024 // n) * qr.BORDER                                          # 4 modules in pixels
    a = np.asarray(im)
    for band in (a[:margin], a[-margin:], a[:, :margin], a[:, -margin:]):
        assert (band == qr.PAPER).all()
    assert (a[margin:-margin, margin:-margin] == qr.INK).all(axis=-1).any()  # and the code inside it


@pytest.mark.parametrize("name", EXPECTED)
def test_svg_is_scalable_and_labelled(built, name):
    out, _ = built
    root = ET.fromstring((out / f"{name}.svg").read_bytes())
    assert root.get("viewBox") == f"0 0 {root.get('width')} {root.get('height')}"
    title = root.find("{http://www.w3.org/2000/svg}title")
    assert title is not None and EXPECTED[name] in title.text
    assert b'stroke="#26231e"' in (out / f"{name}.svg").read_bytes()         # the same dark ink


def test_rebuild_writes_nothing_when_unchanged(built):
    out, first = built
    assert first == {"written": 6, "unchanged": 0}
    assert qr.build(C.load_all(seed_root()), out) == {"written": 0, "unchanged": 6}


def test_order_code_follows_the_square_link(repo, tmp_path):
    edit(repo, "site.json", lambda d: d["ordering"].update(square_url="https://layers-test.square.site"))
    files = qr.files(C.load_all(repo))
    assert decode(files["order.png"]) == "https://layers-test.square.site"
    assert decode(files["menu.png"]) == EXPECTED["menu"]


def test_the_site_ships_the_codes():
    """public/assets/qr/ holds all six files and the fixed-address codes scan."""
    d = ROOT / "public" / "assets" / "qr"
    for name in EXPECTED:
        assert (d / f"{name}.svg").is_file() and (d / f"{name}.png").is_file(), name
    for name in ("menu", "links"):
        assert decode((d / f"{name}.png").read_bytes()) == EXPECTED[name]
    assert Image.open(io.BytesIO((d / "menu.png").read_bytes())).size == (1024, 1024)
