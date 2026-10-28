"""
Making changes simply: the Edit buttons on the website (staff mode), the
"More sections" every main page can have, and pages of the manager's own.

  * every Edit link opens a real screen of Pages CMS: an entry named in
    .pages.yml, the app's own route shapes, its encodeURIComponent;
  * visitors get nothing new: no staff-mode element is in the HTML, only
    data-edit attributes, and a page without sections is exactly as before;
  * the six kinds of section render in the house style, escape what's typed,
    and name their photos the same way in the photo build, the validator and
    the page;
  * pages of her own: web addresses, the menus, the sitemap, unpublishing;
  * a CMS save (tools/cms_normalize.py, the port of Pages CMS's own save)
    keeps sections and pages exactly.

Seed assertions read the frozen seed (tests/fixtures/seed), never content/.
tools/cms_normalize.py's block support was also checked against Pages CMS
v2.1.8's own code (docs/dev/CMS.md).
"""
import json
import re
import urllib.parse

import pytest
import yaml

import cms_normalize as N
import content as C
import render
import validate_content as V
from conftest import ROOT, TODAY, edit, load_tool, seed_root

media = load_tool(ROOT / "tools" / "build-home-media.py", "media_for_edit_tests")
CONFIG = yaml.safe_load((ROOT / ".pages.yml").read_text())

# Seed photos big enough for any spot (4096 px and up), one too small for most
WIDE, TALL, SQUARE = ("src-img/originals/storefront-run-crowd.jpg", "src-img/originals/serving-with-a-laugh.jpg",
                      "src-img/originals/counter-handoff.jpg")
SMALL = "src-img/originals/special-phi-velvet-cup.jpg"          # 608 × 760

# One section of every kind, as a manager would write them.
SECTIONS = [
    {"type": "text", "eyebrow": "New", "heading": "A year on Channing Way", "text": "Some **bold** words.\n\nMore."},
    {"type": "photo", "image": WIDE, "alt": "Runners outside the shop", "caption": "Saturday", "size": "wide"},
    {"type": "photo-text", "image": TALL, "alt": "Serving a smoothie", "heading": "Catering", "text": "For teams.",
     "button_label": "Ask us", "button_link": "/catering", "photo_side": "right"},
    {"type": "photos", "photos": [{"image": SQUARE, "alt": "One"}, {"image": TALL, "alt": "Two"},
                                  {"image": WIDE, "alt": "Three"}]},
    {"type": "quote", "quote": "“Always pure, never watered down.”", "name": "Layers"},
    {"type": "button", "label": "See the menu", "link": "/menu", "style": "outline"},
]


def site(root=None):
    return render.Site(root=root or seed_root(), today=TODAY)


def built(s, *slots):
    """Pretend the photo build made these slots (pages need the manifest)."""
    s.manifest = {**s.manifest, **{x: {"widths": [480, 960], "aspect": 1.0} for x in slots}}
    return s


def section_slots(key, sections):
    return [p["slot"] for p in C.section_photos(C.sections_prefix(key), sections)]


def custom_page(repo, address, **fields):
    d = repo / "content" / "custom-pages"
    d.mkdir(exist_ok=True)
    data = {"title": address.replace("-", " ").capitalize(), "address": address, "intro": "Hello.", **fields}
    (d / f"{address}.json").write_text(json.dumps(data, ensure_ascii=False))
    return data


def cms_entries():
    """{name: entry} of .pages.yml, groups flattened (as Pages CMS does)."""
    out = {}

    def walk(items):
        for it in items:
            if it.get("type") == "group":
                walk(it["items"])
            else:
                out[it["name"]] = it
    walk(CONFIG["content"])
    return out


EDIT_LINK = re.compile(re.escape(render.EDITOR_URL)
                       + r"(?:/file/(?P<file>[^/?#]+)|/collection/(?P<coll>[^/?#]+)(?:/edit/(?P<path>[^/?#]+)|(?P<new>/new))?)?")


def assert_opens_a_real_screen(url, root):
    """An editor link names an entry of .pages.yml of the right kind and, for
    one entry, a file that exists in that collection's folder."""
    m = EDIT_LINK.fullmatch(url)
    assert m, f"not an editor link: {url}"
    entries = cms_entries()
    if m["file"]:
        name = urllib.parse.unquote(m["file"])
        assert entries[name]["type"] == "file", url
    elif m["coll"]:
        e = entries[urllib.parse.unquote(m["coll"])]
        assert e["type"] == "collection", url
        if m["path"]:
            path = urllib.parse.unquote(m["path"])
            assert path.startswith(e["path"] + "/") and path.endswith(".json"), url
            assert (root / path).is_file(), f"{url}: {path} doesn't exist"


# ---------------------------------------------------------------------------
# The editor links
# ---------------------------------------------------------------------------
def test_editor_links_follow_the_pages_cms_routes():
    e = render.EDITOR_URL
    assert e == "https://app.pagescms.org/meni-gottesman/layers/main"
    assert render.editor_link("pages/home") == f"{e}/file/home"
    assert render.editor_link("pages/404") == f"{e}/file/not-found"
    assert render.editor_link("hours") == f"{e}/file/hours"
    assert render.editor_link("albums") == f"{e}/collection/albums"
    assert render.editor_link("specials/phi-velvet") == (
        f"{e}/collection/specials/edit/content%2Fspecials%2Fphi-velvet%2Ejson")
    assert render.editor_link("custom-pages/summer-menu") == (
        f"{e}/collection/custom-pages/edit/content%2Fcustom-pages%2Fsummer-menu%2Ejson")
    assert render.editor_link("new:custom-pages") == f"{e}/collection/custom-pages/new"
    for bad in ("pages/nope", "nope", "nope/x", "new:nope", "specials/"):
        with pytest.raises(KeyError):
            render.editor_link(bad)


def test_uri_component_is_javascripts_encodeuricomponent():
    for raw, js in (("content/specials/phi-velvet.json", "content%2Fspecials%2Fphi-velvet.json"),
                    ("a b", "a%20b"), ("!'()*-._~", "!'()*-._~"), ("é", "%C3%A9"), ("?&=#+", "%3F%26%3D%23%2B")):
        assert render.uri_component(raw) == js


def test_every_editor_name_is_an_entry_of_pages_yml():
    entries = cms_entries()
    for key, name in render.CMS_FILES.items():
        assert entries[name]["type"] == "file" and entries[name]["path"] == f"content/{key}.json", key
    for folder, name in render.CMS_COLLECTIONS.items():
        assert entries[name]["type"] == "collection" and entries[name]["path"] == f"content/{folder}", folder
    # and every file and collection of the CMS can be reached
    assert {e["name"] for e in entries.values()} == set(render.CMS_FILES.values()) | set(render.CMS_COLLECTIONS.values())


def test_every_edit_button_opens_a_real_screen(repo):
    """Every link the pages carry (data-edit, the bar's data-edit-page and
    data-edit-root, /edit's shortcuts), seed and with sections, a page of her
    own, a special and an event, resolves to a screen and a file that exist."""
    edit(repo, "pages/home.json", lambda d: d.update(sections=SECTIONS))
    custom_page(repo, "summer-menu", sections=SECTIONS[:1], show_in="menu")
    (repo / "content" / "events" / "2026-11-07-run.json").write_text(json.dumps(
        {"title": "Run", "date": "2026-11-07", "published": True}))
    s = built(site(repo), *section_slots("pages/home", SECTIONS))
    seen = 0
    for key, html in s.render_all().items():
        if html is None:
            continue
        for url in re.findall(r'data-edit(?:-page|-root)?="([^"]*)"', html):
            assert_opens_a_real_screen(url, repo)
            seen += 1
        for url in re.findall(r'href="(https://app\.pagescms\.org[^"]*)"', html):
            assert_opens_a_real_screen(url, repo)
    assert seen > 100
    html = s.render("home")
    assert 'data-edit="' + render.editor_link("events/2026-11-07-run") + '"' in html
    assert 'data-edit="' + render.editor_link("specials/phi-velvet") + '"' in html


# ---------------------------------------------------------------------------
# Visitors see nothing new
# ---------------------------------------------------------------------------
def test_visitors_get_no_staff_mode_markup():
    """The pages carry data-edit attributes and nothing else: the Edit buttons
    and the bar exist only once main.js turns staff mode on."""
    for key, html in site().render_all().items():
        if html is None:
            continue
        for word in ("edit-chip", "edit-bar", "is-editing", "edit-host", "viewer__edit"):
            assert word not in html, (key, word)
        assert re.search(r'<body class="[^"]*" data-edit-root="' + re.escape(render.EDITOR_URL) + '"', html), key
        for url in re.findall(r'data-edit(?:-[a-z]+)?="([^"]*)"', html):
            assert url.startswith(render.EDITOR_URL) or not url.startswith("http"), (key, url)
        # no sections and no pages of her own: nothing of them is drawn
        for word in ('class="more', "header--more", "page-custom"):
            assert word not in html, (key, word)


def test_the_pages_differ_only_by_their_data_edit_attributes():
    """Without the attributes the seed's pages are what the site served before
    the Edit buttons: the published pages' HTML holds no element, class or
    text added for them (the full-site diff against the last build is in the
    developer notes, docs/dev/CMS.md)."""
    out = site().render_all()
    home = re.sub(r' data-edit(?:-[a-z]+)?="[^"]*"', "", out["home"])
    assert "<section class=\"ed ed--instagram\" aria-labelledby=\"instagram-title\">" in home
    assert '<header id="site-header" class="header" data-state="transparent">' in home
    assert "\n\n\n" not in home        # an empty "More sections" leaves no blank line
    assert out["home"].count('data-edit="') == 12       # 8 sections, the hours line, 3 in the footer


def test_staff_mode_waits_for_the_switch():
    """main.js adds nothing (and fetches nothing) unless ?edit or the
    remembered switch turned staff mode on; it runs last; print hides it."""
    js = (ROOT / "public" / "assets" / "js" / "main.js").read_text()
    staff = js[js.index("function initStaffMode()"):js.index("function boot()")]
    assert staff.index("if (!on) return;") < staff.index("addEditChip") < staff.index("addEditBar")
    assert "fetch(" not in js[js.index("var EDIT_KEY"):js.index("function boot()")]
    boot = js[js.index("function boot()"):]
    assert boot.index("initOpenNow();") < boot.index("initMotion();") < boot.index("initStaffMode();")
    assert "'layers-edit'" in js and "/^(off|0|false|no|hide)$/i" in js
    css = (ROOT / "public" / "assets" / "css" / "styles.css").read_text()
    assert re.search(r"@media print\{\.edit-chip,\.edit-bar,\.edit-toast,\.viewer__edit\{display:none!important\}", css)


def test_the_edit_start_page():
    html = site().render("edit")
    assert '<meta name="robots" content="noindex">' in html and "cloudflareinsights" not in html
    assert '<a class="btn btn--sage btn--lg" href="/?edit">Show Edit buttons on the website</a>' in html
    assert f'href="{render.EDITOR_URL}" target="_blank" rel="noopener">Open the editor' in html
    assert 'href="?edit=off">Hide Edit buttons</a>' in html
    assert f'href="{render.editor_link("new:custom-pages")}"' in html and "Create a new page" in html
    assert f'href="{render.HANDBOOK_URL}"' in html
    assert render.HANDBOOK_URL == "https://github.com/meni-gottesman/layers/blob/main/docs/HANDBOOK.md"
    assert 'href="/photo-prep"' in html and "data-edit-state" in html
    assert '<a href="/edit" aria-current="page">Edit the website</a>' in html
    # the button that turns the Edit buttons on comes first, and pressing it is step 1
    assert html.index("Show Edit buttons on the website</a>") < html.index('<ol class="edit-steps">')
    for step in ("Press Show Edit buttons on the website</strong>, just above", "press the ✎ Edit button",
                 "Change it and press Save.", "The website updates by itself in 2–4 minutes."):
        assert step in html
    # how to undo a mistake, in the editor's own words (the /actions page isn't open to her)
    assert "under <strong>Actions</strong>, press <strong>Undo my last change</strong>" in html
    assert "/actions" not in html
    assert "Nothing right now: everything checked out at the last update." in html     # no notes


# ---------------------------------------------------------------------------
# "More sections"
# ---------------------------------------------------------------------------
def test_each_kind_of_section_in_the_house_style(repo):
    edit(repo, "pages/home.json", lambda d: d.update(sections=SECTIONS))
    html = built(site(repo), *section_slots("pages/home", SECTIONS)).render("home")
    # after the Instagram section, before the Visit band
    assert html.index("ed--instagram") < html.index('<div class="more">') < html.index("ed ed--visit")
    for want in ('<section class="more__item more-text" aria-labelledby="section-1"',
                 '<p class="eyebrow">New</p>', '<h2 id="section-1" class="chapter__title">A year on Channing Way</h2>',
                 "<p>Some <strong>bold</strong> words.</p>",
                 '<figure class="more__item ed-tile ed-tile--wide"', '<figcaption class="ed-label">Saturday</figcaption>',
                 'src="/assets/img/blocks/home_2-960.jpg"',
                 '<section class="more__item ed-split ed-split--flip" aria-labelledby="section-3"',
                 '<a class="btn btn--sage" href="/catering">Ask us</a>',
                 '<div class="more__item ed-row more-row more-row--3"', "/assets/img/blocks/home_4_3-",
                 "<p>“Always pure, never watered down.”</p>",            # the typed quotes aren't doubled
                 '<figcaption class="ed-label more-quote__who">Layers</figcaption>',
                 '<div class="more__item more-button ed-ctas"', '<a class="btn btn--line" href="/menu">See the menu</a>'):
        assert want in html, want
    for n, kind in enumerate(("text", "photo", "photo and text", "row of photos", "quote", "button"), 1):
        assert (f'data-edit="{render.editor_link("pages/home")}" '
                f'data-edit-label="Edit section {n} ({kind}) under More sections"') in html


def test_sections_escape_what_is_typed(repo):
    evil = '<script>alert(1)</script>'
    edit(repo, "pages/home.json", lambda d: d.update(sections=[
        {"type": "text", "heading": evil, "text": f"[x](javascript:alert(1)) {evil}"},
        {"type": "quote", "quote": f"</p>{evil}", "name": '"><img src=x onerror=alert(1)>'},
        {"type": "button", "label": evil, "link": "/menu"},
        {"type": "button", "label": "Bad", "link": "javascript:alert(1)"},       # the validator refuses it…
        {"type": "photo-text", "image": TALL, "alt": evil, "heading": "H", "button_label": "Go",
         "button_link": "//evil.com"},                                          # …and the page never draws it
    ]))
    html = built(site(repo), *section_slots("pages/home", [{"type": "photo-text"}] * 5)).render("home")
    assert "<script>alert" not in html and "javascript:" not in html and "onerror=alert(1)>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and 'href="//evil.com"' not in html
    assert ">Bad<" not in html and ">Go<" not in html
    assert 'alt="&lt;script&gt;alert(1)&lt;/script&gt;"' in html


def test_every_main_page_can_have_sections(repo):
    for key in C.SECTION_FILES:
        rel = f"{key}.json"
        edit(repo, rel, lambda d, key=key: d.update(sections=[{"type": "text", "heading": f"Added to {key}"}]))
    s = site(repo)
    pages = {cfg["content"]: k for k, cfg in render.PAGE_CONFIG.items() if cfg.get("content")}
    for key in C.SECTION_FILES:
        html = s.render(pages[key])
        assert f">Added to {key}</h2>" in html, key
        assert ('<div class="more more--gap">' in html) == (key == "pages/catering"), key   # after the green form
    assert set(C.SECTION_FILES) == {f"pages/{k}" for k in ("home", "story", "how", "what", "day", "catering", "visit")} | {
        "faq", "menu"}


def test_section_photos_have_one_name_everywhere(repo):
    """content.section_photos names the photos; the photo build makes exactly
    those slots (shape and sizes per kind), the page shows them."""
    assert section_slots("pages/home", SECTIONS) == ["blocks/home_2", "blocks/home_3", "blocks/home_4_1",
                                                     "blocks/home_4_2", "blocks/home_4_3"]
    assert C.sections_prefix("menu") == "blocks/menu"
    assert C.sections_prefix("custom-pages/run-club") == "custom/run-club"
    edit(repo, "pages/home.json", lambda d: d.update(sections=SECTIONS))
    custom_page(repo, "run-club", photo={"image": WIDE, "alt": "Top"}, sections=[SECTIONS[1]])
    custom_page(repo, "draft-page", photo={"image": WIDE, "alt": "Top"}, sections=[SECTIONS[1]], published=False)
    content = C.load_all(repo)
    specs = json.loads((repo / "src-img" / "slot-specs.json").read_text())
    jobs = media.section_slots(content, specs)
    assert set(jobs) == {"blocks/home_2", "blocks/home_3", "blocks/home_4_1", "blocks/home_4_2", "blocks/home_4_3",
                         "custom/run-club_top", "custom/run-club_1"}          # not the draft's
    assert (jobs["blocks/home_2"]["aspect"], jobs["blocks/home_2"]["widths"]) == ("21:9", "full")
    assert (jobs["blocks/home_3"]["aspect"], jobs["blocks/home_3"]["widths"]) == ("4:5", "tall")
    assert (jobs["blocks/home_4_1"]["aspect"], jobs["blocks/home_4_1"]["widths"]) == ("1", "half")
    assert (jobs["custom/run-club_top"]["aspect"], jobs["custom/run-club_top"]["widths"]) == ("21:9", "full")
    assert jobs["blocks/home_2"]["edit"] == media.GENTLE_EDIT and "blocks" in media.GROUPS and "custom" in media.GROUPS
    standard = media.section_slots({**content, "pages": {**content["pages"], "home": {
        **content["pages"]["home"], "sections": [{**SECTIONS[1], "size": "standard", "zoom": "more"}]}}}, specs)
    assert standard["blocks/home_1"]["aspect"] == "3:2" and standard["blocks/home_1"]["zoom"] == 1.35


def _problems(repo, **match):
    return [p for p in V.validate(repo, today=TODAY) if all(m in p[k] for k, m in match.items())]


def test_section_problems_are_named_as_the_cms_shows_them(repo):
    edit(repo, "pages/home.json", lambda d: d.update(sections=[
        {"type": "text"},
        {"type": "photo-text", "image": TALL, "alt": "A", "heading": "H", "button_label": "Go"},
        {"type": "photo", "image": SMALL, "alt": "Too small for a wide band", "size": "wide"},
        {"type": "photos", "photos": [{"image": SQUARE, "alt": "x"}] * 5},
        {"type": "video", "url": "x"},
        {"type": "quote"},
        {"type": "button", "label": "Go", "link": "http://insecure.example"},
    ]))
    found = [p for p in V.validate(repo, today=TODAY) if p["where"] == "Page: Home"]
    errs = {p["field"]: p for p in found if p["level"] == "error"}
    # an empty Text section is only a note: it isn't drawn, and never holds up an update
    (empty,) = [p for p in found if p["field"] == "More sections → Section 1 (Text)"]
    assert empty["level"] == "warning" and "This text section is empty, so it isn’t on the website" in empty["message"]
    assert "“Go” needs a link" in errs["More sections → Section 2 (Photo and text) → Button link"]["message"]
    assert "too small" in errs["More sections → Section 3 (Photo) → Photo"]["message"]
    assert "at most 4" in errs["More sections → Section 4 (Row of photos) → Photos"]["message"]
    assert "doesn’t know (“video”)" in errs["More sections → Section 5"]["message"]
    assert "can’t be empty" in errs["More sections → Section 6 (Quote) → Quote"]["message"]
    assert "https://" in errs["More sections → Section 7 (Button) → Link"]["message"]


def test_a_wide_photo_must_be_wide_enough_after_the_crop(repo):
    # a landscape photo zoomed "A little closer" is fine as Standard; a portrait photo in a wide band keeps a thin strip
    edit(repo, "pages/story.json", lambda d: d.update(sections=[
        {"type": "photo", "image": "src-img/originals/runners-waving-midrun.jpg", "alt": "Runners", "size": "wide"},
        {"type": "photo", "image": WIDE, "alt": "Crowd", "size": "standard", "zoom": "a-little"}]))
    found = _problems(repo, where="Page: The Layers Story", field="More sections")
    assert [p["field"] for p in found] == ["More sections → Section 1 (Photo) → Photo"]
    assert found[0]["level"] == "warning" and "Only part of" in found[0]["message"]


def test_problems_on_a_draft_page_of_her_own_dont_stop_the_update(repo):
    custom_page(repo, "later", sections=[{"type": "text"}], published=False)
    p = _problems(repo, field="More sections → Section 1 (Text)")
    assert p and p[0]["level"] == "warning" and p[0].get("draft") is True


# ---------------------------------------------------------------------------
# Pages of her own
# ---------------------------------------------------------------------------
def test_a_page_of_her_own(repo, tmp_path):
    custom_page(repo, "summer-menu", title="Summer menu", intro="Cold drinks.\nAll summer.",
                sections=[SECTIONS[0], SECTIONS[5]], show_in="menu",
                google_description="Summer drinks at Layers, Berkeley.")
    s = site(repo)
    out = s.render_all()
    html = out["custom/summer-menu"]
    assert "<title>Summer menu | Layers Superfood Bar</title>" in html
    assert '<meta name="description" content="Summer drinks at Layers, Berkeley.">' in html
    assert '<link rel="canonical" href="https://layerssuperfoodbar.com/summer-menu">' in html
    assert '<h1 class="story-head__title story-head__title--long">Summer menu</h1>' in html
    assert '<p class="story-head__lede">Cold drinks.<br>\nAll summer.</p>' in html
    assert 'id="site-header"' in html and 'class="footer"' in html and 'class="signoff"' in html
    assert '<body class="page-custom" ' in html
    assert f'data-edit-page="{render.editor_link("custom-pages/summer-menu")}"' in html
    assert html.count(f'data-edit="{render.editor_link("custom-pages/summer-menu")}"') == 3   # title + 2 sections
    assert '<a data-nav href="/summer-menu" aria-current="page">Summer menu</a>' in html
    for key in ("home", "menu", "faq"):
        assert '<a data-nav href="/summer-menu">Summer menu</a>' in out[key]
        assert '<a data-drawer href="/summer-menu">Summer menu</a>' in out[key]
        assert '<a href="/summer-menu">Summer menu</a>' in out[key]          # footer
    written, urls = render.write_pages(s, out, tmp_path / "out")
    assert (tmp_path / "out" / "summer-menu" / "index.html").read_text() == html
    assert "https://layerssuperfoodbar.com/summer-menu" in urls


def test_google_title_and_a_top_photo(repo):
    custom_page(repo, "run-club", google_title="Run club | Layers", photo={"image": WIDE, "alt": "Runners"},
                sections=[SECTIONS[0]])
    html = built(site(repo), "custom/run-club_top").render("custom/run-club")
    assert "<title>Run club | Layers</title>" in html
    assert 'src="/assets/img/custom/run-club_top-960.jpg"' in html and 'alt="Runners"' in html
    assert '<div class="more more--gap">' in html                # sections after the photo get the gap


def test_where_a_page_is_linked(repo):
    custom_page(repo, "b-footer", title="B footer", show_in="footer")
    custom_page(repo, "c-nowhere", title="C nowhere", show_in="none")
    custom_page(repo, "a-menu", title="A menu", show_in="menu")
    custom_page(repo, "d-menu", title="D menu", show_in="menu")
    custom_page(repo, "e-menu", title="E menu", show_in="menu")
    custom_page(repo, "f-draft", title="F draft", show_in="menu", published=False)
    home = site(repo).render("home")
    header = home[home.index('<nav class="header__nav"'):home.index("</nav>", home.index('<nav class="header__nav"'))]
    footer = home[home.index('aria-label="Footer"'):]
    footer = footer[:footer.index("</nav>")]
    assert re.findall(r'data-nav href="/([a-z-]+)"', header)[-2:] == ["a-menu", "d-menu"]   # two, in title order
    assert "/e-menu" not in header and '<a href="/e-menu">E menu</a>' in footer               # the third: footer
    assert '<a href="/b-footer">B footer</a>' in footer and "/b-footer" not in header
    assert "/c-nowhere" not in home and "/f-draft" not in home
    assert site(repo).render_all()["custom/c-nowhere"] is not None                            # still at its address
    assert 'name="robots" content="noindex"' in site(repo).render_all()["custom/c-nowhere"]      # unlisted: not in Google
    assert 'class="header header--more"' in home
    w = _problems(repo, where="Your page: E menu", field="Show it in")
    assert w and w[0]["level"] == "warning" and "“A menu” and “D menu” (the first 2 by page title, A–Z)" in w[0]["message"]


def test_the_main_menu_hands_over_to_the_phone_menu_only_when_it_must():
    """One short name changes nothing (the site's own 1100 px); longer ones
    move the switch just as far as they need; the longest names allowed
    still fit on a computer screen, so the desktop menu never disappears."""
    assert render.header_more([]) == ""
    assert render.header_more(["Run Club"]) == "header--more"
    assert render.header_more(["Saturday Run Club"]) == "header--more"
    assert render.header_more(["Run Club", "Jobs"]) == "header--more"
    assert render.header_more(["Saturday Run Club", "Jobs"]) == "header--more header--more-1140"
    assert render.header_more(["Saturday Run Club", "Holiday Gift Guide"]) == "header--more header--more-1220"
    widest = ["W" * C.MENU_NAME_MAX]                        # the widest one name can be: still fits
    assert C.nav_needed(widest) <= C.NAV_ROOM_PX and render.header_more(widest).endswith("-1140")
    css = (ROOT / "public" / "assets" / "css" / "styles.css").read_text()
    for w in render.HEADER_WIDTHS:
        assert (f"@media (max-width:{w}px){{\n  .header--more-{w} .header__nav{{display:none}}\n"
                f"  .header--more-{w} .burger{{display:block}}") in css, w
    assert "header--more-xl" not in css


# Names measured in Chrome in the menu's type (Archivo semi-condensed, 13 px,
# uppercase, .08em), Oct 2026: the estimate never comes out narrower, and
# not much wider either.
MEASURED = {"Saturday Run Club": 139.7, "Holiday Gift Guide": 137.1, "Gifts for every runner": 176.9,
            "How We Make It": 112.9, "Our Story": 77.1, "Run Club": 66.7, "Catering": 67.9, "Jobs": 35.6}


def test_menu_widths_are_estimated_safely():
    for name, px in MEASURED.items():
        assert px <= C.nav_width(name) <= px * 1.05, (name, C.nav_width(name), px)
    assert C.nav_width("saturday run club") == C.nav_width("SATURDAY RUN CLUB")      # shown in capitals
    assert C.nav_width("🏃") == round(1.03 * C.NAV_UNKNOWN_PX, 1)                   # anything else: wide
    # the site's own row: Menu, Our Story, How We Make It, Catering, Visit + the Order button, 20 px apart
    assert C.NAV_BASE_PX == round(38.9 + 77.1 + 112.9 + 67.9 + 34.3 + 184.6 + 5 * 20, 1)


def test_a_page_whose_name_doesnt_fit_goes_in_the_footer(repo):
    """Too long a title, a third page, or two names too wide together: the
    page is in the footer only, and the note says why and what to do."""
    custom_page(repo, "run-club", title="Saturday Morning Run Club Berkeley", show_in="menu")
    home = site(repo).render("home")
    assert "/run-club" not in home[:home.index("</header>")] and '<a href="/run-club">Saturday Morning' in home
    (w,) = _problems(repo, where="Your page: Saturday Morning", field="Name in the menu")
    assert w["level"] == "warning" and "34 characters" in w["message"] and "up to 18" in w["message"]
    assert not [p for p in V.validate(repo, today=TODAY) if p["level"] == "error"]
    # a "Name in the menu" puts it there; the footer keeps the page's title
    edit(repo, "custom-pages/run-club.json", lambda d: d.update(menu_title="Run Club"))
    home = site(repo).render("home")
    assert '<a data-nav href="/run-club">Run Club</a>' in home and '<a data-drawer href="/run-club">Run Club</a>' in home
    assert '<a href="/run-club">Saturday Morning Run Club Berkeley</a>' in home
    assert not _problems(repo, where="Your page: Saturday Morning")
    # two names too wide together: the second (A–Z) waits in the footer
    edit(repo, "custom-pages/run-club.json", lambda d: d.update(show_in="footer"))
    custom_page(repo, "gifts", title="ZZ", menu_title="MMMMMMMMMMMMMMMMMM", show_in="menu")
    custom_page(repo, "aa", title="AA", menu_title="WWWWWWWWWWWWWWWWWW", show_in="menu")
    links = C.custom_page_links(C.load_all(repo)["custom-pages"])
    assert [p["slug"] for p in links["menu"]] == ["aa"]
    assert [(p["slug"], why) for p, why in links["overflow"]] == [("gifts", "wide")]
    (w,) = _problems(repo, where="Your page: ZZ", field="Name in the menu")
    assert "Together with “WWWWWWWWWWWWWWWWWW”" in w["message"]
    # and whatever is in it fits
    assert C.nav_needed([C.menu_name(p) for p in links["menu"]]) <= C.NAV_ROOM_PX


def test_name_in_the_menu_is_at_most_18_characters():
    f = C.COLLECTIONS["custom-pages"][1]["menu_title"]
    assert f.max == C.MENU_NAME_MAX == 18
    (yml,) = [x for x in cms_entries()["custom-pages"]["fields"] if x["name"] == "menu_title"]
    assert yml["options"]["maxlength"] == 18 and not yml.get("required")


@pytest.mark.parametrize("stem,address,level,says", [
    ("menu", "menu", "error", "/menu is already used by the website itself"),
    ("summer", "Summer Menu", "error", "for example summer-menu"),
    ("summer", "winter", "warning", "this page is still at /summer — changing “Web address” doesn’t move it"),
    ("cdn-cgi", "cdn-cgi", "error", "already used"),
])
def test_web_addresses(repo, stem, address, level, says):
    d = repo / "content" / "custom-pages"
    d.mkdir()
    (d / f"{stem}.json").write_text(json.dumps({"title": "T", "address": address, "intro": "x"}))
    found = [p for p in V.validate(repo, today=TODAY) if p["field"] == "Web address"]
    assert found and found[0]["level"] == level and says in found[0]["message"] and found[0]["where"] == "Your page: T"
    if level == "warning":     # an address changed after the first Save never holds up an update…
        assert not [p for p in V.validate(repo, today=TODAY) if p["level"] == "error"]
        assert site(repo).render_all()["custom/summer"] is not None              # …and the page stays put
    if stem == "menu":   # even unchecked, a page of her own never replaces one of the site's
        s = site(repo)
        assert "custom/menu" not in s.pages and 'class="story-head menu-head"' in s.render("menu")


def test_a_file_name_that_cant_be_an_address(repo):
    d = repo / "content" / "custom-pages"
    d.mkdir()
    (d / "Summer Menu.json").write_text(json.dumps({"title": "T", "address": "summer-menu"}))
    found = [p for p in V.validate(repo, today=TODAY) if p["level"] == "error"]
    assert any(p["field"] == "Web address" and "can’t be used in a web address" in p["message"] for p in found)


def test_reserved_addresses_cover_every_page_and_tool():
    outs = {cfg["out"] for cfg in render.PAGE_CONFIG.values()} - {"index"}
    assert outs <= set(C.RESERVED_ADDRESSES) and set(C.SITE_PATHS) == outs
    addr = next(f for f in cms_entries()["custom-pages"]["fields"] if f["name"] == "address")
    assert addr["pattern"]["regex"] == C.address_pattern()
    assert cms_entries()["custom-pages"]["filename"] == {"template": "{fields.address}.json", "field": False}


def test_unpublished_and_deleted_pages_leave_the_site(repo, tmp_path):
    out_dir = tmp_path / "out"
    (out_dir / "keep-me").mkdir(parents=True)
    (out_dir / "keep-me" / "index.html").write_text("<body class=\"page-other\">not ours")
    custom_page(repo, "pop-up", sections=[SECTIONS[0]])
    s = site(repo)
    render.write_pages(s, s.render_all(), out_dir)
    assert (out_dir / "pop-up" / "index.html").is_file()
    edit(repo, "custom-pages/pop-up.json", lambda d: d.update(published=False))
    s = site(repo)
    _, urls = render.write_pages(s, s.render_all(), out_dir)
    assert not (out_dir / "pop-up").exists() and not any("pop-up" in u for u in urls)
    custom_page(repo, "pop-up", sections=[SECTIONS[0]])
    s = site(repo)
    render.write_pages(s, s.render_all(), out_dir)
    (repo / "content" / "custom-pages" / "pop-up.json").unlink()                    # deleted in the CMS
    s = site(repo)
    render.write_pages(s, s.render_all(), out_dir)
    assert not (out_dir / "pop-up").exists() and (out_dir / "keep-me" / "index.html").is_file()


def test_a_page_with_only_its_title_is_a_note(repo):
    (repo / "content" / "custom-pages").mkdir()
    (repo / "content" / "custom-pages" / "empty.json").write_text(json.dumps({"title": "Empty", "address": "empty"}))
    w = _problems(repo, where="Your page: Empty")
    assert [p["level"] for p in w] == ["warning"] and "only its title" in w[0]["message"]


# ---------------------------------------------------------------------------
# A CMS save keeps it all
# ---------------------------------------------------------------------------
def _entry(name):
    return next(e for e in N.Cms(ROOT).entries if e["name"] == name)


def test_a_cms_save_keeps_sections_and_pages_exactly(repo):
    """Hand-written sections and a hand-written page, saved the way Pages CMS
    saves them: no problems, the same again on a second save, and the same
    site before and after."""
    cms = N.Cms(ROOT)
    edit(repo, "pages/home.json", lambda d: d.update(sections=SECTIONS))
    custom_page(repo, "run-club", photo={"image": WIDE, "alt": "Top"}, sections=SECTIONS, show_in="menu")
    slots = section_slots("pages/home", SECTIONS) + section_slots("custom-pages/run-club", SECTIONS) + [
        "custom/run-club_top"]
    before = built(site(repo), *slots).render_all()
    for rel in ("content/pages/home.json", "content/custom-pages/run-club.json"):
        p = repo / rel
        text, problems = N.save(json.loads(p.read_text()), cms.entry_for(rel), cms)
        assert not problems, problems
        again, problems = N.save(json.loads(text), cms.entry_for(rel), cms)
        assert again == text and not problems
        p.write_text(text)
    saved = json.loads((repo / "content" / "pages" / "home.json").read_text())["sections"]
    assert [s["type"] for s in saved] == [s["type"] for s in SECTIONS]
    assert list(saved[2])[:2] == ["type", "image"]                       # the kind first, then its fields in order
    assert saved[1]["focus"] == "auto" and saved[5]["style"] == "outline"
    assert built(site(repo), *slots).render_all() == before


def test_a_cms_save_refuses_what_it_would_lose():
    home = json.loads((seed_root() / "content" / "pages" / "home.json").read_text())
    for section, kind in (({"type": "video"}, "invalid"), ({"type": "text", "heading": "Hi", "colour": "red"},
                                                            "undeclared"),
                          ({"type": "photo", "alt": "no photo"}, "invalid")):
        _, problems = N.save({**home, "sections": [section]}, _entry("home"), N.Cms(ROOT))
        assert problems and problems[0]["kind"] == kind, section
    # an item added without choosing its kind (null) is dropped by the save, as in the CMS
    text, problems = N.save({**home, "sections": [None, {"type": "quote", "quote": "Hi"}]}, _entry("home"), N.Cms(ROOT))
    assert not problems and json.loads(text)["sections"] == [{"type": "quote", "quote": "Hi"}]


def test_the_cms_section_kinds_match_the_site():
    comp = CONFIG["components"]["more-sections"]
    assert comp["type"] == "block" and comp["blockKey"] == C.SECTIONS.key
    assert [(b["name"], b["label"]) for b in comp["blocks"]] == [(k, b.label) for k, b in C.SECTION_BLOCKS.items()]
    assert comp["list"]["collapsible"]["summary"] == "Section {index}"       # the validator's "Section 2 (…)"
    users = [e["name"] for e in cms_entries().values()
             if any(f.get("component") == "more-sections" for f in e.get("fields") or [])]
    assert sorted(users) == sorted(["home", "story", "how", "what", "day", "catering", "visit", "faq", "menu",
                                    "custom-pages"])
    # "More sections" near the end: the page's own fields first, then the
    # sections, then only what is rarely needed (the film's spoken texts),
    # and "Google and shared links" last
    for e in cms_entries().values():
        names = [f["name"] for f in e.get("fields") or []]
        if "sections" in names and e["type"] == "file":
            after = names[names.index("sections") + 1:]
            assert after[-1:] == ["seo"] and set(after) <= {"film", "seo"}, e["name"]
