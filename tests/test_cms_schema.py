"""
The Pages CMS configuration (.pages.yml) against the site's own content
schema (tools/content.py), the content files, and the workflows.

Pages CMS rewrites a whole file from .pages.yml when the manager saves, so a
mismatch here loses data or breaks the build on the first save (CMS_SPEC §8):

  * every key the site reads is declared, with the validator's label;
  * every hard limit the validator enforces is enforced in the CMS too, and
    no soft limit (a warning) blocks a save there;
  * defaults agree, so a missing key means the same thing to both;
  * a simulated CMS save of every file (tools/cms_normalize.py, a port of
    Pages CMS's save code) leaves the built site unchanged;
  * the sidebar and the action buttons are what the handbook describes.

The content files these checks read are the frozen seed (tests/fixtures/seed,
see conftest.py), never the live content/ — a manager's save can't fail
them. The live files are checked in CI by `tools/cms_normalize.py --check`,
a step that tells the developer but never stops a publish.

tools/cms_normalize.py itself was checked against Pages CMS v2.1.8's own
code (byte-identical saves of every content file, and ~15,000 fuzzed
variants); the tests below pin the behaviours that matter.
"""
import json
import re
import shutil

import pytest

try:      # not importorskip: these checks guard every CMS save, so they must never be skipped quietly
    import yaml
except ImportError:          # pragma: no cover
    raise ImportError("PyYAML is needed to read .pages.yml: pip install -r requirements.txt") from None

import cms_normalize as N  # noqa: E402
import content as C  # noqa: E402
import hours  # noqa: E402
import render  # noqa: E402
import validate_content as V  # noqa: E402
from conftest import FIXTURE, ROOT, TODAY, load_tool, seed_content, seed_root  # noqa: E402

CMS = N.Cms(ROOT)          # the configuration (code)


def seed_cms():
    """The configuration over the frozen seed content."""
    return N.Cms(seed_root())

# The five workflows the CMS buttons start (CMS_SPEC §11) and their labels.
ACTIONS = {"Publish now": "build-deploy.yml", "Refresh menu from Square": "menu-refresh.yml",
           "Back up now": "backup.yml", "Restore a backup": "restore.yml", "Undo my last change": "undo.yml"}

# Sidebar order (CMS_SPEC §11 / the handbook). Labels are the validator's
# "where" names (tools/content.py WHERE / PAGES), so an error message and the
# CMS screen use the same words; a collection is the plural of its entries'
# "Special: …", "Event: …", "Album: …".
COLLECTION_LABELS = {"specials": "Specials", "events": "Events", "albums": "Photo albums",
                     "custom-pages": "Your own pages"}
SIDEBAR = [
    ("This week", [C.WHERE["announcement"], "Specials", "Events", C.WHERE["hours"]]),
    (C.WHERE["menu"], None),
    ("Pages", [C.PAGES[k] for k in ("home", "story", "how", "what", "day", "catering", "visit")]
     + [C.WHERE["faq"], C.WHERE["links"]] + [C.PAGES[k] for k in ("gift-cards", "loyalty", "404")]
     + ["Your own pages"]),
    ("Photo albums", None),
    (C.WHERE["instagram"], None),
    (C.WHERE["site"], None),
]

# Files that may be saved unfinished: nothing in them is required in the CMS
# (the validator reports their problems as drafts until they're published).
DRAFT_FILES = {"content/pages/gift-cards.json", "content/pages/loyalty.json"}

# The patterns the CMS uses, each checked below against the validator itself.
TIME = r"^\s*$|^\s*([01][0-9]|2[0-3]):[0-5][0-9]\s*$"      # spaces around it are trimmed (content.Time)
# Links allow spaces around them (a paste often brings one; the build trims them).
WEB = r"^\s*$|^\s*https://[^\s/$.?#]\S*\s*$"
SITE = r"^\s*$|^\s*(https://[^\s/$.?#]\S*|#\S*|/(?![/\\])\S*)\s*$"


# ---------------------------------------------------------------------------
# Walking .pages.yml and tools/content.py side by side
# ---------------------------------------------------------------------------
def schema_of(entry):
    """The tools/content.py schema an entry manages: (fields, where-label)."""
    path = entry["path"]
    if entry["type"] == "collection":
        coll = path.split("/", 1)[1]
        return C.COLLECTIONS[coll][1], COLLECTION_LABELS[coll]
    key = path[len("content/"):-len(".json")]
    if key.startswith("pages/"):
        return C.PAGE_SCHEMAS[key[6:]], C.PAGES[key[6:]]
    return C.SCHEMAS[key], C.WHERE[key]


def pairs(schema, fields, path, mismatches):
    """(path, content.py node, .pages.yml field) for every field both sides
    declare; keys only one side declares go to `mismatches`. An empty group
    (a page's "photos": {} with no photos) has nothing to declare."""
    by_name = {f["name"]: f for f in fields}
    want = [k for k, n in schema.items() if not (isinstance(n, C.Obj) and not n.fields)]
    at = ".".join(map(str, path))
    for k in want:
        if k not in by_name:
            mismatches.append(f"{at}.{k}: in tools/content.py (the site reads it) but not declared in "
                              ".pages.yml — the first CMS save would delete it")
            continue
        node, f = schema[k], by_name[k]
        yield path + (k,), node, f
        if isinstance(node, C.Blocks):        # each kind of section, field by field
            cms_blocks = {b["name"]: b for b in f.get("blocks") or []}
            for name, block in node.blocks.items():
                if name not in cms_blocks:
                    mismatches.append(f"{at}.{k}: the section kind “{name}” is in tools/content.py but not in "
                                      ".pages.yml")
                    continue
                yield from pairs(block.fields, cms_blocks[name].get("fields") or [], path + (k, name), mismatches)
            for name in cms_blocks:
                if name not in node.blocks:
                    mismatches.append(f"{at}.{k}: the section kind “{name}” is in .pages.yml but not in "
                                      "tools/content.py — the build would never draw it")
        elif isinstance(node, C.Obj):
            yield from pairs(node.fields, f.get("fields") or [], path + (k,), mismatches)
        elif isinstance(node, C.List) and isinstance(node.item, C.Obj):
            yield from pairs(node.item.fields, f.get("fields") or [], path + (k, "[]"), mismatches)
    for k in by_name:
        if k not in want:
            mismatches.append(f"{at}.{k}: declared in .pages.yml but not in tools/content.py — the build "
                              "would never read it")


def every_field():
    """[(entry, path, node, field, draft)] across the whole config, and the
    keys only one side declares."""
    out, mismatches = [], []
    for e in CMS.entries:
        schema, _ = schema_of(e)
        for path, node, f in pairs(schema, e["fields"], (e["name"],), mismatches):
            out.append((e, path, node, f, e["path"] in DRAFT_FILES))
    return out, mismatches


FIELDS, MISMATCHES = every_field()


def _id(x):
    return ".".join(map(str, x[1]))


def every_field_passes(check):
    """Run a per-field check on every field; report every failure at once."""
    failures = []
    for item in FIELDS:
        try:
            check(item)
        except AssertionError as e:
            failures.append(f"{_id(item)}: {e}")
    assert not failures, f"{len(failures)} field(s):\n" + "\n".join(failures)


def cms_fields(fields):
    for f in fields:
        yield f
        yield from cms_fields(f.get("fields") or [])
        for b in f.get("blocks") or []:
            yield from cms_fields(b.get("fields") or [])


# ---------------------------------------------------------------------------
# Every key declared, with the validator's words
# ---------------------------------------------------------------------------
def test_config_is_usable_by_the_normaliser():
    """Field types, collection file names, date formats: everything
    tools/cms_normalize.py (and so the save simulation) understands."""
    assert len(CMS.entries) == 21
    assert {e["path"] for e in CMS.entries if e["type"] == "collection"} == {
        "content/specials", "content/events", "content/albums", "content/custom-pages"}


def test_every_content_file_is_managed_and_every_key_declared():
    cms, seed = seed_cms(), seed_root()
    managed = {rel for rel, _ in cms.files()}
    on_disk = {str(p.relative_to(seed)) for _, p, _, _ in C.files(seed)}
    assert managed == on_disk
    for rel, entry in cms.files():
        _, problems = N.save(json.loads((seed / rel).read_text()), entry, cms)
        assert not problems, f"{rel}: {problems}"


def test_both_sides_declare_the_same_fields():
    """Every key the site reads (tools/content.py) is declared in .pages.yml,
    and nothing else is."""
    assert not MISMATCHES, "\n".join(MISMATCHES)
    assert len(FIELDS) > 300


def _labels_match_the_validator(item):
    _, path, node, f, _ = item
    assert f.get("label") == node.label, f"{'.'.join(map(str, path))}: “{f.get('label')}” vs “{node.label}”"


def test_labels_match_the_validator():
    every_field_passes(_labels_match_the_validator)


def test_sidebar_order_and_names():
    raw = CMS.raw["content"]
    got = [(it.get("label"), [x.get("label") for x in it["items"]] if it.get("type") == "group" else None)
           for it in raw]
    assert got == SIDEBAR
    for e in CMS.entries:
        assert e["label"] == schema_of(e)[1]


# ---------------------------------------------------------------------------
# Types, limits and defaults agree with tools/content.py
# ---------------------------------------------------------------------------
def _types_agree(item):
    _, path, node, f, _ = item
    t, opts = f.get("type"), f.get("options") or {}
    if isinstance(node, C.Blocks):
        # a list of blocks, stored under the same key, with the same kinds and labels in the same order
        assert t == "block" and f.get("list") and f.get("blockKey") == node.key
        assert [(b["name"], b["label"]) for b in f["blocks"]] == [(k, b.label) for k, b in node.blocks.items()]
        return
    if isinstance(node, C.List):
        assert f.get("list"), "a list in tools/content.py must be a list in the CMS"
        node = node.item
    else:
        assert not f.get("list")
    if isinstance(node, C.Obj):
        assert t == "object"
    elif isinstance(node, C.Bool):
        assert t == "boolean"
    elif isinstance(node, C.Int):
        assert t == "number" and opts.get("min") == node.min and opts.get("max") == node.max
    elif isinstance(node, C.Choice):
        names = [v["name"] if isinstance(v, dict) else v for v in opts["values"]]
        assert t == "select" and names == list(node.options) and not opts.get("multiple")
    elif isinstance(node, C.Date):
        assert t == "date" and opts.get("format") == "yyyy-MM-dd"
        assert f.get("default") == "", "without default \"\" a new date field starts as today's date"
    elif isinstance(node, C.Time):
        assert t == "string" and f["pattern"]["regex"] == TIME
    elif isinstance(node, C.Image):
        assert t == "image" and opts.get("media") == "photos" and opts.get("path") == "src-img/uploads"
    elif isinstance(node, C.Url):
        assert t == "string" and f.get("pattern"), "links are checked in the CMS too"
        regex = f["pattern"]["regex"]
        assert regex in (WEB, SITE) or regex in SPECIAL_PATTERNS
        if regex == SITE:
            assert "site" in node.allow
        if regex == WEB:
            assert node.allow == ("https",)
    elif isinstance(node, C.Text):
        assert t in ("string", "text")
        if node.markdown or node.multiline:
            assert t == "text", "formatted text needs the multi-line box"
        if f.get("pattern"):
            assert f["pattern"]["regex"] in SPECIAL_PATTERNS
    else:
        raise AssertionError(f"unmapped content type {type(node).__name__}")


def test_types_agree():
    every_field_passes(_types_agree)


def _limits_agree(item):
    """Errors in the validator are hard limits in the CMS; warnings never are
    (a warning must not stop a save). Draft pages require nothing."""
    _, path, node, f, draft = item
    opts, lst = f.get("options") or {}, f.get("list")
    assert "minlength" not in opts
    if isinstance(node, C.Blocks):
        assert isinstance(lst, dict) and "collapsible" in lst and not f.get("required")
        assert lst.get("min") is None and lst.get("max") is None, "any number of sections, none needed"
        return
    if isinstance(node, C.List):
        if isinstance(node.item, C.Obj):
            assert isinstance(lst, dict) and "collapsible" in lst, "the object form of list needs collapsible"
            assert not f.get("required"), "use list.min, not required, on a list of groups"
            assert lst.get("min") == (None if draft or not node.min else node.min)
            assert lst.get("max") == node.max
        else:
            # on a list of texts, `required` means "at least one item" in the CMS
            assert lst is True and node.max is None
            assert bool(f.get("required")) == (node.min >= 1 and not draft)
            assert opts.get("maxlength") == getattr(node.item, "max", None)
        return
    if isinstance(node, C.Text):
        assert opts.get("maxlength") == node.max
    if isinstance(node, C.Obj) or draft:
        assert not f.get("required"), "a draft page must be saveable unfinished"
    else:
        assert bool(f.get("required")) == bool(node.required), "required must match tools/content.py"


def test_limits_agree():
    every_field_passes(_limits_agree)


def _defaults_agree(item):
    """A missing key means its default to the build; the CMS shows (and then
    saves) its own default for it. They must be the same value."""
    _, path, node, f, _ = item
    if isinstance(node, (C.Obj, C.List, C.Date, C.Blocks)):
        return
    want = node.default()
    if "default" in f:
        assert f["default"] == want
    elif isinstance(node, C.Bool):
        assert want is False, "a switch without a CMS default starts off"
    else:
        assert want == "", f"declare `default: {want!r}` in .pages.yml"


def test_defaults_agree():
    every_field_passes(_defaults_agree)


def test_announcement_limit_and_alt_texts():
    """Spot checks of the numbers people ask about."""
    ann = {f["name"]: f for f in next(e for e in CMS.entries if e["name"] == "announcement")["fields"]}
    assert ann["message"]["options"]["maxlength"] == C.SCHEMAS["announcement"]["message"].max == 110
    alts = [f for f in cms_fields(sum((e["fields"] for e in CMS.entries), [])) if f["name"] in ("alt", "image_alt")]
    assert alts and all(f["options"]["maxlength"] == 250 for f in alts)


# ---------------------------------------------------------------------------
# Every pattern accepts exactly what the validator accepts
# ---------------------------------------------------------------------------
def _site_error(section, key, value):
    data = {section: {key: value}}
    v = V.Context(ROOT, "Business details", "content/site.json")
    V.check_site(data, v)
    return any(p["level"] == "error" for p in v.problems)


def _price_error(value):
    v = V.Context(ROOT, "Special", "content/specials/x.json")
    V.check_special({"price": value}, v, TODAY)
    return any(p["level"] == "error" and p["field"] == "Price" for p in v.problems)


def _web_name_error(value):
    v = V.Context(ROOT, "Special", "content/specials/x.json")
    C.COLLECTIONS["specials"][1]["name"].check(value, v, ["Name"])
    return any(p["level"] == "error" for p in v.problems)


def _address_error(value):
    """A page of her own's web address: the validator's own checks (the
    pattern and the reserved words; the file name is the address)."""
    v = V.Context(ROOT, "Your page", "content/custom-pages/x.json")
    C.COLLECTIONS["custom-pages"][1]["address"].check(value, v, ["Web address"])
    V.check_custom_page({"address": value}, v, value.strip())
    return any(p["level"] == "error" and p["field"] == "Web address" for p in v.problems)


def _time_error(value):
    v = V.Context(ROOT, "Opening hours", "content/hours.json")
    C.Time("Opens").check(value, v, ["Opens"])
    return bool(v.problems)


SPECIAL_PATTERNS = {
    r"^$|^\+?[0-9\s().-]{7,20}$": (lambda s: _site_error("business", "phone", s),
                                   ["(510) 555-0123", "+1 510 555 0123", "510.555.0123", "555-01", "call us",
                                    "510-555-0123 ext 4", "12345678901234567890", "123456789012345678901"]),
    r"^$|^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$": (lambda s: _site_error("business", "public_email", s),
                                             ["hello@layers.com", "a@b.co", "a@b", "a b@c.com", "@b.com",
                                              "a@b.c", "x@y.museum", "a@@b.com"]),
    r"^$|^@?[A-Za-z0-9._]{1,30}$": (lambda s: _site_error("social", "instagram_handle", s),
                                     ["layerssuperfoodbar", "@layerssuperfoodbar", "layers.bar_1",
                                      "https://instagram.com/x", "a" * 31, "a b", "@"]),
    r"^$|^[0-9a-fA-F]{32}$": (lambda s: _site_error("analytics", "cloudflare_web_analytics_token", s),
                               ["0123456789abcdef0123456789ABCDEF", "0123456789abcdef", "g" * 32, "a" * 33]),
    r"^$|^\$?[0-9]{1,3}(\.[0-9]{2})?$": (_price_error, ["9.50", "$9.50", "12", "1234", "9.5", "$", "nine",
                                                        "9.505", "$100.00"]),
    # the validator checks these stripped (a pasted link's spaces don't count)
    r"^\s*https://(www\.)?instagram\.com/(p|reel|reels|tv)/[A-Za-z0-9_-]+/?(\?\S*)?\s*$": (
        lambda s: not C.INSTAGRAM_POST.fullmatch(s.strip()),
        ["https://www.instagram.com/p/DeFwOJmj8zc/", "https://instagram.com/reel/abc_-1",
         "https://www.instagram.com/p/abc/?igsh=x", "https://www.instagram.com/layerssuperfoodbar/",
         "http://www.instagram.com/p/abc/", "https://www.instagram.com/stories/x/1/", "",
         "https://instagram.com/reel/ABC/ ", " https://www.instagram.com/p/abc/\n", "https://www.instagram.com/p/a b/"]),
    r"^\s*$|^\s*https://feeds\.behold\.so/[A-Za-z0-9_-]+/?\s*$": (
        lambda s: bool(s.strip()) and not C.BEHOLD_FEED.fullmatch(s.strip()),
        ["https://feeds.behold.so/AbC123", "https://feeds.behold.so/AbC123/", "https://behold.so/AbC123",
         "https://feeds.behold.so/a/b", "http://feeds.behold.so/abc", " https://feeds.behold.so/AbC123 "]),
    # a special's / event's / album's name becomes its web address: letters or numbers needed
    r"[A-Za-z0-9]": (_web_name_error, ["Phi Velvet", "🎃🎃", "Açaí 2", "抹茶", "★", "", "x", "9", "🍓 Strawberry"]),
    # a page of her own's web address: a-z, 0-9 and dashes, and none of the site's own paths
    C.address_pattern(): (_address_error,
                          ["summer-menu", "menu", "Menu", "summer menu", "summer--menu", "-summer", "summer-", "a",
                           "2027", "404", "edit", "menu-2", "our-menu", "cdn-cgi", "café", "", "summer_menu",
                           "layers", "home", "story-of-us", "photo-prep", "links-2", " summer", "visit"]),
}

URL_SAMPLES = ["https://layerssuperfoodbar.square.site", "https://x.co/a?b=c#d", "http://x.com", "https://",
               "https://.x.com", "https:// x.com", "ftp://x.com", "mailto:hi@layers.com", "/menu",
               "/catering#catering", "#faq", "//evil.com", "/\\evil", "/a b", "menu", "javascript:alert(1)", "",
               " https://x.co/a ", "https://x.co/a\n", "\t/menu ", "  ", " // evil.com"]


@pytest.mark.parametrize("regex,check,samples", [(TIME, _time_error,
                                                   ["09:00", "9:00", "23:59", "24:00", "00:00", "18:30", "12:60",
                                                    "1200", "ab:cd", "07:5", "19:05", "", "-1:00", "17:00 ",
                                                    " 09:00", "17:00\n", "  ", "17: 00", "1 7:00"])]
                         + [(r, c, s) for r, (c, s) in SPECIAL_PATTERNS.items()])
def test_patterns_agree_with_the_validator(regex, check, samples):
    for s in samples:
        assert bool(re.search(regex, s)) == (not check(s)), f"{s!r}: CMS and validator disagree"


@pytest.mark.parametrize("regex,allow", [(WEB, ("https",)), (SITE, ("https", "site"))])
def test_link_patterns_agree_with_the_validator(regex, allow):
    for s in URL_SAMPLES:
        assert bool(re.search(regex, s)) == (s.strip() == "" or C.url_ok(s, allow)), f"{s!r}"


def test_patterns_only_come_from_the_checked_list():
    for e in CMS.entries:
        for f in cms_fields(e["fields"]):
            if f.get("pattern"):
                assert f["pattern"]["regex"] in (TIME, WEB, SITE, *SPECIAL_PATTERNS)
                assert f["pattern"].get("message"), "a pattern needs a friendly message"


# ---------------------------------------------------------------------------
# Media, operations, lists, the YAML itself
# ---------------------------------------------------------------------------
def test_media_and_uploads():
    (m,) = CMS.raw["media"]
    assert (m["input"], m["output"], m["extensions"], m["rename"]) == (
        "src-img", "src-img", ["jpg", "jpeg", "png", "webp"], "safe")
    for e in CMS.entries:
        for f in cms_fields(e["fields"]):
            if f.get("type") == "image":
                assert f["options"] == {"media": "photos", "path": "src-img/uploads"}


def test_every_photo_in_content_can_be_picked_in_the_cms():
    """The media browser lists only these extensions (lower case), and a
    content file pointing at anything else can't be saved."""
    for rel, entry in seed_cms().files():
        text = (seed_root() / rel).read_text()
        for path in re.findall(r'"(src-img/[^"]+)"', text):
            assert path.rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp"), f"{rel}: {path}"


def test_files_and_collections_are_protected():
    for e in CMS.entries:
        ops = e.get("operations") or {}
        if e["type"] == "file":
            assert ops.get("delete") is False, f"{e['name']}: the manager must not be able to delete it"
        else:
            assert ops.get("rename") is False, f"{e['name']}: the file name is the address and photo name"
            fn = e["filename"]["template"]
            assert fn.endswith(".json") and e["filename"].get("field") is False and e.get("subfolders") is False


def test_list_fields_have_no_description():
    """Pages CMS doesn't show a list's description, and repeats it under
    every item — describe the fields inside instead."""
    for e in CMS.entries:
        for f in cms_fields(e["fields"]):
            if f.get("list"):
                assert not f.get("description"), f"{e['name']} › {f['name']}"


def test_yaml_reads_the_same_in_pages_cms():
    """Pages CMS reads YAML 1.2; PyYAML (the tests, the normaliser) reads
    1.1. Plain scalars the two read differently must be quoted, and keys
    must be unique (the CMS keeps the last one silently)."""
    text = (ROOT / ".pages.yml").read_text()
    risky = re.compile(r"(y|Y|yes|Yes|YES|n|N|no|No|NO|on|On|ON|off|Off|OFF)"
                       r"|[-+]?[0-9][0-9_]*(:[0-5]?[0-9])+(\.[0-9_]*)?"     # 09:00 -> 540 in YAML 1.1
                       r"|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}.*"                  # dates
                       r"|0[0-9]+|[-+]?[0-9][0-9_]*_[0-9_]*")                # octal / 1_000
    for tok in yaml.scan(text):
        if isinstance(tok, yaml.ScalarToken) and tok.plain:
            assert not risky.fullmatch(tok.value), f"quote {tok.value!r} in .pages.yml"

    class Unique(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
        dup = {k for k in keys if keys.count(k) > 1}
        assert not dup, f"duplicate keys in .pages.yml: {dup}"
        return yaml.SafeLoader.construct_mapping(loader, node, deep)
    Unique.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    yaml.load(text, Loader=Unique)


# ---------------------------------------------------------------------------
# The action buttons
# ---------------------------------------------------------------------------
def test_actions():
    acts = CMS.raw["actions"]
    assert [a["label"] for a in acts] == list(ACTIONS)
    for a in acts:
        assert a["workflow"] == ACTIONS[a["label"]] and a["ref"] == "main"
        c = a["confirm"]
        assert c["title"].endswith("?") and len(c["message"]) > 40 and c["button"]
    restore = next(a for a in acts if a["workflow"] == "restore.yml")
    assert restore["fields"] == [{"name": "backup", "label": "Backup name", "type": "text", "required": True,
                                  "default": "latest"}]
    assert all(not a.get("fields") for a in acts if a is not restore)


def test_action_workflows_exist_and_take_the_payload():
    """Each button's workflow is in .github/workflows/ (or is one of the five
    CMS_SPEC §11 names, while it's being written) and accepts the `payload`
    input Pages CMS sends."""
    for a in CMS.raw["actions"]:
        wf = ROOT / ".github" / "workflows" / a["workflow"]
        assert wf.is_file() or a["workflow"] in ACTIONS.values()
        if wf.is_file():
            doc = yaml.safe_load(wf.read_text())
            on = doc.get("on", doc.get(True))          # YAML 1.1 reads the key `on` as true
            inputs = (on.get("workflow_dispatch") or {}).get("inputs") or {}
            assert "payload" in inputs, f"{a['workflow']} must accept the `payload` input"


# ---------------------------------------------------------------------------
# The normaliser: a faithful CMS save
# ---------------------------------------------------------------------------
def test_content_files_are_in_the_cms_format():
    """So the history of a CMS edit shows only the edit (and "Undo my last
    change" reverts only that). The seed is; the live files are checked by
    `python3 tools/cms_normalize.py --check` (CI runs it for the developer)."""
    cms = seed_cms()
    for rel, entry in cms.files():
        old, new, problems = N.normalise(rel, cms)
        assert not problems and old == new, f"{rel} isn't in the CMS's format: run python3 tools/cms_normalize.py"


def test_normalisation_is_idempotent():
    cms, seed = seed_cms(), seed_root()
    for rel, entry in cms.files():
        data = json.loads((seed / rel).read_text())
        schema, _ = schema_of(entry)
        for d in (data, C.normalise(schema, json.loads((seed / rel).read_text()))):
            once, p1 = N.save(d, entry, cms)
            twice, p2 = N.save(json.loads(once), entry, cms)
            assert not p1 and not p2 and once == twice, rel


def test_simulated_cms_save_leaves_the_built_site_unchanged(repo):
    """Start from the most hand-written form of every file (every key, with
    the build's defaults filled in), save each one the way Pages CMS does,
    and the content the build reads, the menu data, every page and the
    validator's findings stay exactly the same."""
    shutil.copy(ROOT / ".pages.yml", repo / ".pages.yml")
    for _, path, schema, _ in C.files(repo):
        full = C.normalise(schema, json.loads(path.read_text()))
        path.write_text(json.dumps(full, indent=2, ensure_ascii=False) + "\n")

    def snapshot(name):
        load_tool(repo / "tools" / "sync-menu-from-store.py", name).sync(offline=True)
        return (C.load_all(repo), (repo / "data" / "menu-fallback.json").read_text(),
                render.Site(root=repo, today=TODAY).render_all(), V.validate(repo, TODAY))

    before = snapshot("sync_cms_before")
    cms = N.Cms(repo)
    changed = 0
    for rel, entry in cms.files():
        p = repo / rel
        text, problems = N.save(json.loads(p.read_text()), entry, cms)
        assert not problems, f"{rel}: {problems}"
        changed += text != p.read_text()
        p.write_text(text)
    assert changed == len(cms.files())
    after = snapshot("sync_cms_after")
    for i, what in enumerate(("content", "menu data", "pages", "validation")):
        assert after[i] == before[i], f"a CMS save changed the {what}"


def test_sanitize_matches_pages_cms():
    """sanitizeObject: "" and null go everywhere; an emptied list or group
    is dropped as a value but an empty group INSIDE a list stays; false and
    0 are values."""
    got = N.sanitize({"a": "", "b": [], "c": {"d": ""}, "e": [{}], "f": False, "g": 0,
                      "h": ["", None, "x"], "i": None, "j": [[]], "k": {"l": [""]}})
    assert got == {"e": [{}], "f": False, "g": 0, "h": ["x"], "j": [[]]}
    assert N.dump({"a": 1, "1": 2}) == '{\n  "1": 2,\n  "a": 1\n}'      # JS: integer-like keys first
    assert N.dump({}) == ""


def _entry(name):
    return next(e for e in CMS.entries if e["name"] == name)


def test_what_a_cms_save_does():
    ann = seed_content("announcement.json")
    text, problems = N.save({**ann, "message": "Hello", "starts": "2026-11-01", "ends": ""}, _entry("announcement"), CMS)
    assert not problems and json.loads(text) == {**ann, "message": "Hello", "starts": "2026-11-01"}
    assert not text.endswith("\n") and text.startswith('{\n  "enabled"')
    # a missing switch or choice gets the CMS default, written out
    text, _ = N.save({"message": "Hi"}, _entry("announcement"), CMS)
    assert json.loads(text) == {"enabled": False, "message": "Hi", "tone": "green"}
    # a special without the order-button keys gets their defaults (as the build does)
    sp = seed_content("specials/phi-velvet.json")
    del sp["order_button"], sp["availability_note"]
    out = json.loads(N.save(sp, _entry("specials"), CMS)[0])
    assert out["order_button"] == "none" and out["availability_note"] == "In store for a limited time."


@pytest.mark.parametrize("change,kind", [
    (lambda d: d.update(colour="red"), "undeclared"),
    (lambda d: d["weekly"]["monday"].update(note="by appointment"), "undeclared"),
    (lambda d: d.update(special=[{"date": "11/26/2026", "label": "Thanksgiving", "closed": True}]), "lost"),
    (lambda d: d["weekly"]["monday"].update(open="9am"), "invalid"),
    (lambda d: d.update(special=[{"label": "No date", "closed": True}]), "invalid"),
])
def test_normaliser_refuses_to_lose_data(change, kind):
    data = seed_content("hours.json")
    change(data)
    _, problems = N.save(data, _entry("hours"), CMS)
    assert problems and problems[0]["kind"] == kind


def test_cli_refuses_and_writes_nothing(tmp_path, capsys):
    shutil.copytree(FIXTURE / "content", tmp_path / "content")
    shutil.copy(ROOT / ".pages.yml", tmp_path / ".pages.yml")
    p = tmp_path / "content" / "site.json"
    d = json.loads(p.read_text())
    d["business"]["fax"] = "510 555 0199"
    p.write_text(json.dumps(d, indent=4))
    before = {q: q.read_text() for q in (tmp_path / "content").rglob("*.json")}
    assert N.main(["--root", str(tmp_path)]) == 1
    assert "business.fax" in capsys.readouterr().err
    assert before == {q: q.read_text() for q in (tmp_path / "content").rglob("*.json")}
    del d["business"]["fax"]
    p.write_text(json.dumps(d, indent=4))
    assert N.main(["--root", str(tmp_path), "--check"]) == 1          # not in the CMS format yet
    assert N.main(["--root", str(tmp_path)]) == 0
    assert N.main(["--root", str(tmp_path), "--check"]) == 0
    assert p.read_text() == (FIXTURE / "content" / "site.json").read_text()


def test_a_date_field_without_an_empty_default_would_start_as_today():
    """The trap the `default: ""` on every date avoids."""
    f = {"name": "starts", "type": "date", "options": {"format": "yyyy-MM-dd"}}
    assert N.default_value(f, TODAY) == "2026-10-27"
    assert N.default_value({**f, "default": ""}, TODAY) == ""
    assert hours.parse_date(N.default_value(f, TODAY)) == TODAY


def test_every_photo_field_points_to_photo_prep():
    """Uploads over ~3.3 MB fail in the hosted editor, so every photo field's
    help must say where to shrink a photo — including fields added later."""
    import yaml
    cfg = yaml.safe_load((ROOT / ".pages.yml").read_text())
    comps = cfg.get("components") or {}
    missing, seen = [], 0

    def walk(fields, where):
        nonlocal seen
        for f in fields or []:
            spec = {**(comps.get(f["component"], {}) if f.get("component") else {}), **f}
            if spec.get("type") == "image":
                seen += 1
                if "photo-prep" not in (spec.get("description") or ""):
                    missing.append(f"{where} › {f.get('name')}")
            walk(spec.get("fields"), f"{where} › {f.get('name')}")
            for b in spec.get("blocks") or []:
                walk(b.get("fields"), f"{where} › {f.get('name')} › {b.get('name')}")

    def entries(items, where=""):
        for e in items or []:
            walk(e.get("fields"), f"{where}{e.get('name')}")
            entries(e.get("items"), f"{where}{e.get('name')} › ")
    entries(cfg.get("content"))
    for name, c in comps.items():
        walk(c.get("fields"), f"component {name}")
        for b in c.get("blocks") or []:
            walk(b.get("fields"), f"component {name} › {b.get('name')}")
    assert seen >= 10, f"only {seen} photo fields found — did the walker break?"
    assert not missing, "photo fields without the /photo-prep hint: " + ", ".join(missing)
