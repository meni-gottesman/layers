"""Content validation (tools/validate_content.py): seed content passes, and
broken content produces friendly, CMS-labelled messages."""
import json

import pytest

import content as C
import validate_content as V
from conftest import FIXTURE, TODAY, edit


def run(repo):
    return V.validate(repo, today=TODAY)


def errors(problems):
    return [p for p in problems if p["level"] == "error"]


def find(problems, **match):
    hits = [p for p in problems if all(m in p[k] for k, m in match.items())]
    assert hits, f"no problem matching {match} in:\n{V.format_problems(problems)}"
    return hits[0]


def test_seed_content_has_no_errors(repo):
    assert errors(run(repo)) == []


def test_every_problem_has_the_reported_shape(repo):
    edit(repo, "hours.json", lambda d: d["weekly"]["monday"].update(open="nine"))
    for p in run(repo):
        assert set(p) >= {"level", "where", "field", "message"}
        assert p["level"] in ("error", "warning")


def test_bad_time(repo):
    edit(repo, "hours.json", lambda d: d["weekly"]["saturday"].update(open="9am"))
    p = find(errors(run(repo)), where="Opening hours", field="Saturday → Opens")
    assert p["field"] == "Saturday → Opens"            # the CMS's own labels, nothing else
    assert "24-hour" in p["message"] and "9am" in p["message"]


def test_closing_before_opening(repo):
    edit(repo, "hours.json", lambda d: d["weekly"]["saturday"].update(open="18:00", close="09:00"))
    p = find(errors(run(repo)), where="Opening hours", field="Saturday → Opens")
    assert "Saturday’s opening time (18:00) is not before its closing time (09:00)" in p["message"]


def test_closed_day_needs_no_times(repo):
    edit(repo, "hours.json", lambda d: d["weekly"]["sunday"].update(closed=True, open="", close=""))
    assert errors(run(repo)) == []


def test_special_hours_checks(repo):
    edit(repo, "hours.json", lambda d: d.update(special=[
        {"date": "2026-11-26", "label": "Thanksgiving", "closed": True},
        {"date": "2026-11-26", "label": "Again", "closed": True},
        {"date": "2026-13-01", "label": "Bad", "closed": True},
        {"date": "2026-12-24", "label": "Short day", "closed": False, "open": "10:00", "close": ""}]))
    errs = errors(run(repo))
    # each item: its number and the text the CMS shows on it ("{date} {label}")
    find(errs, field="Special hours 2 (“2026-11-26 Again”) → Date", message="listed twice")
    find(errs, field="Special hours 3 (“2026-13-01 Bad”) → Date", message="isn’t a date")
    find(errs, field="Special hours 4 (“2026-12-24 Short day”) → Opens", message="both an opening and a closing time")


def test_missing_alt_text(repo):
    edit(repo, "pages/home.json", lambda d: d["photos"]["fresh_1"].update(alt=""))
    p = find(errors(run(repo)), where="Page: Home", field="Photos → Made fresh — photo 1 → Photo description")
    assert "needs a short description" in p["message"] and "can’t see it" in p["message"]


def test_missing_alt_on_a_community_square(repo):
    edit(repo, "pages/home.json", lambda d: d["community"]["squares"][2]["photo"].pop("alt"))
    p = find(errors(run(repo)), field="Community → Square photo 3 (“", message="needs a short description")
    assert p["field"].endswith("”) → Photo → Photo description")


def test_long_announcement(repo):
    edit(repo, "announcement.json", lambda d: d.update(enabled=True, message="x" * 300))
    p = find(errors(run(repo)), where="Announcement bar", field="Message")
    assert "300 characters long; the limit is 110" in p["message"]


def test_disabled_content_errors_are_only_warnings(repo):
    edit(repo, "announcement.json", lambda d: d.update(enabled=False, message="x" * 300))
    probs = run(repo)
    assert errors(probs) == []
    assert "won’t stop the update" in find(probs, where="Announcement bar")["message"]


def test_missing_image(repo):
    edit(repo, "pages/visit.json", lambda d: d["photos"]["hero"].update(image="src-img/uploads/nope.jpg"))
    p = find(errors(run(repo)), where="Page: Visit", field="Photos → Main photo → Photo")
    assert "can’t be found" in p["message"] and "nope.jpg" in p["message"]


def test_image_outside_src_img(repo):
    edit(repo, "pages/visit.json", lambda d: d["photos"]["hero"].update(image="../etc/passwd"))
    find(errors(run(repo)), field="Photos → Main photo → Photo", message="photo folder")


def test_leading_slash_image_path_is_accepted(repo):
    edit(repo, "pages/visit.json", lambda d: d["photos"]["hero"].update(
        image="/src-img/originals/shop-interior-pendants.jpg"))
    assert errors(run(repo)) == []


def test_small_upload_is_rejected_with_sizes(repo):
    from PIL import Image
    Image.new("RGB", (700, 500), "white").save(repo / "src-img" / "uploads" / "tiny.jpg")
    edit(repo, "pages/home.json", lambda d: d["photos"]["hero"].update(image="src-img/uploads/tiny.jpg"))
    edit(repo, "pages/what.json", lambda d: d["photos"]["hero"].update(image="src-img/uploads/tiny.jpg"))
    errs = errors(run(repo))
    full = find(errs, where="Page: Home", field="Top photo → Photo")["message"]
    assert "700×500 pixels" in full and "at least 1200 pixels" in full
    half = find(errs, where="Page: What We Make")["message"]
    assert "at least 800 pixels" in half


def test_big_enough_upload_passes(repo):
    from PIL import Image
    Image.new("RGB", (1600, 1000), "white").save(repo / "src-img" / "uploads" / "big.jpg")
    edit(repo, "pages/home.json", lambda d: d["photos"]["hero"].update(image="src-img/uploads/big.jpg"))
    assert errors(run(repo)) == []


def test_seo_lengths_are_warnings(repo):
    edit(repo, "pages/how.json", lambda d: d["seo"].update(title="T" * 70))
    probs = run(repo)
    assert errors(probs) == []
    find(probs, level="warning", where="Page: How We Make It", field="Google and shared links → Google title", message="about 60")


def test_caption_limit(repo):
    edit(repo, "pages/home.json", lambda d: d["community"]["wide"].update(caption="c" * 81))
    find(errors(run(repo)), field="Community → Wide photo → Caption", message="limit is 80")


def test_links_must_be_https_or_site_paths(repo):
    edit(repo, "links.json", lambda d: d["buttons"].append({"label": "Bad", "url": "javascript:alert(1)"}))
    edit(repo, "announcement.json", lambda d: d.update(enabled=True, message="Hi", link_label="Go",
                                                        link_url="http://example.com"))
    errs = errors(run(repo))
    find(errs, where="Link in bio", field="Button 5 (“Bad”) → Link", message="isn’t a link the site can use")
    find(errs, where="Announcement bar", field="Link", message="secure https://")


def test_instagram_and_behold_urls(repo):
    def f(d):
        d["curated"][0]["post_url"] = "https://www.instagram.com/layerssuperfoodbar/"
        d["behold_feed_url"] = "https://behold.so/feed/123"
    edit(repo, "instagram.json", f)
    errs = errors(run(repo))
    find(errs, where="Instagram", field="Post 1 → Instagram post link", message="isn’t a link to an Instagram post")
    find(errs, where="Instagram", field="Behold feed link", message="https://feeds.behold.so/")


def test_reel_links_are_fine(repo):
    edit(repo, "instagram.json", lambda d: d["curated"][0].update(post_url="https://www.instagram.com/reel/AbC_12-x/"))
    assert errors(run(repo)) == []


def test_analytics_token(repo):
    edit(repo, "site.json", lambda d: d.setdefault("analytics", {}).update(cloudflare_web_analytics_token="abc"))
    find(errors(run(repo)), where="Business details", field="Analytics → Cloudflare Web Analytics token",
         message="32 letters and numbers")
    edit(repo, "site.json", lambda d: d.setdefault("analytics", {}).update(cloudflare_web_analytics_token="0123456789abcdef" * 2))
    assert errors(run(repo)) == []


def test_dates_in_specials_and_events(repo):
    edit(repo, "specials/phi-velvet.json", lambda d: d.update(starts="2026-11-10", ends="2026-11-01"))
    (repo / "content" / "events" / "run-club.json").write_text(json.dumps(
        {"title": "Run club", "date": "2026-11-08", "start_time": "09:00", "end_time": "08:00"}))
    errs = errors(run(repo))
    find(errs, where="Special: Phi Velvet", field="Last day shown", message="before the start date")
    find(errs, where="Event: Run club", field="End time", message="not after the start time")


def test_ended_special_is_a_warning(repo):
    edit(repo, "specials/phi-velvet.json", lambda d: d.update(ends="2026-10-01"))
    probs = run(repo)
    assert errors(probs) == []
    find(probs, level="warning", where="Special: Phi Velvet", message="no longer shows")


def test_bad_collection_file_name(repo):
    src = repo / "content" / "specials" / "phi-velvet.json"
    (repo / "content" / "specials" / "Phi Velvet 2.json").write_text(src.read_text())
    find(errors(run(repo)), message="can’t be used in a web address")


def test_menu_ids(repo):
    def f(d):
        d["items"].append(dict(d["items"][0]))                       # duplicate
        d["items"].append({"square_id": "GONE123", "square_name": "Old item"})
    edit(repo, "menu.json", f)
    probs = run(repo)
    find(errors(probs), where="Menu", message="listed twice")
    find(probs, level="warning", where="Menu", field="Old item", message="no longer lists")


def test_new_square_item_not_yet_listed_is_a_warning(repo):
    edit(repo, "menu.json", lambda d: d.update(items=d["items"][1:]))
    probs = run(repo)
    assert errors(probs) == []
    p = find(probs, level="warning", where="Menu", message="aren’t in this list")
    assert "Hide from the website" in p["message"] and "Undo my last change" in p["message"]


def test_invalid_json_is_explained(repo):
    (repo / "content" / "faq.json").write_text('{"items": [}')
    p = find(errors(run(repo)), where="FAQ")
    assert "isn’t valid JSON (line 1" in p["message"]


def test_missing_file(repo):
    (repo / "content" / "pages" / "story.json").unlink()
    find(errors(run(repo)), where="Page: The Layers Story", message="missing")


def test_unknown_keys_are_ignored(repo):
    edit(repo, "site.json", lambda d: d.update(_cms_meta={"x": 1}, extra="hello"))
    assert errors(run(repo)) == []


def test_wrong_type_is_explained(repo):
    edit(repo, "faq.json", lambda d: d.update(items="oops"))
    find(errors(run(repo)), where="FAQ", field="Questions", message="should be a list")


def test_unpublished_page_is_lenient(repo):
    # Gift Cards has no photo yet and is unpublished: a warning, not an error
    probs = run(repo)
    find(probs, level="warning", where="Page: Gift Cards", message="won’t stop the update")
    edit(repo, "pages/gift-cards.json", lambda d: d.update(published=True))
    find(errors(run(repo)), where="Page: Gift Cards", field="Photos → Main photo → Photo")


@pytest.mark.parametrize("rel", sorted(str(p.relative_to(FIXTURE / "content")) for p in (FIXTURE / "content").rglob("*.json")))
def test_cms_save_keeps_content_valid(repo, rel):
    """Pages CMS drops empty values when it saves; the defaults layer makes
    that harmless (CMS_SPEC §8.2)."""
    p = repo / "content" / rel
    p.write_text(C.dump_cms_json(json.loads(p.read_text())))
    assert errors(run(repo)) == []


def test_report_files(repo):
    probs = run(repo)
    V.write_report(repo, probs, "passed", steps=[{"name": "validate", "status": "ok"}])
    rep = json.loads((repo / "build-report.json").read_text())
    assert rep["status"] == "passed" and rep["errors"] == 0
    md = (repo / "build-report.md").read_text()
    assert md.startswith("# Website update: published")
    edit(repo, "hours.json", lambda d: d["weekly"]["monday"].update(open="9"))
    probs = run(repo)
    V.write_report(repo, probs, "failed")
    md = (repo / "build-report.md").read_text()
    assert md.startswith("# Website update didn’t publish") and "**Opening hours** › Monday → Opens" in md


# ---------------------------------------------------------------------------
# Placeholders, navigation, drafts in the report
# ---------------------------------------------------------------------------
def test_publishing_a_page_with_placeholder_text_is_blocked(repo):
    probs = run(repo)
    draft = find(probs, where="Page: Loyalty", field="How it works, in a few sentences")
    assert draft["level"] == "warning" and draft.get("draft") and "placeholder" in draft["message"]
    edit(repo, "pages/loyalty.json", lambda d: d.update(published=True))
    errs = errors(run(repo))
    p = find(errs, where="Page: Loyalty", field="How it works, in a few sentences", message="placeholder text")
    assert "client to supply" in p["message"]
    find(errs, where="Page: Loyalty", field="Step 1", message="placeholder text")


def test_markdown_links_are_not_placeholders(repo):
    edit(repo, "faq.json", lambda d: d["items"][0].update(answer="[See the menu](/menu)"))
    assert errors(run(repo)) == []


def test_a_published_page_nobody_links_to_is_flagged(repo):
    def ready(d):
        d.update(published=True, text="Collect a stamp with every bowl.", steps=["Buy a bowl", "Get a stamp"])
    edit(repo, "pages/loyalty.json", ready)
    probs = run(repo)
    assert errors(probs) == []
    p = find(probs, level="warning", where="Page: Loyalty", field="Published", message="no menu on the site links")
    assert "/loyalty" in p["message"] and not p.get("draft")


def test_report_keeps_drafts_apart(repo):
    probs = run(repo)
    V.write_report(repo, probs, "passed")
    md = (repo / "build-report.md").read_text()
    look = md.split("## Worth a look")[1].split("<details>")[0] if "## Worth a look" in md else ""
    assert "Gift Cards" not in look and "Loyalty" not in look
    assert "Not on the site — notes" in md and "Page: Gift Cards" in md.split("Not on the site — notes")[1]
    rep = json.loads((repo / "build-report.json").read_text())
    assert rep["drafts"] >= 2 and rep["warnings"] == len([p for p in probs if p["level"] == "warning"
                                                          and not p.get("draft")])


# ---------------------------------------------------------------------------
# Photo sizes: every photo that wasn't placed before the CMS, judged on its crop
# ---------------------------------------------------------------------------
def _photo(repo, folder, name, size):
    from PIL import Image
    d = repo / "src-img" / folder
    if d.is_symlink():                      # originals/albums/menu are the real folders: use a new one
        raise AssertionError("pick a folder that isn't a symlink")
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(d / name)
    return f"src-img/{folder}/{name}"


def test_small_photo_outside_uploads_is_checked_too(repo):
    path = _photo(repo, "new-shoot", "small.jpg", (700, 500))
    edit(repo, "pages/visit.json", lambda d: d["photos"]["hero"].update(image=path))
    p = find(errors(run(repo)), where="Page: Visit", field="Photos → Main photo → Photo")
    assert "700×500 pixels" in p["message"] and "at least 800 pixels" in p["message"]


def test_portrait_photo_in_a_wide_band_is_judged_on_its_crop(repo):
    """1000×1600 passes the long-edge rule but a 21:9 band crops it to 1000×429."""
    path = _photo(repo, "uploads", "tall.jpg", (1000, 1600))
    edit(repo, "pages/home.json", lambda d: d["photos"]["visit"].update(image=path))
    p = find(errors(run(repo)), where="Page: Home", field="Photos → Visit photo → Photo")
    assert "1000×1600 pixels" in p["message"] and "cropped to 1000×429" in p["message"]
    assert "at least 1200 pixels wide after cropping" in p["message"]


def test_big_portrait_photo_in_a_wide_band_gets_a_composition_warning(repo):
    path = _photo(repo, "uploads", "big-tall.jpg", (1333, 2000))
    edit(repo, "pages/home.json", lambda d: d["photos"]["visit"].update(image=path))
    probs = run(repo)
    assert errors(probs) == []
    p = find(probs, level="warning", where="Page: Home", field="Photos → Visit photo → Photo")
    assert "1333×571 of it shows" in p["message"] and "landscape" in p["message"]


def test_zoom_counts_in_the_crop(repo):
    path = _photo(repo, "uploads", "edge.jpg", (900, 900))            # square spot: 900 ≥ 800 …
    edit(repo, "pages/home.json", lambda d: d["photos"]["bowls"].update(image=path))
    assert errors(run(repo)) == []
    edit(repo, "pages/home.json", lambda d: d["photos"]["bowls"].update(zoom="more"))   # … 900 / 1.35 = 667
    p = find(errors(run(repo)), field="Photos → Bowls photo → Photo")
    assert "cropped to 667×667" in p["message"] and "Zoom to none" in p["message"]


def test_community_square_labels(repo):
    path = _photo(repo, "uploads", "sq.jpg", (1000, 700))             # 700×700 crop < 800
    edit(repo, "pages/home.json", lambda d: d["community"]["squares"][1]["photo"].update(image=path))
    find(errors(run(repo)), field="Community → Square photo 2 (“Saturday morning with She Runs Berkeley”) → Photo → Photo",
         message="cropped to 700×700")


def test_photos_placed_before_the_cms_are_exempt_in_their_own_spot_only(repo):
    """The Phi Velvet photo is 608×760: small, but placed and checked by hand
    for the special — there it passes (the seed has no errors). Picked for
    another spot it is judged like any new photo."""
    assert errors(run(repo)) == []
    edit(repo, "pages/what.json", lambda d: d["photos"]["hero"].update(image="src-img/originals/special-phi-velvet-cup.jpg"))
    p = find(errors(run(repo)), where="Page: What We Make", field="Photos → Main photo → Photo")
    assert "608×760 pixels" in p["message"]


def test_a_small_square_photo_cant_become_the_homepage_hero(repo):
    """sq-mango-coco.png (364×337) is exempt on the menu card it was made for,
    never in a full-width spot."""
    edit(repo, "pages/home.json", lambda d: d["photos"]["hero"].update(image="src-img/menu/sq-mango-coco.png"))
    p = find(errors(run(repo)), where="Page: Home", field="Top photo → Photo")
    assert "364×337 pixels" in p["message"] and "1200" in p["message"]


def test_a_moved_seed_photo_keeps_its_exemption_only_where_it_was(repo):
    import content as C2
    ex = C2.existing_photos(repo)
    assert ex["src-img/originals/prep-cap-topdown.jpg"] == {"pages/home:photos.hero"}
    assert "menu" in ex["src-img/menu/sq-mango-coco.png"] and "albums" in ex["src-img/albums/02-run-clubs/14.jpg"]


def test_menu_and_instagram_photos_are_checked(repo):
    path = _photo(repo, "uploads", "thin.jpg", (1600, 600))           # square crop 600×600
    edit(repo, "menu.json", lambda d: d["items"][0].update(photo=path))
    edit(repo, "instagram.json", lambda d: d["curated"][0].update(image=path))
    errs = errors(run(repo))
    find(errs, where="Menu", field="Photo", message="cropped to 600×600")
    find(errs, where="Instagram", field="Post 1 → Photo", message="cropped to 600×600")


def test_two_menu_items_with_the_same_name_are_flagged(repo):
    def f(d):
        for it in d["items"]:
            if it["square_name"] == "Mango Coco":
                it["display_name"] = "Pink Pink Pink"
    edit(repo, "menu.json", f)
    probs = run(repo)
    assert errors(probs) == []
    find(probs, level="warning", where="Menu", field="Pink Pink Pink → Name on the website",
         message="same name")


def test_film_needs_a_name(repo):
    edit(repo, "pages/home.json", lambda d: d["film"].update(label=""))
    find(errors(run(repo)), where="Page: Home", field="Film → Name of the film")


# ---------------------------------------------------------------------------
# What isn't on the site can't stop an update; what is, is explained well
# ---------------------------------------------------------------------------
def _event(repo, slug, **fields):
    d = repo / "content" / "events"
    d.mkdir(exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps({"title": slug.title(), "date": "2026-11-08", **fields}))


def test_a_past_event_with_a_deleted_photo_is_only_a_note(repo):
    _event(repo, "old", date="2026-10-01", image="src-img/uploads/gone.jpg", image_alt="Runners")
    probs = run(repo)
    assert errors(probs) == []
    p = find(probs, where="Event: Old", message="can’t be found")
    assert p.get("draft") and "isn’t on the site any more" in p["message"]
    _event(repo, "soon", image="src-img/uploads/gone.jpg", image_alt="Runners")      # upcoming: still an error
    find(errors(run(repo)), where="Event: Soon", message="can’t be found")


def test_an_ended_special_with_a_deleted_photo_is_only_a_note(repo):
    edit(repo, "specials/phi-velvet.json", lambda d: d.update(ends="2026-10-20", image="src-img/uploads/gone.jpg"))
    probs = run(repo)
    assert errors(probs) == []
    assert all(p.get("draft") for p in probs if p["where"] == "Special: Phi Velvet")


def test_a_hidden_menu_item_with_a_deleted_photo_is_only_a_note(repo):
    def f(d):
        for it in d["items"]:
            if it["square_name"] == "Mango Coco":
                it.update(hidden=True, photo="src-img/uploads/gone.jpg")
    edit(repo, "menu.json", f)
    probs = run(repo)
    assert errors(probs) == []
    p = find(probs, where="Menu", field="Bowls · Mango Coco → Photo", message="can’t be found")
    assert p.get("draft") and "hidden from the website" in p["message"]


def test_a_damaged_upload_is_caught_with_its_name_and_spot(repo):
    from PIL import Image
    f = repo / "src-img" / "uploads" / "cut.jpg"
    Image.new("RGB", (1600, 1200), (180, 60, 60)).save(f, quality=95)
    f.write_bytes(f.read_bytes()[:3000])                         # the upload broke off
    edit(repo, "pages/home.json", lambda d: d["photos"]["bowls"].update(image="src-img/uploads/cut.jpg"))
    p = find(errors(run(repo)), where="Page: Home", field="Photos → Bowls photo → Photo")
    assert "“cut.jpg” can’t be opened — the file may be damaged" in p["message"]


def test_a_deleted_square_photo_is_explained(repo):
    """No field points at a Square product photo; deleting it in the media
    library must still say why the card lost its photo."""
    menu = json.loads((repo / "data" / "menu-fallback.json").read_text())
    item = next(i for c in menu["categories"] for i in c["items"]
                if (i.get("image_source") or "").startswith("src-img/menu/"))
    (repo / "src-img" / "menu").unlink()                         # a copy of the folder without that photo
    (repo / "src-img" / "menu").mkdir()
    import shutil
    from conftest import seed_root
    for f in (seed_root() / "src-img" / "menu").iterdir():
        if f"src-img/menu/{f.name}" != item["image_source"]:
            shutil.copy(f, repo / "src-img" / "menu" / f.name)
    p = find(run(repo), level="warning", where="Menu", message="was deleted from the photo library")
    assert "Undo my last change" in p["message"] and "menu refresh" in p["message"] and not p.get("draft")


def test_switching_off_the_link_in_bio_page_warns_about_the_qr_codes(repo):
    edit(repo, "links.json", lambda d: d.update(enabled=False))
    p = find(run(repo), level="warning", where="Link in bio", field="Publish the page")
    assert "QR codes" in p["message"] and "Instagram bio" in p["message"] and not p.get("draft")


def test_a_grid_of_one_or_two_posts_is_flagged(repo):
    edit(repo, "instagram.json", lambda d: d.update(count=2))
    find(run(repo), level="warning", where="Instagram", field="Number of posts", message="Only 2 posts will show")
    edit(repo, "instagram.json", lambda d: d.update(count=4, curated=d["curated"][:1]))
    find(run(repo), level="warning", where="Instagram", field="Hand-picked posts", message="Only 1 post will show")


def test_a_name_needs_letters_or_numbers(repo):
    """An all-emoji name gives an empty web address: refused by the CMS (the
    same rule is a pattern in .pages.yml) and explained here."""
    _event(repo, "2026-10-31-", title="🎃🎃", date="2026-10-31")
    errs = errors(run(repo))
    find(errs, where="Event: 🎃🎃", field="Title", message="at least one letter or number")
    p = find(errs, where="Event: 🎃🎃", field="Title", message="can’t be used in a web address")
    assert "delete this entry and create it again" in p["message"]


def test_links_are_trimmed_on_the_way_in(repo):
    """Pages CMS keeps a pasted link's trailing space or line break; the build
    reads the link without it (and .pages.yml lets it through)."""
    edit(repo, "instagram.json", lambda d: d["curated"][0].update(post_url="https://www.instagram.com/reel/AbC_12-x/ \n"))
    edit(repo, "links.json", lambda d: d["buttons"][1].update(url=" /menu "))
    assert errors(run(repo)) == []
    c = C.load_all(repo)
    assert c["links"]["buttons"][1]["url"] == "/menu"
    assert c["instagram"]["curated"][0]["post_url"] == "https://www.instagram.com/reel/AbC_12-x/"


def test_the_report_never_turns_typed_text_into_markdown(repo):
    """build-report.md is shown on GitHub (and posted as an issue in a public
    repo): an @handle must not notify anyone, and no link or image may form."""
    _event(repo, "run-club", title="Run club with @octocat ![x](https://evil.example/t.png) #12",
           start_time="25:00")
    V.write_report(repo, run(repo), "failed")
    md = (repo / "build-report.md").read_text()
    line = next(ln for ln in md.splitlines() if "octocat" in ln)
    assert "@octocat" not in line and "@⁠octocat" in line
    assert "![x](" not in line and "\\!\\[x\\]" in line and "#⁠12" in line
