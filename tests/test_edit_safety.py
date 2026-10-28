"""
The second pass on "change anything simply": the places a manager following
the natural path could still end up with something broken, hidden or
confusing — each one now either can't happen or comes with a plain note.

  * links to the site's own pages: a typo is an error that says what was
    probably meant; a page that's switched off simply isn't linked until it's
    back (buttons, the announcement, /links, events, formatted text);
  * a hand-picked Instagram post the grid would never show is an error;
  * a page whose web address another page already had (the CMS saves it as
    "<address>-1"), or whose address was changed after the first Save, is a
    warning that says where the page really is — never an error;
  * an empty Text section isn't drawn and never holds up an update;
  * the Edit buttons' entry links have no file extension, so signing in on
    the way returns her to the right screen;
  * /edit lists what's worth a look, with a link to each screen;
  * smaller things: times with a stray space, a new special's label, the
    sections before a page's closing words, a page's own photo when shared,
    the editing bar early in the Tab order, the photo help's full address.

Seed assertions read the frozen seed (tests/fixtures/seed), never content/.
"""
import json
import re
import urllib.parse

import pytest
import yaml

import content as C
import render
import validate_content as V
from conftest import ROOT, TODAY, edit, seed_root

WIDE = "src-img/originals/storefront-run-crowd.jpg"
TALL = "src-img/originals/serving-with-a-laugh.jpg"


def site(root=None):
    return render.Site(root=root or seed_root(), today=TODAY)


def built(s, *slots):
    s.manifest = {**s.manifest, **{x: {"widths": [480, 960, 1200], "aspect": 1.0} for x in slots}}
    return s


def page(repo, address, **fields):
    d = repo / "content" / "custom-pages"
    d.mkdir(exist_ok=True)
    data = {"title": address.replace("-", " ").capitalize(), "address": address, "intro": "Hello.", **fields}
    (d / f"{address}.json").write_text(json.dumps(data, ensure_ascii=False))
    return data


def problems(repo, **match):
    return [p for p in V.validate(repo, today=TODAY) if all(m in p[k] for k, m in match.items())]


def errors(repo):
    return [p for p in V.validate(repo, today=TODAY) if p["level"] == "error"]


# ---------------------------------------------------------------------------
# Links to the site's own pages
# ---------------------------------------------------------------------------
def test_site_page_reads_a_link_as_the_page_it_goes_to():
    assert C.site_page("/menu") == C.site_page("/menu/") == C.site_page(" /menu#bowls ") == "/menu"
    assert C.site_page("/") == C.site_page("/#who") == "/"
    for other in ("https://layerssuperfoodbar.square.site", "mailto:hi@x.co", "#faq", "//evil.com",
                  "/assets/qr/menu.png", "/sitemap.xml", "/api/menu", ""):
        assert C.site_page(other) is None, other


def test_a_typo_in_a_link_is_an_error_that_suggests_the_page(repo):
    page(repo, "run-club", sections=[{"type": "text", "heading": "Hi"}])
    edit(repo, "pages/home.json", lambda d: d.update(sections=[
        {"type": "button", "label": "Join us", "link": "/run-clubb"},
        {"type": "button", "label": "Menu", "link": "/Menu"},
        {"type": "button", "label": "Visit", "link": "/layers/visit"},
        {"type": "text", "text": "See [our menu](/menus) and [the story](/story)."},
    ]))
    edit(repo, "announcement.json", lambda d: d.update(enabled=True, message="Hi", link_label="Go",
                                                        link_url="/nowhere-at-all"))
    errs = {p["field"]: p["message"] for p in errors(repo)}
    assert "/run-clubb isn’t a page on the website" in errs["More sections → Section 1 (Button) → Link"]
    assert "Did you mean /run-club?" in errs["More sections → Section 1 (Button) → Link"]
    assert "write /menu" in errs["More sections → Section 2 (Button) → Link"]
    assert "Leave out /layers" in errs["More sections → Section 3 (Button) → Link"]
    assert "Did you mean /menu?" in errs["More sections → Section 4 (Text) → Text"]
    assert "Check the spelling" in errs["Link"]                     # the announcement's
    assert len(errs) == 5                                           # /story is fine


def test_a_link_to_a_switched_off_page_is_a_note_and_isnt_drawn(repo):
    page(repo, "run-club", sections=[{"type": "text", "heading": "Hi"}], published=False)
    edit(repo, "pages/home.json", lambda d: d.update(sections=[
        {"type": "button", "label": "Join the run club", "link": "/run-club"},
        {"type": "photo-text", "image": TALL, "alt": "A", "heading": "Saturdays", "text": "[Join](/run-club/) us.",
         "button_label": "Join", "button_link": "/run-club#when"},
        {"type": "button", "label": "Gift cards", "link": "/gift-cards"},       # the site's own draft
    ]))
    edit(repo, "announcement.json", lambda d: d.update(enabled=True, message="Run with us", link_label="Join",
                                                        link_url="/run-club"))
    edit(repo, "links.json", lambda d: d["buttons"].append({"label": "Run club", "url": "/run-club"}))
    assert not errors(repo)
    notes = problems(repo, message="which is switched off")
    assert {p["field"] for p in notes} >= {"More sections → Section 1 (Button) → Link",
                                           "More sections → Section 2 (Photo and text) → Text",
                                           "More sections → Section 2 (Photo and text) → Button link",
                                           "More sections → Section 3 (Button) → Link", "Link",
                                           "Button 5 (“Run club”) → Link"}
    assert any("your page “Run club”" in p["message"] for p in notes)
    assert any("the Gift Cards page" in p["message"] for p in notes)
    s = built(site(repo), "blocks/home_2")
    out = s.render_all()
    for key in ("home", "links"):
        assert 'href="/run-club' not in out[key], key
    assert "Join the run club" not in out["home"] and ">Gift cards<" not in out["home"]
    assert "<p>Join us.</p>" in out["home"]                         # the link's words stay, as text
    assert 'class="ann__msg">Run with us</p>' in out["home"]
    # switched back on: everything comes back by itself
    edit(repo, "custom-pages/run-club.json", lambda d: d.update(published=True))
    out = built(site(repo), "blocks/home_2").render_all()
    assert '<a class="btn btn--sage" href="/run-club">Join the run club</a>' in out["home"]
    assert 'href="/run-club/">Join</a>' in out["home"] and 'href="/run-club">Run club</a>' in out["links"]


def test_links_in_drafts_are_only_notes(repo):
    (repo / "content" / "specials" / "later.json").write_text(json.dumps(
        {"name": "Later", "description": "See [this](/nope).", "published": False}))
    (p,) = problems(repo, where="Special: Later")
    assert p["level"] == "warning" and p.get("draft") and "/nope isn’t a page" in p["message"]


def test_the_seed_links_all_go_somewhere():
    found = [p for p in V.validate(seed_root(), today=TODAY) if "isn’t a page on the website" in p["message"]
             or "which is switched off" in p["message"]]
    assert not found, found


# ---------------------------------------------------------------------------
# Instagram: a post the grid would never show
# ---------------------------------------------------------------------------
NEW_POST = {"image": "src-img/albums/04-the-regulars/04.jpg", "post_url": "https://www.instagram.com/p/DfAbCdEfGhI/",
            "alt": "A new post"}


def test_a_hand_picked_post_past_the_number_shown_is_an_error(repo):
    edit(repo, "instagram.json", lambda d: d["curated"].append(NEW_POST))      # "Add an item": at the end
    (e,) = [p for p in errors(repo) if p["where"] == "Instagram"]
    assert e["field"] == "Post 5" and "the grid shows the first 4 posts" in e["message"]
    assert "Drag this post up" in e["message"] and "set “Number of posts” to 5" in e["message"]
    # dragged to the top (the old fourth now off the grid): that one is the error
    edit(repo, "instagram.json", lambda d: d.update(curated=[d["curated"][-1], *d["curated"][:-1]]))
    assert [p["field"] for p in errors(repo) if p["where"] == "Instagram"] == ["Post 5"]
    edit(repo, "instagram.json", lambda d: d.update(count=5))
    assert not errors(repo)


@pytest.mark.parametrize("change", [{"enabled": False}, {"mode": "auto", "behold_feed_url": "https://feeds.behold.so/abc"}])
def test_extra_posts_are_fine_when_the_grid_doesnt_show_them(repo, change):
    """Section off, or automatic posts (the hand-picked ones are the backup)."""
    edit(repo, "instagram.json", lambda d: (d["curated"].append(NEW_POST), d.update(change)))
    assert not [p for p in errors(repo) if p["where"] == "Instagram"]


# ---------------------------------------------------------------------------
# A page's web address: taken already, or changed after the first Save
# ---------------------------------------------------------------------------
def test_a_page_saved_under_a_taken_address(repo):
    """Pages CMS doesn't refuse a file name that exists: it saves the new
    page as run-club-1.json. The page is there, and the note says so."""
    page(repo, "run-club", title="Run Club", published=False)
    d = repo / "content" / "custom-pages"
    (d / "run-club-1.json").write_text(json.dumps({"title": "Run Club (spring)", "address": "run-club",
                                                   "intro": "Back for spring."}))
    assert not errors(repo)
    (w,) = problems(repo, where="Your page: Run Club (spring)", field="Web address")
    assert w["level"] == "warning"
    assert ("Another of your pages (“Run Club”, switched off) already has the web address /run-club, so the editor "
            "saved this one at /run-club-1") in w["message"]
    assert "change “Web address” to run-club-1" in w["message"]
    out = site(repo).render_all()
    assert out["custom/run-club-1"] is not None and out["custom/run-club"] is None


def cms_entry(name):
    """An entry of .pages.yml by name, sidebar groups looked into."""
    def walk(items):
        for it in items:
            if it.get("type") == "group":
                yield from walk(it["items"])
            else:
                yield it
    return next(e for e in walk(yaml.safe_load((ROOT / ".pages.yml").read_text())["content"]) if e["name"] == name)


def test_the_web_address_help_says_it_must_be_new():
    (f,) = [x for x in cms_entry("custom-pages")["fields"] if x["name"] == "address"]
    assert "not one your other pages use" in f["description"] and "Fixed at the first Save" in f["description"]


# ---------------------------------------------------------------------------
# Sections and pages
# ---------------------------------------------------------------------------
def test_an_empty_text_section_is_left_out(repo):
    edit(repo, "pages/story.json", lambda d: d.update(sections=[{"type": "text"}, {"type": "quote", "quote": "Hi"}]))
    assert not errors(repo)
    html = site(repo).render("story")
    assert "more-text" not in html and "<p>“Hi”</p>" in html
    assert 'data-edit-label="Edit section 2 (quote) under More sections"' in html      # still numbered as in the CMS


@pytest.mark.parametrize("key", ["story", "how", "what"])
def test_sections_come_before_the_closing_words(repo, key):
    edit(repo, f"pages/{key}.json", lambda d: d.update(sections=[{"type": "quote", "quote": "Hi"}]))
    html = site(repo).render(key)
    assert html.index('<div class="more more--gap more--before-close">') < html.index('<section class="story-close"')
    assert html.index("</section>", html.index('<section class="story-close"')) > html.rindex("more-quote")


def test_a_page_of_her_own_shares_its_own_photo(repo):
    page(repo, "run-club", photo={"image": WIDE, "alt": "Runners"})
    page(repo, "plain")
    s = built(site(repo), "custom/run-club_top")
    assert ('<meta property="og:image" content="https://layerssuperfoodbar.com/assets/img/custom/run-club_top-1200.jpg">'
            in s.render("custom/run-club"))
    assert 'content="https://layerssuperfoodbar.com/assets/img/home/hero-' in s.render("custom/plain")


def test_a_new_special_keeps_the_limited_time_label(repo):
    (repo / "content" / "specials" / "golden-hour.json").write_text(json.dumps({"name": "Golden Hour"}))
    edit(repo, "specials/phi-velvet.json", lambda d: d.update(published=False))
    html = site(repo).render("home")
    assert '<p class="eyebrow special__badge">Limited time</p>' in html and "Golden Hour" in html
    edit(repo, "specials/golden-hour.json", lambda d: d.update(badge="New"))
    assert '<p class="eyebrow special__badge">New</p>' in site(repo).render("home")


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------
def test_a_time_with_a_stray_space_is_fine(repo):
    edit(repo, "hours.json", lambda d: d["weekly"]["saturday"].update(close="17:00 "))
    assert not errors(repo)
    s = site(repo)
    assert s.weekly["saturday"]["close"] == "17:00" and "Sat" in s.render("visit")


# ---------------------------------------------------------------------------
# The Edit buttons and /edit
# ---------------------------------------------------------------------------
def test_entry_links_have_no_file_extension():
    """Pages CMS's proxy skips any address ending in ".<letters>" (it takes
    it for a file), so after signing in she'd land on the Projects page.
    Every editor link avoids that; the app still opens the same file."""
    for target in ("specials/phi-velvet", "events/2026-11-07-run", "albums/community", "custom-pages/run-club",
                   "pages/home", "hours", "albums", "new:custom-pages"):
        url = render.editor_link(target)
        path = urllib.parse.urlsplit(url).path
        assert not re.search(r"\.[^/]+$", path), url             # Pages CMS v2.1.8 proxy.ts isStaticAsset
        if "/edit/" in path:
            assert urllib.parse.unquote(path.rsplit("/", 1)[1]) == f"content/{target}.json"


def test_edit_lists_what_is_worth_a_look(repo):
    page(repo, "run-club", title="Saturday Morning Run Club Berkeley", show_in="menu")
    s = site(repo)
    s.notes = V.split_problems(V.validate(repo, today=TODAY))[1]
    html = s.render("edit")
    assert "Worth a look</h2>" in html and "stop the website updating" in html
    assert "<strong>Your page: Saturday Morning Run Club Berkeley</strong> › Name in the menu" in html
    assert f'href="{render.editor_link("custom-pages/run-club")}" target="_blank" rel="noopener">Open it in the editor' in html
    assert "<strong>Page: Catering</strong> › Google and shared links → Google description" in html   # the seed's own
    assert html.index("What would you like to change?") < html.index("Worth a look") < html.index(">Help<")
    # only on /edit, and never a note on a draft
    assert "Worth a look" not in s.render("home")
    assert not [n for n in s.notes if n.get("draft")]


def test_the_build_hands_its_warnings_to_edit():
    src = (ROOT / "tools" / "build.py").read_text()
    pages = src[src.index("def pages():"):src.index("render.write_pages(")]
    assert pages.index("site.notes = validate_content.split_problems(problems)[1]") < pages.index("render_all()")


def test_the_editing_bar_comes_early_for_the_keyboard():
    js = (ROOT / "public" / "assets" / "js" / "main.js").read_text()
    bar = js[js.index("function addEditBar()"):js.index("function initStaffMode()")]
    assert "body.insertBefore(bar, skip ? skip.nextSibling : body.firstChild)" in bar and "appendChild(bar)" not in bar
    # on a phone the short words still say what they do
    assert "Open<span class=\"edit-bar__long\"> the</span>' +\n        ' editor</span>" in bar
    assert "Hide<span class=\"edit-bar__long\"> edit</span> buttons" in bar


def test_photo_help_gives_the_whole_address_and_the_minimum_size():
    raw = (ROOT / ".pages.yml").read_text()
    assert "at /photo-prep." not in raw
    assert raw.count("Shrink it first at layerssuperfoodbar.com/photo-prep.") >= 10
    for spot in ("a tall (portrait) photo works best, at least 800 pixels wide", "shown as a small square, at least 800",
                 "shown square, at least 800 pixels wide", "At least 800 pixels wide. Drag photos",
                 "Shown square, at least 800 pixels wide. The grid shows the first posts in this list"):
        assert spot in raw, spot
