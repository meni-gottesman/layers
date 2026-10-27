"""Phase B features (CMS_SPEC §11): the specials order button, delivery links,
the staff tool pages (/photo-prep, /brand) and the polish that came with them."""
import json
import re

import content as C
import render
import validate_content as V
from conftest import ROOT, TODAY, edit, seed_root


def site(root=None):
    return render.Site(root=root or seed_root(), today=TODAY)


def special_html(html):
    """Every <article class="special"> … </article> in a page."""
    return re.findall(r'<article class="special".*?</article>', html, re.S)


def add_special(repo, slug, **fields):
    data = {"name": slug.replace("-", " ").title(), "image": "", "published": True, **fields}
    (repo / "content" / "specials" / f"{slug}.json").write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Specials: order button none | square | link
# ---------------------------------------------------------------------------
def test_phi_velvet_has_no_button_and_says_in_store():
    s = site()
    for key in ("home", "menu", "links"):
        (card,) = [c for c in special_html(s.render(key)) if "Phi Velvet" in c]
        assert '<p class="special__note">In store for a limited time.</p>' in card, key
        assert "btn" not in card and "square.site" not in card, key


def test_order_button_square_and_link(repo):
    add_special(repo, "sq", order_button="square")
    add_special(repo, "own", order_button="link", order_url="https://example.com/order")
    cards = {c.split('class="special__name">')[1].split("<")[0]: c
             for c in special_html(render.Site(root=repo, today=TODAY).render("menu"))}
    sq, own = cards["Sq"], cards["Own"]
    assert ('<a class="btn btn--sage" href="https://layerssuperfoodbar.square.site" target="_blank" '
            'rel="noopener">Order on Square<span class="sr-only"> (opens Square in a new tab)</span></a>') in sq
    assert "special__note" not in sq
    assert ('href="https://example.com/order" target="_blank" rel="noopener">Order<span class="sr-only"> Own</span>'
            '<span class="sr-only"> (opens in a new tab)</span></a>') in own


def test_custom_availability_note_and_its_default(repo):
    add_special(repo, "custom", availability_note="Only at the Saturday run club.")
    add_special(repo, "plain")
    cards = special_html(render.Site(root=repo, today=TODAY).render("menu"))
    assert any("Only at the Saturday run club." in c for c in cards)
    plain = [c for c in cards if ">Plain<" in c][0]
    assert "In store for a limited time." in plain           # missing key = the default


def test_order_button_validation(repo):
    add_special(repo, "needs-link", order_button="link")
    add_special(repo, "unused-link", order_button="square", order_url="https://example.com/x")
    add_special(repo, "bad-choice", order_button="paypal")
    problems = V.validate(repo, today=TODAY)
    err = [p for p in problems if p["level"] == "error" and p["where"] == "Special: Needs Link"]
    assert err and err[0]["field"] == "Order link" and "there’s no order link" in err[0]["message"]
    warn = [p for p in problems if p["where"] == "Special: Unused Link"]
    assert warn and warn[0]["level"] == "warning" and "isn’t used" in warn[0]["message"]
    bad = [p for p in problems if p["where"] == "Special: Bad Choice" and p["field"] == "Order button"]
    assert bad and bad[0]["level"] == "error"


def test_order_button_schema():
    fields = C.COLLECTIONS["specials"][1]
    assert fields["order_button"].options == ("none", "square", "link") and fields["order_button"].default() == "none"
    assert fields["availability_note"].default() == "In store for a limited time."


# ---------------------------------------------------------------------------
# Delivery links (Visit + /links), nothing when empty
# ---------------------------------------------------------------------------
DD = "https://www.doordash.com/store/layers-123/"
UE = "https://www.ubereats.com/store/layers/abc"


def test_no_delivery_links_no_markup():
    s = site()
    assert "visit__delivery" not in s.render("visit") and "Delivery on" not in s.render("links")


def test_delivery_links_on_visit_and_links(repo):
    edit(repo, "site.json", lambda d: d.setdefault("ordering", {}).update(doordash_url=DD, ubereats_url=UE))
    s = render.Site(root=repo, today=TODAY)
    visit, links = s.render("visit"), s.render("links")
    line = re.search(r'<p class="ed-split__fine visit__delivery">.*?</p>', visit, re.S).group(0)
    assert line.index("DoorDash") < line.index("Uber Eats") and f'href="{DD}"' in line
    assert visit.index("ed-ctas") < visit.index("visit__delivery")           # under the order buttons
    assert f'href="{DD}" target="_blank" rel="noopener">Delivery on DoorDash' in links
    assert f'href="{UE}" target="_blank" rel="noopener">Delivery on Uber Eats' in links
    for page in ("home", "menu"):
        assert DD not in s.render(page)


def test_only_the_set_service_shows_and_no_duplicate_button(repo):
    edit(repo, "site.json", lambda d: d.setdefault("ordering", {}).update(ubereats_url=UE))
    edit(repo, "links.json", lambda d: d["buttons"].append({"label": "Uber Eats", "url": UE, "highlight": False}))
    s = render.Site(root=repo, today=TODAY)
    assert "DoorDash" not in s.render("visit") and "Uber Eats" in s.render("visit")
    assert s.render("links").count(f'href="{UE}"') == 1


def test_delivery_link_to_the_wrong_site_is_a_warning(repo):
    edit(repo, "site.json", lambda d: d.setdefault("ordering", {}).update(doordash_url="https://www.ubereats.com/store/x"))
    p = [p for p in V.validate(repo, today=TODAY) if p["field"] == "Ordering → DoorDash link"]
    assert p and p[0]["level"] == "warning" and "doordash.com" in p[0]["message"]


# ---------------------------------------------------------------------------
# Staff tools: /photo-prep and /brand
# ---------------------------------------------------------------------------
def test_staff_pages_are_noindex_and_unlinked(tmp_path):
    s = site()
    out = s.render_all()
    _, urls = render.write_pages(s, out, tmp_path / "out")
    for key, path in (("photo-prep", "/photo-prep"), ("brand", "/brand")):
        html = out[key]
        assert '<meta name="robots" content="noindex">' in html and 'rel="canonical"' not in html
        assert (tmp_path / "out" / key / "index.html").exists() and not any(u.endswith(path) for u in urls)
        assert 'id="m-drawer"' not in html and "footer__grid" not in html        # light chrome
        for other, page in out.items():
            if page and other not in ("photo-prep", "brand"):
                assert f'href="{path}"' not in page, (other, path)               # not in any navigation


def test_staff_pages_load_their_script_and_skip_analytics(repo):
    edit(repo, "site.json", lambda d: d.setdefault("analytics", {}).update(cloudflare_web_analytics_token="a" * 32))
    out = render.Site(root=repo, today=TODAY).render_all()
    for key, html in out.items():
        if html is None:
            continue
        tool = key in ("photo-prep", "brand")
        assert ('/assets/js/staff.js' in html) == tool, key
        assert ("cloudflareinsights" in html) != tool, key
    assert (ROOT / "public" / "assets" / "js" / "staff.js").is_file()


def test_photo_prep_page():
    html = site().render("photo-prep")
    assert '<input class="pp__input" id="pp-file" type="file" accept="image/*"' in html
    assert '<label class="pp__label" for="pp-file">' in html
    assert "Nothing is uploaded anywhere" in html and 'role="status"' in html
    assert "Settings → Camera → Formats → Most Compatible" in html                # the HEIC help
    js = (ROOT / "public" / "assets" / "js" / "staff.js").read_text()
    for must in ("imageOrientation: 'from-image'", "MAX_EDGE = 2400", "LIMIT = 3000000", "0.85", "-web.jpg"):
        assert must in js, must


def test_brand_colours_come_from_the_css_tokens():
    css = (ROOT / "public" / "assets" / "css" / "styles.css").read_text()
    root = re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)
    colours = site().brand_colours()
    assert [c["token"] for c in colours] == [t for t, _, _ in render.BRAND_COLOURS]
    for c in colours:
        assert re.search(rf"--{c['token']}:\s*{c['hex']}\b", root, re.I), c
    html = site().render("brand")
    assert "#3A4A2C" in html and "#E5E0D8" in html and "Layers green" in html


def test_brand_page_downloads_exist():
    html = site().render("brand")
    for url in re.findall(r'href="(/assets/[^"]+)"[^>]*download', html):
        assert (ROOT / "public" / url.lstrip("/")).is_file(), url
    for name in ("menu", "order", "links"):
        assert f'href="/assets/qr/{name}.svg" download="layers-qr-{name}.svg"' in html
        assert f'href="/assets/qr/{name}.png" download="layers-qr-{name}.png"' in html
    assert 'href="/assets/img/wordmark-green.png" download="layers-wordmark-green.png"' in html
    assert "300 × 129 px" in html and "fonts.google.com/specimen/Archivo" in html
    assert 'href="/photo-prep"' in html


# ---------------------------------------------------------------------------
# Polish
# ---------------------------------------------------------------------------
def test_event_partner_on_its_own_line(repo):
    ev = repo / "content" / "events"
    ev.mkdir(exist_ok=True)
    (ev / "run.json").write_text(json.dumps({"title": "Run club", "date": "2026-11-07", "partner": "She Runs Berkeley"}))
    home = render.Site(root=repo, today=TODAY).render("home")
    assert '<p class="event__name">Run club</p>' in home and '<p class="event__partner">With She Runs Berkeley</p>' in home


def test_instagram_list_is_named():
    assert '<ul class="ig__grid" role="list" aria-label="Instagram posts"' in site().render("home")


def test_dated_entries_really_hide():
    """main.js sets [hidden] on an ended special / past event; their display:grid
    and display:flex would win over [hidden] without these rules."""
    css = (ROOT / "public" / "assets" / "css" / "styles.css").read_text()
    assert ".special[hidden],.event[hidden]{display:none}" in css
    assert ".pp__result[hidden]{display:none}" in css
