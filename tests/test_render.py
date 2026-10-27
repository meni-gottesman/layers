"""Page rendering (tools/render.py + templates/): every page renders, content
is escaped, and a CMS save (which drops empty values) changes nothing. Seed
assertions read the frozen seed (tests/fixtures/seed), never the live content."""
import json
import re

import pytest

import content as C
import render
from conftest import TODAY, edit, seed_root


def site(root=None, **kw):
    return render.Site(root=root or seed_root(), today=TODAY, **kw)


def test_every_published_page_renders():
    out = site().render_all()
    published = [k for k, v in out.items() if v is not None]
    assert set(published) == {"home", "menu", "story", "how", "what", "day", "catering", "faq", "visit", "404",
                              "links", "photo-prep", "brand"}
    for k in published:
        assert out[k].startswith("<!DOCTYPE html>") and out[k].rstrip().endswith("</html>"), k


def test_drafts_render_too():
    """Unpublished pages still have to render, so publishing one can't break the build."""
    s = site()
    s.manifest = {**s.manifest, "gift/hero": {"widths": [480, 720], "aspect": 0.8},
                  "loyalty/side": {"widths": [480], "aspect": 1.0}}
    for key in ("gift-cards", "loyalty", "order"):
        assert "</html>" in s.render(key)




def test_content_is_escaped(repo):
    edit(repo, "pages/home.json", lambda d: d["hero"].update(line='<script>alert("x")</script>'))
    edit(repo, "faq.json", lambda d: d["items"][0].update(answer="[x](javascript:alert(1)) <b>hi</b>"))
    out = render.Site(root=repo, today=TODAY).render_all()
    assert "<script>alert" not in out["home"] and "&lt;script&gt;" in out["home"]
    assert "javascript:" not in out["faq"] and "<b>hi" not in out["faq"]


def test_business_details_flow_into_the_chrome(repo):
    def f(d):
        d["business"]["phone"] = "(510) 555-0123"
        d["social"]["tiktok_url"] = "https://www.tiktok.com/@layers"
        d["footer_tagline"] = "New tagline"
    edit(repo, "site.json", f)
    html = render.Site(root=repo, today=TODAY).render("visit")
    assert 'href="tel:5105550123"' in html and "New tagline" in html
    assert 'href="https://www.tiktok.com/@layers"' in html
    home = render.Site(root=repo, today=TODAY).render("home")
    ld = json.loads(home.split('<script type="application/ld+json">')[1].split("</script>")[0])
    assert ld["telephone"] == "(510) 555-0123" and "https://www.tiktok.com/@layers" in ld["sameAs"]


def test_hours_change_everywhere(repo):
    edit(repo, "hours.json", lambda d: d["weekly"]["sunday"].update(closed=True, open="", close=""))
    s = render.Site(root=repo, today=TODAY)
    for key in ("home", "visit", "faq"):
        assert "Sun Closed" in s.render(key) or "Sunday</th><td>Closed" in s.render(key), key


def test_square_links_in_text_say_so():
    faq = site().render("faq")
    assert ('<a href="https://layerssuperfoodbar.square.site" target="_blank" rel="noopener">online'
            '<span class="sr-only"> (opens Square in a new tab)</span></a>') in faq


def test_jsonld_cannot_close_its_script(repo):
    edit(repo, "site.json", lambda d: d["business"].update(name="Layers</script><script>alert(1)"))
    home = render.Site(root=repo, today=TODAY).render("home")
    assert "</script><script>alert(1)" not in home


def _scripts(html):
    """[(type, text)] of every <script> element, split the way a browser's
    tokenizer would at the FIRST "</script" (so a payload that ends early shows)."""
    out, rest = [], html
    while "<script" in rest:
        head, rest = rest.split("<script", 1)[1].split(">", 1)
        body, rest = rest.split("</script", 1)
        out.append((re.search(r'type="([^"]+)"', head).group(1) if 'type="' in head else "", body))
    return out


def test_hostile_text_cannot_change_how_the_page_parses(repo):
    """'<!--<script>' inside a <script> puts the HTML parser into its
    "double-escaped" state, where the next </script> no longer ends the
    script and the rest of the page is swallowed. The albums data and the
    schema.org JSON are written with <, > and & escaped, so they parse back
    to exactly the content."""
    evil = "Runners <!--<script> after the run & </script> <b>"
    # data/albums.json is what tools/build-albums.py writes from the album's alt texts
    p = repo / "data" / "albums.json"
    albums = json.loads(p.read_text())
    albums[1]["photos"][0]["alt"] = evil
    p.write_text(json.dumps(albums))
    edit(repo, "site.json", lambda d: d["business"].update(name="Layers <!--<script>"))
    s = render.Site(root=repo, today=TODAY)
    day, home = s.render("day"), s.render("home")
    for html, kind in ((day, "application/json"), (home, "application/ld+json")):
        payloads = [body for t, body in _scripts(html) if t == kind]
        assert payloads and all("<" not in body and ">" not in body for body in payloads), kind
    data = json.loads(next(b for t, b in _scripts(day) if t == "application/json"))
    assert data[1]["photos"][0]["alt"] == evil          # same text once parsed
    ld = json.loads(next(b for t, b in _scripts(home) if t == "application/ld+json"))
    assert ld["name"] == "Layers <!--<script>"
    assert day.rstrip().endswith("</html>") and '<script src="/assets/js/main.js" defer></script>' in day


def test_cms_save_leaves_every_page_unchanged(repo):
    """Pages CMS drops empty values ("", [], {}) when it saves (CMS_SPEC §8.2):
    rewrite every content file that way and the site must not change."""
    before = site().render_all()
    for p in (repo / "content").rglob("*.json"):
        p.write_text(C.dump_cms_json(json.loads(p.read_text())))
    after = render.Site(root=repo, today=TODAY).render_all()
    assert after == before


# ---------------------------------------------------------------------------
# The content features (CMS_SPEC §2.2–2.7, §9)
# ---------------------------------------------------------------------------
def _section(html, cls):
    """The <section …class="… cls …"> element's markup (up to its </section>)."""
    start = html.index(f'class="ed {cls}"') if f'class="ed {cls}"' in html else html.index(cls)
    return html[html.rindex("<section", 0, start):html.index("</section>", start)]


def test_instagram_grid_before_the_visit_band():
    home = site().render("home")
    ig = _section(home, "ed--instagram")
    assert home.index("ed--instagram") < home.index("ed--visit") and home.index("ed--community") < home.index("ed--instagram")
    assert '<ul class="ig__grid" role="list"' in ig and ig.count('class="ig__item"') == 4
    assert 'href="https://www.instagram.com/p/DeFwOJmj8zc/" target="_blank" rel="noopener"' in ig
    assert "Follow along" in ig and 'href="https://www.instagram.com/layerssuperfoodbar/"' in ig
    assert "/assets/img/instagram/1-480.webp" in ig and "smiling tricolor dog" in ig   # alt from the content
    assert "(opens Instagram in a new tab)" in ig
    assert "behold" not in home.lower() and "cdn" not in ig      # nothing fetched by visitors


def test_instagram_without_posts_shows_only_the_follow_link(repo):
    (repo / "data" / "instagram.json").unlink()
    edit(repo, "instagram.json", lambda d: d.update(curated=[]))
    ig = _section(render.Site(root=repo, today=TODAY).render("home"), "ed--instagram")
    assert "Follow @layerssuperfoodbar" in ig and "ig__grid" not in ig


def test_instagram_switched_off_or_without_handle_and_posts(repo):
    (repo / "data" / "instagram.json").unlink()
    edit(repo, "instagram.json", lambda d: d.update(enabled=False))
    assert "ed--instagram" not in render.Site(root=repo, today=TODAY).render("home")
    edit(repo, "instagram.json", lambda d: d.update(enabled=True, curated=[]))
    edit(repo, "site.json", lambda d: d["social"].update(instagram_handle=""))
    assert "ed--instagram" not in render.Site(root=repo, today=TODAY).render("home")


def test_specials_band_and_menu_card():
    s = site()
    home, menu = s.render("home"), s.render("menu")
    band = _section(home, "ed--specials")
    assert home.index("ed--products") < home.index("ed--specials") < home.index("ed--community")
    assert "Phi Velvet" in band and "Made with Cal Alpha Phi" in band and "Limited time" in band
    assert "In store for a limited time." in band and "btn" not in band       # order button "none" (not on Square)
    assert "/assets/img/specials/phi-velvet-480.webp" in band and "Greek yogurt" in band
    assert menu.index("menu-specials") < menu.index('data-chip-rail') and "Phi Velvet" in menu


def test_specials_follow_their_switches_and_dates(repo):
    edit(repo, "specials/phi-velvet.json", lambda d: d.update(show_on_home=False))
    s = render.Site(root=repo, today=TODAY)
    assert "ed--specials" not in s.render("home") and "Phi Velvet" in s.render("menu")
    edit(repo, "specials/phi-velvet.json", lambda d: d.update(show_on_home=True, ends="2026-10-26"))
    s = render.Site(root=repo, today=TODAY)
    assert "Phi Velvet" not in s.render("home") and "Phi Velvet" not in s.render("menu")


def test_events_coming_up(repo):
    ev = repo / "content" / "events"
    ev.mkdir(exist_ok=True)
    (ev / "late.json").write_text(json.dumps({"title": "Pop-up", "date": "2026-11-12", "location": "Sproul"}))
    (ev / "soon.json").write_text(json.dumps({"title": "Run club", "date": "2026-11-07", "start_time": "08:30",
                                              "end_time": "10:00", "partner": "She Runs Berkeley"}))
    (ev / "past.json").write_text(json.dumps({"title": "Old news", "date": "2026-10-01"}))
    (ev / "draft.json").write_text(json.dumps({"title": "Secret", "date": "2026-11-20", "published": False}))
    s = render.Site(root=repo, today=TODAY)
    home = s.render("home")
    assert "Coming up" in home and home.index("Coming up") < home.index("See every album")
    assert home.index("Run club") < home.index("Pop-up")
    assert '<time datetime="2026-11-07T08:30">Sat, Nov 7 · 8:30am–10am</time>' in home
    assert "Old news" not in home and "Secret" not in home
    assert "Run club" in s.render("links")


def test_no_events_no_list():
    assert "Coming up" not in site().render("home")


def test_announcement_bar(repo):
    edit(repo, "announcement.json", lambda d: d.update(enabled=True, message="Closed Thursday for Thanksgiving",
                                                        link_label="Hours", link_url="/visit", tone="butter",
                                                        starts="2026-10-20", ends="2026-11-27"))
    s = render.Site(root=repo, today=TODAY)
    for key in ("home", "menu", "visit"):
        html = s.render(key)
        assert '<body class="' in html and ' has-ann"' in html, key
        assert 'class="ann ann--butter"' in html and 'href="/visit">Hours</a>' in html
        assert html.index('id="ann"') < html.index('id="site-header"')
    edit(repo, "announcement.json", lambda d: d.update(ends="2026-10-26"))     # ended yesterday
    assert 'id="ann"' not in render.Site(root=repo, today=TODAY).render("home")


def test_no_announcement_no_markup():
    home = site().render("home")
    assert 'id="ann"' not in home and "has-ann" not in home


def test_special_hours_everywhere(repo):
    edit(repo, "hours.json", lambda d: d.update(special=[
        {"date": "2026-11-26", "label": "Thanksgiving", "closed": True},
        {"date": "2026-12-24", "label": "Christmas Eve", "closed": False, "open": "10:00", "close": "14:00"},
        {"date": "2027-06-01", "label": "Too far ahead", "closed": True},
        {"date": "2026-10-01", "label": "Past", "closed": True}]))
    s = render.Site(root=repo, today=TODAY)
    home, visit = s.render("home"), s.render("visit")
    meta = json.loads(re.search(r"<meta name=\"layers-hours\" content='([^']*)'>", home).group(1))
    assert meta["special"] == {"2026-11-26": None, "2026-12-24": [600, 840]}
    assert meta["1"] == [540, 1080]                                   # the weekly hours are still there
    ld = json.loads(home.split('<script type="application/ld+json">')[1].split("</script>")[0])
    assert ld["specialOpeningHoursSpecification"] == [
        {"@type": "OpeningHoursSpecification", "validFrom": "2026-11-26", "validThrough": "2026-11-26",
         "opens": "00:00", "closes": "00:00"},
        {"@type": "OpeningHoursSpecification", "validFrom": "2026-12-24", "validThrough": "2026-12-24",
         "opens": "10:00", "closes": "14:00"}]
    assert "Special hours" in visit and "Thu, Nov 26" in visit and "Thanksgiving" in visit
    assert "10am–2pm" in visit and "Too far ahead" not in visit and "Past" not in visit


def test_without_special_hours_the_payload_is_unchanged():
    home = site().render("home")
    assert "<meta name=\"layers-hours\" content='{\"1\":[540,1080],\"2\":[540,1080],\"3\":[540,1080]," in home
    assert "special" not in re.search(r"<meta name=\"layers-hours\" content='([^']*)'>", home).group(1)
    assert "specialOpeningHoursSpecification" not in home


def test_links_page():
    s = site()
    out = s.render_all()
    links = out["links"]
    assert '<meta name="robots" content="noindex">' in links and 'rel="canonical"' not in links
    assert 'class="btn btn--sage btn--block" href="https://layerssuperfoodbar.square.site" target="_blank"' in links
    assert 'href="/menu">See the menu</a>' in links
    assert 'id="m-drawer"' not in links and "footer__grid" not in links      # light chrome
    assert "Phi Velvet" in links                                                # active specials
    for key, html in out.items():
        if html and key != "links":
            assert 'href="/links"' not in html, key                           # not in any navigation


def test_links_page_off_and_out_of_the_sitemap(repo, tmp_path):
    s = site()
    out = s.render_all()
    _, urls = render.write_pages(s, out, tmp_path / "out")
    assert not any(u.endswith("/links") for u in urls) and (tmp_path / "out" / "links" / "index.html").exists()
    edit(repo, "links.json", lambda d: d.update(enabled=False))
    assert render.Site(root=repo, today=TODAY).render_all()["links"] is None


def test_hidden_menu_items_are_named_for_the_live_menu(repo):
    import conftest
    edit(repo, "menu.json", lambda d: [it.update(hidden=True) for it in d["items"] if it["square_name"] == "Mango Coco"])
    conftest.load_tool(repo / "tools" / "sync-menu-from-store.py", "sync_hidden_render").sync(offline=True)
    menu = render.Site(root=repo, today=TODAY).render("menu")
    assert 'data-hidden-ids="VLK7BDLF3CHWWWUKENU3PK4C"' in menu and "Mango Coco" not in menu
    assert "data-hidden-ids" not in site().render("menu")                   # none hidden: unchanged markup


# ---------------------------------------------------------------------------
# Review fixes (Oct 27 2026)
# ---------------------------------------------------------------------------
def test_line_breaks_typed_in_a_multi_line_box_are_kept(repo):
    edit(repo, "pages/home.json", lambda d: d["community"].update(text="First line <b>\nSecond line"))
    home = render.Site(root=repo, today=TODAY).render("home")
    assert '<p class="ed-text">First line &lt;b&gt;<br>\nSecond line</p>' in home
    assert render.line_breaks("No break & more") == "No break &amp; more"      # as {{ text }} would be


def test_analytics_only_on_the_live_site(repo):
    """The same build is the GitHub Pages preview and runs on localhost: the
    beacon is loaded by a script that checks the hostname first."""
    edit(repo, "site.json", lambda d: d.setdefault("analytics", {}).update(cloudflare_web_analytics_token="ab" * 16))
    home = render.Site(root=repo, today=TODAY).render("home")
    loader = re.search(r"<script>\(function\(\)\{var h=(\[[^\]]*\]);if\(h\.indexOf\(location\.hostname\)<0\)return;"
                       r".*?</script>", home, re.S)
    assert loader and json.loads(loader.group(1)) == ["layerssuperfoodbar.com", "www.layerssuperfoodbar.com"]
    beacon = re.search(r"setAttribute\('data-cf-beacon',(\"[^)]*\")\)", loader.group(0)).group(1)
    assert json.loads(json.loads(beacon)) == {"token": "ab" * 16}          # a JS string holding the JSON
    assert '<script defer src="https://static.cloudflareinsights.com' not in home      # never loaded directly
    assert "cloudflareinsights" not in site().render("home")                            # no token: nothing


def test_staff_pages_never_show_the_announcement(repo):
    edit(repo, "announcement.json", lambda d: d.update(enabled=True, message="Closed Thursday"))
    out = render.Site(root=repo, today=TODAY).render_all()
    assert 'id="ann"' in out["home"] and 'id="ann"' in out["links"]
    for key in ("photo-prep", "brand"):
        assert 'id="ann"' not in out[key] and "has-ann" not in out[key], key


def test_pages_without_a_description_use_the_default(repo):
    out = site().render_all()
    default = C.load_all(seed_root())["site"]["seo"]["default_description"]
    assert f'<meta name="description" content="{default}">' in out["links"]
    assert f'<meta name="description" content="{default}">' not in out["home"]          # its own


def test_story_wide_photos_follow_fewer_chapters(repo):
    edit(repo, "pages/story.json", lambda d: d.update(chapters=d["chapters"][:1]))
    story = render.Site(root=repo, today=TODAY).render("story")
    assert story.count("/assets/img/story/philosophy-") > 0 and story.count("/assets/img/story/journey-") > 0
    assert story.index("story/philosophy") < story.index("story/journey") < story.index('class="pillars"')
    full = site().render("story")
    assert full.index('id="ch-2"') < full.index("story/philosophy") < full.index('id="ch-3"')   # seed: unchanged
    assert full.index('id="ch-4"') < full.index("story/journey") < full.index('id="ch-5"')


def test_an_event_without_a_photo_keeps_the_column(repo):
    ev = repo / "content" / "events"
    ev.mkdir(exist_ok=True)
    (ev / "a.json").write_text(json.dumps({"title": "With photo", "date": "2026-11-07",
                                           "image": "src-img/albums/02-run-clubs/14.jpg", "image_alt": "Runners"}))
    (ev / "b.json").write_text(json.dumps({"title": "Without", "date": "2026-11-08"}))
    s = render.Site(root=repo, today=TODAY)
    s.manifest = {**s.manifest, "events/a": {"widths": [240, 480], "aspect": 1.0}}
    home = s.render("home")
    without = home[home.index(">Without<") - 400:home.index(">Without<")]
    assert '<span class="event__media event__media--none" aria-hidden="true"></span>' in without
    (ev / "a.json").unlink()                                       # no photos at all: no empty column
    assert "event__media" not in render.Site(root=repo, today=TODAY).render("home")


@pytest.mark.parametrize("n,cols,sizes", [(1, 3, "(max-width: 720px) 50vw, 33vw"), (2, 3, "(max-width: 720px) 50vw, 33vw"),
                                          (3, 3, "(max-width: 720px) 33vw, 33vw"),
                                          (4, 4, "(max-width: 720px) 50vw, 25vw")])
def test_instagram_tiles_never_blow_up(repo, n, cols, sizes):
    (repo / "data" / "instagram.json").unlink()
    edit(repo, "instagram.json", lambda d: d.update(count=n))
    s = render.Site(root=repo, today=TODAY)
    s.manifest = {**s.manifest, **{f"instagram/{i}": {"widths": [480, 720, 960], "aspect": 1.0} for i in range(1, 5)}}
    ig = _section(s.render("home"), "ed--instagram")
    assert f"--ig-cols:{cols};" in ig and ig.count('class="ig__item"') == n
    assert f'sizes="{sizes}"' in ig
