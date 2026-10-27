"""The photo slot rule (CMS_SPEC §4): tuned crops stay exactly as tuned until
the manager changes the photo or its framing. Seed assertions read the frozen
seed (tests/fixtures/seed), never the live content."""
import json

import content as C
from conftest import FIXTURE, ROOT, TODAY, blob_id, edit, load_tool, seed_photos, seed_root

SPECS = json.loads((FIXTURE / "src-img" / "slot-specs.json").read_text())
media = load_tool(ROOT / "tools" / "build-home-media.py", "media_for_tests")


def test_tuned_photo_with_auto_framing_uses_the_tuned_values():
    spec = SPECS["home/hero"]
    focal, zoom, edit_ = C.framing(spec["tuned"], spec["tuned"]["image"], "auto", "auto", media.GENTLE_EDIT)
    assert (focal, zoom, edit_) == (spec["tuned"]["focal"], spec["tuned"]["zoom"], spec["tuned"]["edit"])


def test_changing_the_framing_drops_the_tuning():
    spec = SPECS["home/hero"]
    focal, zoom, edit_ = C.framing(spec["tuned"], spec["tuned"]["image"], "top", "auto", media.GENTLE_EDIT)
    assert focal == [0.5, 0.0] and zoom == 1.0 and edit_ == media.GENTLE_EDIT


def test_a_new_photo_gets_keywords_and_the_gentle_retouch():
    spec = SPECS["home/hero"]
    for focus, zoom, want in (("auto", "auto", ([0.5, 0.5], 1.0)), ("bottom-right", "a-little", ([1.0, 1.0], 1.15)),
                              ("left", "more", ([0.0, 0.5], 1.35)), ("top", "none", ([0.5, 0.0], 1.0))):
        f, z, e = C.framing(spec["tuned"], "src-img/uploads/new.jpg", focus, zoom, media.GENTLE_EDIT)
        assert (f, z) == want
        assert e == {"wb": 0.4, "levels": 0.4, "highlights": 0.15, "denoise": 1}


def test_every_page_slot_is_tuned_for_its_seed_photo():
    """With the seed content, every placed photo resolves to its tuned spec —
    which is why the refactor reproduces today's images byte for byte."""
    content = C.load_all(seed_root())
    slots = media.page_slots(content, SPECS)
    assert slots, "no page slots"
    for slot, job in slots.items():
        t = SPECS[slot]["tuned"]
        assert job["src"] == t["image"], slot
        assert (job["focal"], job["zoom"], job["edit"]) == (t["focal"], t["zoom"], t["edit"]), slot


def test_leading_slash_paths_still_match_the_tuning(repo):
    edit(repo, "pages/home.json", lambda d: d["photos"]["hero"].update(image="/src-img/originals/prep-cap-topdown.jpg"))
    slots = media.page_slots(C.load_all(repo), SPECS)
    assert slots["home/hero"]["focal"] == SPECS["home/hero"]["tuned"]["focal"]


def test_unpublished_pages_and_empty_photos_make_no_slot(repo):
    slots = media.page_slots(C.load_all(repo), SPECS)
    assert "gift/hero" not in slots and "loyalty/side" not in slots and "site/share" not in slots
    edit(repo, "site.json", lambda d: d["seo"].update(share_image="src-img/originals/friends-at-storefront.jpg"))
    slots = media.page_slots(C.load_all(repo), SPECS)
    assert slots["site/share"]["widths"] == "share"


def test_menu_photos_keep_their_tuning_and_studio_retouch():
    content = C.load_all(seed_root())
    slots = media.menu_slots(content, SPECS, seed_root() / "data" / "menu-fallback.json")
    assert slots["menu/benys-blendy"]["zoom"] == 1.9
    assert slots["menu/recovery-bowl"]["src"] == "src-img/originals/studio-recovery-bowl.jpg"
    assert slots["menu/pink-pink-pink"]["edit"] == media.MENU_EDIT


def test_fingerprint_changes_with_the_recipe():
    content = C.load_all(seed_root())
    job = media.page_slots(content, SPECS)["home/visit"]
    src = seed_root() / job["src"]
    a = media.fingerprint(job, src)
    assert a == media.fingerprint(dict(job), src)
    assert a != media.fingerprint({**job, "zoom": 1.2}, src)
    assert a != media.fingerprint({**job, "edit": {**job["edit"], "wb": 0.9}}, src)


def test_code_fingerprint_ignores_docstrings_and_comments(tmp_path):
    a, b, c = tmp_path / "a.py", tmp_path / "b.py", tmp_path / "c.py"
    a.write_text('"""doc"""\ndef f():\n    """x"""\n    return 1  # one\n')
    b.write_text('"""other doc"""\n# a comment\ndef f():\n    """y"""\n    return 1\n')
    c.write_text('def f():\n    return 2\n')
    assert C.code_fingerprint(a) == C.code_fingerprint(b) != C.code_fingerprint(c)


# The committed photo manifests store fingerprints that include this hash, so
# it must not change with the Python version (CI runs 3.12, laptops newer).
# This value was computed on 3.11, 3.12 and 3.14; if a Python upgrade changes
# it, every photo would silently be rebuilt in CI — fix code_fingerprint
# instead of updating the number.
FIXTURE = ('"""Module doc."""\nimport math  # a comment\n\n\ndef scale(x, k=2):\n    """Doc é."""\n'
           '    label = f"{x!r:>8} × {k}"  # ×\n    return math.floor(x * k), label\n\n\nclass Tone:\n'
           '    """Doc."""\n    gain = {"wb": 0.4, "#": "not a comment"}\n')


def test_code_fingerprint_is_pinned_across_python_versions(tmp_path):
    p = tmp_path / "fixture.py"
    p.write_text(FIXTURE, encoding="utf-8")
    assert C.code_fingerprint(p) == "644de0d1f1633f8d"


def test_seed_photo_fingerprints_match_this_python():
    """The fixture's manifest (made by the photo build when the seed was
    frozen) is current for the interpreter running the tests: the photo
    fingerprints don't change with the Python version, so CI never rebuilds
    photos a laptop built."""
    seed = seed_root()
    manifest = json.loads((seed / "src-img" / "media-manifest.json").read_text())
    slots = media.all_slots(seed, TODAY)
    assert len(slots) > 30
    for slot, job in slots.items():
        assert manifest[slot]["fp"] == media.fingerprint(job, seed / job["src"]), slot


def test_committed_photo_fingerprints_match_this_python():
    """The repo's own manifest is current too, for every slot whose photo and
    framing are still the seed's (a slot the manager has changed since is
    simply rebuilt by the next build, so it isn't judged here)."""
    seed = seed_root()
    path = ROOT / "src-img" / "media-manifest.json"
    manifest = json.loads(path.read_text())
    seed_jobs, photos = media.all_slots(seed, TODAY), seed_photos()
    live = media.all_slots(ROOT, TODAY)
    checked = 0
    for slot, job in live.items():
        if (slot not in manifest or seed_jobs.get(slot) != job or job["src"] not in photos
                or blob_id(ROOT / job["src"]) != photos[job["src"]]):
            continue
        assert manifest[slot]["fp"] == media.fingerprint(job, ROOT / job["src"]), slot
        checked += 1
    assert checked or not live


def test_entry_slots_for_instagram_specials_and_events(repo):
    content = C.load_all(repo)
    ev = repo / "content" / "events"
    ev.mkdir(exist_ok=True)
    (ev / "run.json").write_text(json.dumps({"title": "Run", "date": "2026-11-07",
                                             "image": "src-img/albums/02-run-clubs/14.jpg", "image_alt": "Runners"}))
    (ev / "old.json").write_text(json.dumps({"title": "Old", "date": "2026-10-01",
                                             "image": "src-img/albums/02-run-clubs/14.jpg", "image_alt": "Runners"}))
    content = C.load_all(repo)
    import datetime as dt
    slots = media.entry_slots(content, SPECS, today=dt.date(2026, 10, 27), root=repo)
    ig = slots["instagram/1"]
    assert (ig["aspect"], ig["widths"], ig["edit"]) == ("1", "tile", media.ALBUM_EDIT)   # an album photo: album look
    sp = slots["specials/phi-velvet"]
    assert sp["edit"] == SPECS["specials/phi-velvet"]["tuned"]["edit"] and sp["aspect"] == "4:5"
    assert slots["events/run"]["widths"] == "thumb" and "events/old" not in slots
    ended = media.entry_slots(content, SPECS, today=dt.date(2027, 1, 1), root=repo)
    assert "specials/phi-velvet" in ended          # no end date: still on


def test_stale_files_are_listed_not_deleted_until_asked(tmp_path, monkeypatch):
    """tools/build.py deletes stale photos only after the pages are written."""
    out = tmp_path / "img"
    (out / "home").mkdir(parents=True)
    keep, old, nameless = out / "home" / "hero-960.jpg", out / "home" / "hero-480.jpg", out / "home" / "-337.webp"
    for f in (keep, old, nameless):
        f.write_bytes(b"x")
    man = tmp_path / "media-manifest.json"
    man.write_text(json.dumps({"home/hero": {"widths": [960], "aspect": 1.6, "fp": "x"}}))
    monkeypatch.setattr(media, "OUT", out)
    monkeypatch.setattr(media, "MANIFEST", man)
    monkeypatch.setattr(media, "all_slots", lambda today=None: {"home/hero": {"src": "missing.jpg"}})
    r = media.build_images(cleanup=False)
    assert set(r["stale"]) == {old, nameless} and old.exists() and nameless.exists()
    assert media.remove(r["stale"]) == 2 and keep.exists() and not old.exists() and not nameless.exists()
