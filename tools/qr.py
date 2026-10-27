"""
QR codes for print — table tents, flyers, the window, a poster at an event.

  python3 tools/build.py      # the build's "qr" step writes them
  python3 tools/qr.py         # just the QR codes

Three codes, written to public/assets/qr/ as SVG (for printers and design
apps: sharp at any size) and PNG (1024 × 1024 px, for everything else):

  menu   https://layerssuperfoodbar.com/menu
  order  the Square store (content/site.json → Ordering → Square store link)
  links  https://layerssuperfoodbar.com/links   (the link-in-bio page)

They always point at the PRODUCTION address, never at a preview, because a
printed code can't be changed later. Dark ink on white with at least the
4-module quiet zone the QR standard asks for: scanners need the contrast and
the margin, so neither is styled. The PNG keeps whole-pixel modules (no
blurry edges): the code is drawn at the largest whole scale that fits and
centred, so the white margin is 4 modules or a little more.

The /brand staff page shows and links all six files. tests/test_qr.py decodes
every PNG with OpenCV and checks the address.
"""
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "assets" / "qr"
SITE_URL = "https://layerssuperfoodbar.com"    # same as render.SITE_URL

INK = (0x26, 0x23, 0x1E)    # --ink: near-black, the darkest colour in the system
PAPER = (0xFF, 0xFF, 0xFF)
SIZE = 1024                 # PNG width and height, px
BORDER = 4                  # quiet zone, in modules (the minimum the standard allows)
SVG_SCALE = 10              # SVG module size: only its default display size; it scales freely

# name -> (label shown on /brand, what it's for)
CODES = {
    "menu": ("Menu", "Opens the menu on the website."),
    "order": ("Order", "Opens the Square store to order for pickup."),
    "links": ("Link in bio", "Opens the /links page: ordering, menu, catering, visit."),
}


def targets(content):
    """{name: url} from the loaded content (tools/content.py load_all)."""
    return {
        "menu": f"{SITE_URL}/menu",
        "order": content["site"]["ordering"]["square_url"].strip(),
        "links": f"{SITE_URL}/links",
    }


def make(url):
    """The QR symbol for a URL. Error correction starts at M (15 % of the code
    can be smudged or covered and it still scans) and is raised for free
    whenever the same symbol size has room for more."""
    import segno
    return segno.make(url, error="m", boost_error=True, micro=False)


def png_bytes(qr):
    """SIZE × SIZE PNG: whole-pixel modules, centred, two-colour palette."""
    from PIL import Image
    rows = [[1 if dark else 0 for dark in row] for row in qr.matrix_iter(scale=1, border=BORDER)]
    n = len(rows)
    scale = SIZE // n
    if scale < 1:
        raise ValueError(f"QR code too dense for {SIZE} px ({n} modules)")
    palette = list(PAPER) + list(INK)
    small = Image.new("P", (n, n))
    small.putpalette(palette)
    small.putdata([v for row in rows for v in row])
    big = small.resize((n * scale, n * scale), Image.NEAREST)
    canvas = Image.new("P", (SIZE, SIZE), 0)
    canvas.putpalette(palette)
    off = (SIZE - n * scale) // 2
    canvas.paste(big, (off, off))
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def svg_bytes(qr, title):
    """SVG with a default size AND a viewBox, so design apps and browsers can
    scale it (segno writes one or the other)."""
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=SVG_SCALE, border=BORDER, dark="#%02x%02x%02x" % INK,
            light="#%02x%02x%02x" % PAPER, xmldecl=False, title=title, svgclass=None, lineclass=None)
    px = qr.symbol_size(scale=SVG_SCALE, border=BORDER)[0]
    svg = buf.getvalue().decode("utf-8")
    head = f'width="{px}" height="{px}"'
    if head not in svg:
        raise ValueError("unexpected SVG from segno")
    return svg.replace(head, f'{head} viewBox="0 0 {px} {px}"', 1).encode("utf-8")


def files(content):
    """{filename: bytes} for every code."""
    out = {}
    for name, url in targets(content).items():
        qr = make(url)
        out[f"{name}.png"] = png_bytes(qr)
        out[f"{name}.svg"] = svg_bytes(qr, f"QR code: {CODES[name][0]} — {url}")
    return out


def build(content, out_dir=OUT):
    """Write the codes; a file whose bytes haven't changed is left alone."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = unchanged = 0
    for name, data in files(content).items():
        dest = out_dir / name
        if dest.is_file() and dest.read_bytes() == data:
            unchanged += 1
            continue
        dest.write_bytes(data)
        written += 1
    return {"written": written, "unchanged": unchanged}


def main():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import content as content_mod
    r = build(content_mod.load_all(ROOT))
    print(f"QR codes: {r['written']} written, {r['unchanged']} unchanged ({OUT.relative_to(ROOT)})")


if __name__ == "__main__":
    main()
