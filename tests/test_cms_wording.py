"""
The editor is written for someone with no technical background (the owner:
"make it as easy for a fully non technical person to make whatever changes
they want simply"). These checks keep .pages.yml that way — docs/dev/CMS.md
"Form order and wording" explains the rules:

  * no web jargon in anything the manager reads (labels, help, choices);
  * help text is short, and an optional field's help starts "Optional —";
  * each form starts with what is changed most: Published first in every
    collection, a photo's Focus and Zoom after the photo and its description,
    "Google and shared links" last on every page;
  * collections list their entries sensibly, and a new entry needs only the
    fields the CMS marks Required — it saves, and the build accepts it;
  * the handbook uses the editor's words, not retired ones.

tests/test_cms_schema.py checks the configuration against the site's own
schema (every key declared, the same labels and limits); this file checks
what it says and in what order.
"""
import json
import re

import cms_normalize as N
import content as C
import validate_content as V
from conftest import ROOT, TODAY, load_tool

CMS = N.Cms(ROOT)
RAW = CMS.raw
ENTRIES = {e["name"]: e for e in CMS.entries}        # components resolved, groups flattened

# Words a café manager shouldn't have to know. ("Google", "link", "photo
# description" are the everyday ones used instead.)
JARGON = re.compile(r"\balt\b|alt text|\bSEO\b|\bslug\b|\bhero\b|\beyebrow\b|\bCTA\b|\bURL\b|\bJSON\b|\bboolean\b"
                    r"|\bfield\b|\bstring\b|\btoken\b|\bmetadata\b|\bfrontmatter\b", re.I)
HELP_MAX = 170           # characters: about two lines under a box
OPTIONAL = "Optional — "

# Labels the editor no longer shows, which the handbook must not send her looking for.
RETIRED = ["Description (alt text)", "Photo description (alt text)", "Hero photo", "Link label", "Availability note",
           "Small heading line", "Albums link label", "Share image", "Default description", "Name of the film (for "
           "screen readers)", "Text description of the film", "Cloudflare Web Analytics token", "→ **SEO**",
           "**Highlight**"]


def visible(fields, where=""):
    """(where, field) for every field the manager sees, depth first (blocks
    included; hidden fields and everything inside them left out)."""
    for f in fields or []:
        if f.get("hidden"):
            continue
        at = f"{where} › {f.get('name')}"
        yield at, f
        yield from visible(f.get("fields"), at)
        for b in f.get("blocks") or []:
            yield f"{at} › {b['name']}", b
            yield from visible(b.get("fields"), f"{at} › {b['name']}")


def every_visible():
    for name, e in ENTRIES.items():
        yield from visible(e["fields"], name)


def groups():
    """Every list of sibling fields (a file, an object, a block), resolved."""
    def walk(fields, where):
        yield where, fields
        for f in fields:
            if f.get("fields"):
                yield from walk(f["fields"], f"{where} › {f['name']}")
            for b in f.get("blocks") or []:
                yield from walk(b.get("fields") or [], f"{where} › {f['name']} › {b['name']}")
    for name, e in ENTRIES.items():
        yield from walk(e["fields"], name)


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------
def test_no_jargon_in_what_the_manager_reads():
    found = []
    for at, f in every_visible():
        texts = [f.get("label") or "", f.get("description") or ""]
        texts += [v.get("label", "") for v in (f.get("options") or {}).get("values") or [] if isinstance(v, dict)]
        found += [f"{at}: {t!r}" for t in texts if JARGON.search(t)]
    for e in ENTRIES.values():
        found += [f"{e['name']}: {e['label']!r}" for t in [e["label"]] if JARGON.search(t)]
    assert not found, "\n".join(found)


def test_help_is_short_and_optional_fields_say_so():
    problems = []
    for at, f in every_visible():
        d = f.get("description") or ""
        if len(d) > HELP_MAX:
            problems.append(f"{at}: {len(d)} characters — keep help to about two lines")
        if "ptional" in d and not d.startswith(OPTIONAL):
            problems.append(f"{at}: say it's optional at the start, as “{OPTIONAL}…”: {d!r}")
        if d.startswith(OPTIONAL) and f.get("required"):
            problems.append(f"{at}: required, but its help says optional")
    assert not problems, "\n".join(problems)


def test_photo_framing_comes_after_the_photo():
    """Focus and Zoom are the rarely-touched part of a photo: after the photo
    and its description, with nothing but read-only boxes after them (an
    album's Cover focus: straight after its Cover photo)."""
    def is_framing(f):
        return f.get("name") in ("focus", "zoom", "cover_focus") and f.get("type") == "select"
    checked = 0
    for where, fields in groups():
        names = [f["name"] for f in fields]
        framing = [i for i, f in enumerate(fields) if is_framing(f)]
        if not framing:
            continue
        checked += 1
        if "cover_focus" in names:
            assert names.index("cover_focus") == names.index("cover") + 1, f"{where}: {names}"
            continue
        first = framing[0]
        assert all(is_framing(f) or f.get("readonly") for f in fields[first:]), f"{where}: {names}"
        assert any(f.get("type") == "image" for f in fields[:first]), f"{where}: the photo comes first"
        assert "alt" not in names or names.index("alt") < first, f"{where}: its description before Focus"
    assert checked > 40
    assert all(RAW["components"][c]["description"].startswith(OPTIONAL) for c in ("photo-focus", "photo-zoom"))


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------
def test_published_comes_first_in_every_collection():
    """Switching Published off is how something comes down: it's the first
    box, and a new entry starts published."""
    for e in CMS.entries:
        if e["type"] == "collection":
            first = e["fields"][0]
            assert (first["name"], first["type"], first.get("default")) == ("published", "boolean", True), e["name"]


def test_google_and_shared_links_is_last_on_every_page():
    for e in CMS.entries:
        shown = [f for f in e["fields"] if not f.get("hidden")]
        if any(f["name"] == "seo" for f in shown):
            assert shown[-1]["name"] == "seo", e["name"]
            assert shown[-1]["label"] == C.SEO_LABEL
    for e in CMS.entries:                # pages of her own: the Google boxes are hers to fill, last
        if e["name"] == "custom-pages":
            assert [f["name"] for f in e["fields"][-2:]] == ["google_title", "google_description"]


def test_the_most_used_comes_first():
    """Spot checks of the order that matters most."""
    first = {name: [f["name"] for f in e["fields"]][:2] for name, e in ENTRIES.items()}
    assert first["announcement"] == ["enabled", "message"]
    assert first["specials"] == ["published", "name"] and first["events"] == ["published", "title"]
    assert first["hours"] == ["special", "weekly"]                # holidays change far more often
    assert first["menu"][0] == "items" and first["links"][0] == "buttons" and first["instagram"][0] == "curated"
    assert [f["name"] for f in ENTRIES["links"]["fields"]][-1] == "enabled"         # take-down switches last
    assert [f["name"] for f in ENTRIES["instagram"]["fields"]][-1] == "enabled"
    home = [f["name"] for f in ENTRIES["home"]["fields"]]
    assert home.index("sections") < home.index("film") < home.index("seo")
    item = [f["name"] for f in ENTRIES["menu"]["fields"][0]["fields"]]
    assert item[:2] == ["square_name", "display_name"] and item[-1] == "square_id"


def test_analytics_is_hidden_but_kept():
    """The manager never needs it, so it's out of sight — but still declared,
    so a save keeps the developer's token."""
    site = ENTRIES["site"]
    (an,) = [f for f in site["fields"] if f["name"] == "analytics"]
    assert an.get("hidden") is True and site["fields"][-1] is an
    data = json.loads((ROOT / "tests" / "fixtures" / "seed" / "content" / "site.json").read_text())
    data["analytics"] = {"cloudflare_web_analytics_token": "0123456789abcdef0123456789abcdef"}
    text, problems = N.save(data, site, CMS, TODAY)
    assert not problems and json.loads(text)["analytics"] == data["analytics"]


# ---------------------------------------------------------------------------
# Collections: the list, and a new entry
# ---------------------------------------------------------------------------
def test_collection_lists():
    views = {e["name"]: e["view"] for e in CMS.entries if e["type"] == "collection"}
    for name, v in views.items():
        assert v["fields"][0] == v["primary"] and v["default"]["sort"] in v["sort"], name
        assert "published" in v["fields"], f"{name}: show which entries are drafts"
    assert (views["events"]["default"]["sort"], views["events"]["default"]["order"]) == ("date", "desc")
    assert views["albums"]["default"]["sort"] == "order"          # as they're shown on the site


NEW = {      # each collection's Required boxes, and a file name the CMS would make from them
    "specials": ({"name": "Pumpkin Bowl"}, "pumpkin-bowl"),
    "events": ({"title": "Saturday run club", "date": "2026-11-07"}, "2026-11-07-saturday-run-club"),
    "albums": ({"title": "Summer pop-ups"}, "summer-pop-ups"),
    "custom-pages": ({"title": "Gift ideas", "address": "gift-ideas"}, "gift-ideas"),
}


def test_a_new_entry_needs_only_its_required_boxes(repo):
    """"Add an entry", fill in what's marked Required, Save: the CMS saves it
    (with its defaults: published, no order button …) and the update goes
    through — at most a "worth a look" note, never an error."""
    cms = N.Cms(ROOT)
    for coll, (filled, stem) in NEW.items():
        e = ENTRIES[coll]
        required = {f["name"] for f in e["fields"] if f.get("required")}
        assert required == set(filled), f"{coll}: the Required boxes are {sorted(required)}"
        state = N.init_state(e["fields"], {}, TODAY)
        state.update(filled)
        text, problems = N.save(state, e, cms, TODAY)
        assert not problems, (coll, problems)
        saved = json.loads(text)
        assert saved["published"] is True
        (repo / "content" / coll).mkdir(exist_ok=True)
        (repo / "content" / coll / f"{stem}.json").write_text(text)
    assert json.loads((repo / "content" / "specials" / "pumpkin-bowl.json").read_text())["order_button"] == "none"
    problems = [p for p in V.validate(repo, TODAY) if any(p["file"].endswith(f"/{s}.json") for _, s in NEW.values())]
    assert not [p for p in problems if p["level"] == "error"], problems


def test_the_menu_refresh_writes_new_items_in_the_editors_order(repo):
    """A Square item the refresh adds is written with its keys in the CMS's
    field order, so the next save in the editor changes nothing about it."""
    sync = load_tool(repo / "tools" / "sync-menu-from-store.py", "sync_wording")
    content = json.loads((repo / "content" / "menu.json").read_text())
    data = json.loads((repo / "data" / "square-store-products.json").read_text())
    content["items"] = content["items"][1:]                      # as if Square had just added the first item
    out, added, _ = sync.update_content(data, content)
    assert added
    item_fields = [f["name"] for f in ENTRIES["menu"]["fields"][0]["fields"]]
    assert list(out["items"][-1]) == item_fields


# ---------------------------------------------------------------------------
# The handbook speaks the editor's language
# ---------------------------------------------------------------------------
def test_the_handbook_uses_the_editors_words():
    text = (ROOT / "docs" / "HANDBOOK.md").read_text(encoding="utf-8")
    assert not [w for w in RETIRED if w in text], [w for w in RETIRED if w in text]
    for label in (C.ALT_LABEL, C.SEO_LABEL, "Google title", "Google description", "First day shown",
                  "Last day shown", "Start time", "Order button text", "Note instead of a button", "Top photo",
                  "Green button", "Menu items", "Name in the menu"):
        assert f"**{label}**" in text, f"the handbook should name “{label}”"
