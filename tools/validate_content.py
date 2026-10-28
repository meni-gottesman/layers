#!/usr/bin/env python3
"""
Checks everything in content/ before the site is built, and explains any
problem in plain English.

  python3 tools/validate_content.py        # check, print, write build-report.json/.md
  python3 tools/build.py                   # runs this first; errors stop the build

Each problem is a dict:

  {"level": "error" | "warning", "where": "Opening hours",
   "field": "Saturday → Opens", "message": "…how to fix it…", "file": "content/hours.json"}

"where" and "field" use the labels the CMS shows (they come from the schemas in
tools/content.py, which .pages.yml mirrors). Files are checked as the build
reads them — through the defaults layer — because the CMS removes empty values
when it saves, so a missing key simply means "empty". Errors stop publishing; warnings
are reported but don't. Content that isn't shown — an unpublished page,
special, event or album, a switched-off announcement or Instagram section —
can't break the site, so its errors are reported as warnings, marked
"draft": true. The report lists drafts separately, so the manager's "worth a
look" list only holds things that are on the site.

Content that isn't on the site right now is treated the same way: a special
whose end date has passed, an event whose day has passed, a menu item
switched to "Hide from the website". Its problems are notes, so tidying old
photos out of the media library never stops an update.

Photo sizes: a photo placed before the CMS was checked by hand in the spot it
was placed in (src-img/existing-photos.json lists each photo with its spots).
Every other photo — and an old photo moved to a new spot — must be big enough
for its spot AFTER the crop: at least 1200 px wide for a full-width spot,
800 px elsewhere, judged on the crop the build will cut (the spot's shape and
the zoom), not just the long edge — a portrait photo in a wide band keeps only
a thin strip. A new photo must also open completely (a damaged upload is
caught here, with its name and spot, not later in the photo build).

Sections ("More sections") are named as the CMS shows them: "Page: Home ›
More sections → Section 2 (Photo and text) → Photo". A page of her own also
has its web address checked (lowercase letters, numbers and dashes; not one
the site uses itself). The page always stays at the address its file was
saved under, so an address changed afterwards, or one another of her pages
already had (the CMS then saves the new one as "<address>-1"), is a warning
that says where the page really is — never an error that would hold up
every other change. A page set to the main menu that doesn't fit there is in
the footer only, and that's a warning too.

Links to the site's own pages (/menu, /run-club) in buttons, the
announcement, the link-in-bio page, events and formatted text are checked
once every file has been read (check_links): one to a page that doesn't
exist is an error (a typo would publish a button to "page not found"); one
to a page that is switched off is a warning, and the page doesn't draw it
until that page is switched on again (render.Site.link_live).

The warnings that aren't about drafts are also listed on /edit ("Worth a
look"), the page the manager starts from (tools/build.py).

Importable: validate(root) -> [problem, …].
"""
import contextlib
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import content as C  # noqa: E402
import hours  # noqa: E402

try:
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
except ImportError:          # sizes can't be checked; existence still is
    Image = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIN_EDGE_FULL, MIN_EDGE = 1200, 800
INSTAGRAM_POST, BEHOLD_FEED = C.INSTAGRAM_POST, C.BEHOLD_FEED
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


DRAFT_NOTE = "(This isn’t shown on the site yet, so it won’t stop the update.)"
# How a collection is named in a message about two of its entries.
PLURALS = {"custom-pages": "of your pages"}
PAST_NOTE = "(This isn’t on the site any more, so it won’t stop the update.)"


class Context:
    """Collects problems for one content file.

    key: the file's content key ("pages/home", "menu", "events/run-club");
    at: where the field being checked sits in the file (kept up to date by
    the schema's Obj/List checks), so a photo knows its spot (content.photo_spot).
    existing: {photo: spots} placed before the CMS (src-img/existing-photos.json)."""

    def __init__(self, root, where, file, lenient=False, existing=None, key="", lenient_note=DRAFT_NOTE):
        self.root, self.where, self.file, self.lenient = pathlib.Path(root), where, file, lenient
        self.key, self.at = key, []
        self.lenient_note = lenient_note
        self.existing = existing or {}    # photos placed before the CMS, and where (no size rule there)
        self.too_small = set()            # photos already reported as too small
        self.problems = []
        self.links = []                   # links to the site's pages, for check_links (content.note_link)

    @contextlib.contextmanager
    def leniently(self, note):
        """Check part of a file (a hidden menu item) as if it weren't on the site."""
        saved = self.lenient, self.lenient_note
        self.lenient, self.lenient_note = True, note or DRAFT_NOTE
        try:
            yield
        finally:
            self.lenient, self.lenient_note = saved

    def spot(self):
        return C.photo_spot(self.key, self.at)

    def exempt(self, rel, spot):
        """A photo placed and checked by hand before the CMS, in this very spot."""
        return spot in self.existing.get(rel, ())

    def make(self, level, path, message, lenient=None, note=None):
        """A problem in this file. lenient/note: as when the field was read
        (a link checked at the end keeps the draft state of where it was)."""
        lenient = self.lenient if lenient is None else lenient
        if level == "error" and lenient:
            level = "warning"
            message += " " + (note or self.lenient_note)
        prob = {"level": level, "where": self.where, "field": " → ".join(p for p in path if p),
                "message": message, "file": self.file}
        if lenient:
            prob["draft"] = True          # not on the site: reported apart from the manager's list
        return prob

    def _add(self, level, path, message):
        self.problems.append(self.make(level, path, message))

    def error(self, path, message):
        self._add("error", path, message)

    def warning(self, path, message):
        self._add("warning", path, message)

    def type_error(self, path, value, kind):
        got = {str: "text", bool: "an on/off value", int: "a number", float: "a number", list: "a list",
               dict: "a group of fields", type(None): "nothing (null)"}.get(type(value), type(value).__name__)
        self.error(path, f"This should be {kind}, but the file has {got}. If you edited the file by hand, "
                         "undo that change; otherwise ask the developer.")

    def check_image(self, path, value, full_width=False, spot=None):
        f = C.image_file(value, self.root)
        if f is None:
            return self.error(path, f"“{value}” isn’t in the site’s photo folder. Choose or upload the photo "
                                    "through the CMS.")
        if not f.is_file():
            return self.error(path, f"The photo “{value}” can’t be found. Upload it again or choose another photo.")
        if f.suffix.lower() not in C.IMAGE_TYPES:
            return self.error(path, f"“{f.name}” isn’t a photo format the site can use. Use a JPEG, PNG, WebP or "
                                    "HEIC (iPhone) photo.")
        size = image_size(f)
        if size is None:
            return self.error(path, f"“{f.name}” can’t be opened — the file may be damaged. Upload it again.")
        # Photos placed before the CMS were checked by hand in their own spot;
        # every other photo (an upload, a file added to any src-img/ folder, or
        # an old photo picked for a new spot) must be big enough — and must
        # open completely: the header alone (the size) reads fine on a photo
        # whose upload broke off.
        rel = C.image_rel(value)
        exempt = self.exempt(rel, spot or self.spot())
        if not exempt and not decodes(f):
            self.too_small.add(rel)       # nothing more to say about it
            return self.error(path, f"“{f.name}” can’t be opened — the file may be damaged. Upload it again.")
        if not exempt and size != (0, 0):
            need = MIN_EDGE_FULL if full_width else MIN_EDGE
            if max(size) < need:
                self.too_small.add(C.image_rel(value))
                where = "a full-width spot" if full_width else "this spot"
                self.error(path, f"“{f.name}” is {size[0]}×{size[1]} pixels — too small for {where}, so it would "
                                 f"look blurry. It needs to be at least {need} pixels on its longest side. "
                                 "Upload a larger version (the original from the phone or camera is best).")

    def check_fit(self, path, value, aspect, zoom="auto", full_width=False, spot=None):
        """The photo after the build crops it to this spot's shape: big enough,
        and not just a thin strip of the original. Photos placed before the
        CMS in this spot, and ones already reported (missing, too small), are
        skipped."""
        rel = C.image_rel(value)
        f = C.image_file(rel, self.root) if rel else None
        if (f is None or self.exempt(rel, spot or self.spot()) or rel in self.too_small or not f.is_file()
                or f.suffix.lower() not in C.IMAGE_TYPES):
            return
        size = image_size(f)
        if not size or size == (0, 0):
            return
        a = C.parse_aspect(aspect)
        cw, ch = C.crop_size(size, a, C.ZOOM_FACTORS.get(zoom, 1.0))
        need = MIN_EDGE_FULL if full_width else MIN_EDGE
        shape = "wide" if a > 1.25 else "tall" if a < 0.9 else "square"
        better = "landscape (wider)" if a > size[0] / size[1] else "portrait (taller)"
        if cw < need:
            self.error(path, f"“{f.name}” is {size[0]}×{size[1]} pixels. This spot is {shape}, so the photo is "
                             f"cropped to {cw}×{ch} — it needs to be at least {need} pixels wide after cropping, "
                             f"or it would look blurry. Upload a larger photo, or a {better} one"
                             + (", or set Zoom to none." if zoom not in ("auto", "none") else "."))
        elif cw * ch < 0.5 * size[0] * size[1]:
            self.warning(path, f"Only part of “{f.name}” fits this spot: the photo is {size[0]}×{size[1]} and the "
                               f"spot is {shape}, so {cw}×{ch} of it shows (about "
                               f"{round(100 * cw * ch / (size[0] * size[1]))}%). A {better} photo would fit better "
                               "— or use Focus to choose which part shows.")


_SIZES, _DECODES = {}, {}


def image_size(f):
    """(w, h) of an image file as the build sees it (after the camera's
    rotation flag, like ImageOps.exif_transpose), (0, 0) when sizes can't be
    read here, None when unreadable."""
    if Image is None:
        return (0, 0)
    key = str(f)
    if key not in _SIZES:
        try:
            with Image.open(f) as im:
                w, h = im.size
                try:
                    if im.getexif().get(0x0112) in (5, 6, 7, 8):     # rotated 90°: swap
                        w, h = h, w
                except Exception:
                    pass
                _SIZES[key] = (w, h)
        except Exception:
            _SIZES[key] = None
    return _SIZES[key]


def decodes(f):
    """True when the whole photo can be decoded (not just its header). A
    JPEG is decoded at 1/8 scale (draft mode reads every byte but skips most
    of the work), so this stays quick for camera-size photos."""
    if Image is None:
        return True
    key = str(f)
    if key not in _DECODES:
        try:
            with Image.open(f) as im:
                if im.format == "JPEG":
                    im.draft("RGB", (max(1, im.width // 8), max(1, im.height // 8)))
                im.load()
            _DECODES[key] = True
        except Exception:
            _DECODES[key] = False
    return _DECODES[key]


def _rel(root, path):
    try:
        return str(pathlib.Path(path).relative_to(root))
    except ValueError:
        return str(path)


def _date(s):
    return hours.parse_date(s) if isinstance(s, str) and s.strip() else None


def _mins(s):
    return hours.parse_time(s) if isinstance(s, str) and s.strip() else None


def _str(d, k):
    v = d.get(k, "") if isinstance(d, dict) else ""
    return v.strip() if isinstance(v, str) else ""


def path_of(schema, dotted):
    """A field's CMS labels, as a message's path: path_of(C.SCHEMAS["site"],
    "business.phone") -> ["Address and contact", "Phone"]. The checks below
    take their labels from the schema rather than spelling them out, so a
    label renamed in tools/content.py (and .pages.yml) is renamed here too."""
    return C.field_labels(schema, dotted, {})


def label_of(schema, key):
    """The CMS label of one top-level field: label_of(schema, "ends") -> "Last day shown"."""
    return schema[key].label


# ---------------------------------------------------------------------------
# Checks that look at more than one field
# ---------------------------------------------------------------------------
def check_hours(d, v):
    weekly = d.get("weekly")
    if isinstance(weekly, dict):
        for day in hours.DAYS:
            x = weekly.get(day)
            if not isinstance(x, dict) or x.get("closed") is True:
                continue
            label = day.capitalize()
            o, c = x.get("open", ""), x.get("close", "")
            if not (isinstance(o, str) and o.strip()):
                v.error([label, "Opens"], f"{label} needs an opening time — or switch on "
                                                         "“Closed all day”.")
            if not (isinstance(c, str) and c.strip()):
                v.error([label, "Closes"], f"{label} needs a closing time — or switch on "
                                                          "“Closed all day”.")
            if _mins(o) is not None and _mins(c) is not None and _mins(c) <= _mins(o):
                v.error([label, "Opens"],
                        f"{label}’s opening time ({o}) is not before its closing time ({c}). Check the times "
                        "— they use the 24-hour clock, so 6pm is 18:00.")
    seen = {}
    for i, s in enumerate(d.get("special") or [] if isinstance(d.get("special"), list) else []):
        if not isinstance(s, dict):
            continue
        label = C.SCHEMAS["hours"]["special"].item_label(i, s)     # as the schema names it: number + summary
        date = _date(s.get("date"))
        if date and date in seen:
            v.error([label, "Date"], f"{s['date']} is listed twice in special hours (also as special hours "
                                     f"{seen[date]}). Keep one.")
        if date:
            seen[date] = i + 1
        if s.get("closed") is True:
            continue
        o, c = s.get("open", ""), s.get("close", "")
        if not (isinstance(o, str) and o.strip()) or not (isinstance(c, str) and c.strip()):
            v.error([label, "Opens"], "Give both an opening and a closing time — or switch on “Closed all day”.")
        elif _mins(o) is not None and _mins(c) is not None and _mins(c) <= _mins(o):
            v.error([label, "Opens"], f"The opening time ({o}) is not before the closing time ({c}). Check the "
                                      "times — they use the 24-hour clock, so 6pm is 18:00.")


def check_window(d, v, schema, start_key="starts", end_key="ends", today=None):
    """A start date and an end date (the announcement's, a special's), named
    with the schema's labels ("First day shown", "Last day shown")."""
    end_label = label_of(schema, end_key)
    a, b = _date(d.get(start_key)), _date(d.get(end_key))
    if a and b and b < a:
        v.error([end_label], f"The end date ({d[end_key]}) is before the start date ({d[start_key]}). "
                             "Check the dates.")
    elif b and today and b < today:
        v.warning([end_label], f"This ended on {d[end_key]}, so it no longer shows on the site.")


def check_link_pair(d, v, url_key, label_key, url_label, label_label, at=()):
    """A link needs its words and the words need a link. at: the labels of
    the group the pair sits in (a section), put before the field's label."""
    if _str(d, url_key) and not _str(d, label_key):
        v.error([*at, label_label], f"Add a label for the link — the words people tap (the link is set in "
                                    f"“{url_label}”).")
    if _str(d, label_key) and not _str(d, url_key):
        v.error([*at, url_label], f"“{d[label_key]}” needs a link. Add one, or clear the label.")


def check_site(d, v):
    site = C.SCHEMAS["site"]
    b = d.get("business") if isinstance(d.get("business"), dict) else {}
    email = _str(b, "public_email")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
        v.error(path_of(site, "business.public_email"), f"“{email}” doesn’t look like an email address.")
    phone = _str(b, "phone")
    if phone and not re.fullmatch(r"\+?[\d\s().-]{7,20}", phone):
        v.error(path_of(site, "business.phone"), f"“{phone}” doesn’t look like a phone number. Use digits, for "
                                                "example (510) 555-0123.")
    social = d.get("social") if isinstance(d.get("social"), dict) else {}
    handle = _str(social, "instagram_handle")
    if handle and not re.fullmatch(r"@?[A-Za-z0-9._]{1,30}", handle):
        v.error(path_of(site, "social.instagram_handle"), f"“{handle}” isn’t an Instagram handle. Write just the "
                                                         "name, for example layerssuperfoodbar — no @ or web "
                                                         "address.")
    # delivery links show on Visit and /links under the service's name, so a
    # link to somewhere else would be labelled wrongly
    ordering = d.get("ordering") if isinstance(d.get("ordering"), dict) else {}
    for key, name, host in (("doordash_url", "DoorDash", "doordash.com"),
                            ("ubereats_url", "Uber Eats", "ubereats.com")):
        u = _str(ordering, key)
        h = (urllib.parse.urlsplit(u).hostname or "") if u.startswith("https://") else ""
        if h and not (h == host or h.endswith("." + host)):
            v.warning(path_of(site, f"ordering.{key}"), f"“{u}” doesn’t look like a {name} link ({host}). It "
                                                       f"shows on the site as “{name}”, so check it’s the right "
                                                       "link.")
    an = d.get("analytics") if isinstance(d.get("analytics"), dict) else {}
    token = _str(an, "cloudflare_web_analytics_token")
    if token and not re.fullmatch(r"[0-9a-fA-F]{32}", token):
        v.error(path_of(site, "analytics.cloudflare_web_analytics_token"),
                "This doesn’t look like a Cloudflare Web Analytics token, which is 32 letters and numbers "
                "(0–9, a–f). Copy it again from Cloudflare → Web Analytics → your site.")


def check_announcement(d, v, today):
    ann = C.SCHEMAS["announcement"]
    if d.get("enabled") is True and not _str(d, "message"):
        v.error([label_of(ann, "message")], "The bar is switched on but has no message. Write one, or switch the "
                                         "bar off.")
    check_link_pair(d, v, "link_url", "link_label", label_of(ann, "link_url"), label_of(ann, "link_label"))
    check_window(d, v, ann, today=today)


def check_instagram(d, v):
    curated = d.get("curated") if isinstance(d.get("curated"), list) else []
    for i, p in enumerate(curated):
        if _str(p, "image"):
            v.check_fit([f"Post {i + 1}", "Photo"], p["image"], C.ENTRY_SLOTS["instagram"][1], spot="instagram")
        u = _str(p, "post_url")
        if u and not INSTAGRAM_POST.fullmatch(u):
            v.error([f"Post {i + 1}", "Instagram post link"],
                    f"“{u}” isn’t a link to an Instagram post. Open the post on Instagram, tap ⋯ → Copy link, "
                    "and paste it here (it looks like https://www.instagram.com/p/…/).")
    urls = [_str(p, "post_url") for p in d.get("curated") or [] if isinstance(p, dict)]
    dups = {u for u in urls if u and urls.count(u) > 1}
    for u in sorted(dups):
        v.warning(["Hand-picked posts"], f"The post {u} is listed more than once.")
    feed = _str(d, "behold_feed_url")
    if feed and not BEHOLD_FEED.fullmatch(feed):
        v.error(["Behold feed link"], f"“{feed}” isn’t a Behold feed link. In Behold, open your feed → "
                                      "“Embed/JSON” and copy the link that starts with https://feeds.behold.so/.")
    if d.get("mode") == "auto" and not feed:
        v.warning(["Posts to show"], "Automatic mode needs the Behold feed link; until it’s added, the "
                                     "hand-picked posts are shown.")
    # A grid of one or two posts blows each photo up across the page. (In
    # automatic mode a feed with fewer than 3 posts already falls back to the
    # hand-picked ones, so this is about the number and the hand-picked list.)
    count = d.get("count") if isinstance(d.get("count"), int) and not isinstance(d.get("count"), bool) else 4
    usable = [i for i, p in enumerate(curated) if _str(p, "image") and _str(p, "post_url")]
    shows = min(count, len(usable)) if d.get("mode") != "auto" or not feed else count
    # "Add an item" puts a new post at the END of the list, and the grid shows
    # the first `count` (tools/instagram.py curated_posts): without this, a post
    # added the natural way would never appear, and nothing would say why. An
    # error, so the update waits and the note says exactly what to do. (With
    # automatic posts the hand-picked ones are only the backup: no error.)
    count_label = label_of(C.SCHEMAS["instagram"], "count")
    if d.get("enabled") is True and (d.get("mode") != "auto" or not feed):
        more = (f", or set “{count_label}” to {min(len(usable), 12)}" if count < 12 else "")
        for i in usable[count:]:
            v.error([f"Post {i + 1}"], f"This post isn’t on the website: the grid shows the first {count} posts in "
                                       f"this list (“{count_label}”). Drag this post up, above one you’d like to "
                                       f"replace (or remove an old one){more}.")
    if d.get("enabled") is True and 0 < shows < 3:
        v.warning(["Number of posts"] if count < 3 else ["Hand-picked posts"],
                  f"Only {shows} post{'s' if shows != 1 else ''} will show. The grid looks best with at least 3 "
                  "(4 or 6 is ideal)" + (" — set “Number of posts” to 3 or more." if count < 3 else
                                         " — add another hand-picked post."))


def check_menu(d, v, root):
    # Square items currently on the menu, from the cached store data
    sync = C.load_tool("sync-menu-from-store.py")
    try:
        known = sync.menu_items(root)
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        known = None
    items = d.get("items") if isinstance(d.get("items"), list) else []
    seen, names = {}, {}
    previous = _previous_square_photos(root)
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        sid = _str(it, "square_id")
        label = C.menu_item_label(i, it)
        hidden = it.get("hidden") is True
        if sid in seen:
            v.error([label, "Square ID"], f"This Square item is listed twice (also as item {seen[sid]}). "
                                          "Remove one of them.")
        seen[sid] = i + 1
        if known is not None and sid and sid not in known:
            v.warning([label], "Square no longer lists this item, so it isn’t shown. It can be removed from "
                               "this list.")
        # two items shown under the same name (each keeps its own photo — the
        # sync gives them separate photo slots — but customers can't tell them apart)
        if known is not None and sid in known and it.get("hidden") is not True:
            shown = _str(it, "display_name") or sync.split_name(known[sid])[0]
            key = re.sub(r"\s+", " ", shown).casefold()
            if key in names:
                v.warning([label, "Name on the website"],
                          f"Another menu item ({names[key]}) is also shown as “{shown}”. Customers would see "
                          "two items with the same name — give one of them a different name on the website.")
            else:
                names[key] = _str(it, "square_name") or label
        if _str(it, "photo"):
            with (v.leniently(MENU_HIDDEN_NOTE) if hidden else contextlib.nullcontext()):
                v.check_fit([label, "Photo"], it["photo"], C.ENTRY_SLOTS["menu"][1], it.get("zoom", "auto"),
                            spot="menu")
        elif not hidden and sid in previous and not (root / previous[sid]).is_file():
            # The item's own Square photo (src-img/menu/, downloaded by the menu
            # refresh) was deleted in the media library: no field points at it,
            # so nothing else would say why the card lost its photo.
            name = _str(it, "display_name") or _str(it, "square_name") or label
            v.warning([label, "Photo"], f"The Square photo for {name} ({previous[sid]}) was deleted from the "
                                        "photo library, so the menu shows it without a photo. Use “Undo my last "
                                        "change” to bring it back — or it comes back by itself with the next menu "
                                        "refresh from Square.")
    if known is not None:
        missing = [n for k, n in known.items() if k not in seen]
        if missing:
            # built outside the f-string: a backslash inside an f-string
            # expression is a SyntaxError before Python 3.12
            shown = ", ".join(re.sub(r"\s+", " ", n) for n in missing[:3])
            v.warning(path_of(C.SCHEMAS["menu"], "items"), f"{len(missing)} Square item(s) aren’t in this list "
                                 f"({shown}{'…' if len(missing) > 3 else ''}), so the menu shows them with "
                                 "Square’s own name and photo. If you removed one to take it off the menu, use "
                                 "“Undo my last change” and switch on “Hide from the website” instead; otherwise "
                                 "they’re added here on the next menu refresh.")


MENU_HIDDEN_NOTE = "(This item is hidden from the website, so it won’t stop the update.)"


def _previous_square_photos(root):
    """{square id: src-img/menu/… photo} from the menu the last build made
    (data/menu-fallback.json) — the Square product photos items were using."""
    try:
        data = json.loads((pathlib.Path(root) / "data" / "menu-fallback.json").read_text(encoding="utf-8"))
        return {it["id"]: it["image_source"] for c in data.get("categories", []) for it in c.get("items", [])
                if isinstance(it.get("image_source"), str) and it["image_source"].startswith("src-img/menu/")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def check_special(d, v, today):
    schema = C.COLLECTIONS["specials"][1]
    check_window(d, v, schema, today=today)
    if _str(d, "image"):
        v.check_fit([label_of(schema, "image")], d["image"], C.ENTRY_SLOTS["specials"][1], spot="specials")
    if _str(d, "image") and not _str(d, "image_alt"):
        v.error([label_of(schema, "image_alt")], "Describe the photo in a few words for people who can’t see it — "
                                              "for example, what’s in the cup.")
    price = _str(d, "price")
    if price and not re.fullmatch(r"\$?\d{1,3}(\.\d{2})?", price):
        v.error(["Price"], f"“{price}” isn’t a price. Write it like 9.50 (or leave it empty).")
    # the order button (CMS_SPEC §11): "link" needs the link; a link with
    # another button choice is simply not used, so only a warning
    mode, label = d.get("order_button"), C.ORDER_BUTTON_LABELS
    if mode == "link" and not _str(d, "order_url"):
        v.error(["Order link"], f"The order button is set to “{label['link']}”, but there’s no order link. Paste "
                                "the link people should order from (starting with https://), or set the order "
                                f"button to “{label['square']}” or “{label['none']}”.")
    elif mode in ("none", "square") and _str(d, "order_url"):
        v.warning(["Order link"], f"This link isn’t used, because the order button is set to “{label[mode]}”. "
                                  f"To use it, set the order button to “{label['link']}”.")
    hl = d.get("highlights")
    if isinstance(hl, list) and len(hl) > 4:
        v.warning(["Highlights"], f"There are {len(hl)} highlights; the card has room for about 3.")


def check_event(d, v):
    schema = C.COLLECTIONS["events"][1]
    o, c = _mins(d.get("start_time")), _mins(d.get("end_time"))
    if o is not None and c is not None and c <= o:
        v.error([label_of(schema, "end_time")], f"The end time ({d['end_time']}) is not after the start time "
                                             f"({d['start_time']}). Times use the 24-hour clock, so 6pm is 18:00.")
    if _str(d, "end_time") and not _str(d, "start_time"):
        v.error([label_of(schema, "start_time")], "Add a start time too (or clear the end time).")
    if _str(d, "image") and not _str(d, "image_alt"):
        v.error([label_of(schema, "image_alt")], "Describe the photo in a few words for people who can’t see it.")
    check_link_pair(d, v, "link_url", "link_label", label_of(schema, "link_url"), label_of(schema, "link_label"))


def check_album(d, v):
    photos = d.get("photos")
    if isinstance(photos, list) and not photos:
        v.warning(["Photos"], "This album has no photos yet, so it isn’t shown.")


def check_page_photos(key, data, schema, v, specs):
    """Every photo spot a page fills (src-img/slot-specs.json bindings), with
    the spot's real shape and the photo's zoom."""
    for spec in specs.values():
        if not isinstance(spec, dict) or not spec.get("content"):
            continue
        src, field = spec["content"].split(":", 1)
        if src != key:
            continue
        try:
            photo = C.get_path(data, field)
            labels = C.field_labels(schema, field, data)
        except (KeyError, IndexError, TypeError, ValueError):
            continue          # a broken shape is reported by the schema checks
        if isinstance(photo, dict):
            image, zoom, labels = photo.get("image"), photo.get("zoom", "auto"), labels + ["Photo"]
        else:
            image, zoom = photo, "auto"
        if isinstance(image, str) and image.strip():
            v.check_fit(labels, image, spec.get("aspect", 1), zoom if isinstance(zoom, str) else "auto",
                        full_width=spec.get("widths") == "full", spot=spec["content"])


def check_sections(key, data, schema, v):
    """A page's "More sections" (and the sections of a page of her own): a
    text section with nothing in it, a button's words without its link (or
    the other way round), and every photo against the shape of its spot —
    the names are the CMS's, "More sections → Section 2 (Photo and text) →
    Photo". The fields themselves (required, lengths, links, photo files)
    are checked by the schema (content.Blocks)."""
    node, sections = schema.get("sections"), data.get("sections")
    if not isinstance(node, C.Blocks) or not isinstance(sections, list):
        return
    for i, s in enumerate(sections):
        if node.block_of(s) is None:
            continue                        # already reported by the schema check
        here = [node.label, node.item_label(i, s)]
        if s["type"] == "text" and not C.text_section_has_words(s):
            # picked by mistake after "Add an item" (it has no required box, so
            # the CMS saves it): not drawn, and never a reason to hold up an update
            v.warning(here, "This text section is empty, so it isn’t on the website. Write a heading or some "
                            "text — or remove the section with the bin icon.")
        elif s["type"] == "photo-text":
            check_link_pair(s, v, "button_link", "button_label", "Button link", "Button text", at=here)
    for p in C.section_photos(C.sections_prefix(key), sections):
        image = p["photo"].get("image")
        if not (isinstance(image, str) and image.strip()):
            continue
        zoom = p["photo"].get("zoom", "auto")
        labels = C.field_labels(schema, ".".join(map(str, p["at"])) + ".image", data)
        v.check_fit(labels, image, p["aspect"], zoom if isinstance(zoom, str) else "auto",
                    full_width=p["full_width"], spot=C.photo_spot(key, p["at"]))


def _page_name(d):
    t = d.get("title") if isinstance(d, dict) else ""
    return f"“{t.strip()}”" if isinstance(t, str) and t.strip() else "another page"


def check_custom_page(d, v, stem, others=None):
    """A page of her own: its web address, the top photo, and a page with
    nothing on it yet. others: {file name (stem): data} of all her pages.

    The page is at its FILE's address (stem): the CMS names the file from
    "Web address" when the page is first saved and can't rename it. So a
    "Web address" that no longer matches doesn't move the page — it's a
    warning that says where the page is (an error would hold up every other
    change until she found the note). Two ways it happens:
      * the address was already another page's (even a switched-off one):
        the CMS quietly saves the new page as "<address>-1";
      * the box was changed after the first Save."""
    schema = C.COLLECTIONS["custom-pages"][1]
    address = label_of(schema, "address")
    raw = d.get("address") if isinstance(d.get("address"), str) else ""
    addr = raw.strip()
    others = others or {}
    if stem in C.RESERVED_ADDRESSES:              # the CMS refuses these: only a file made by hand
        v.error([address], f"/{stem} is already used by the website itself, so this page can’t have it. Make a "
                           f"new page with another web address — for example our-{stem} or {stem}-2 — then "
                           "delete this one.")
    elif addr and not C.ADDRESS.fullmatch(raw):   # as typed: a space is refused in the CMS too
        better = re.sub(r"[^a-z0-9]+", "-", addr.lower()).strip("-") or "summer-menu"
        v.error([address], f"“{addr}” can’t be used in a web address. Use only lowercase letters, numbers "
                           f"and dashes, with no spaces — for example {better}.")
    elif addr and addr != stem:
        if addr in others and re.fullmatch(re.escape(addr) + r"-\d+", stem):
            state = "" if others[addr].get("published", True) is not False else ", switched off"
            v.warning([address], f"Another of your pages ({_page_name(others[addr])}{state}) already has the web "
                                 f"address /{addr}, so the editor saved this one at /{stem} — that’s where it is on "
                                 f"the website. To keep it there, change “{address}” to {stem}. (Two pages can’t "
                                 f"share an address: for this page at /{addr}, delete the other page, then make "
                                 "this one again.)")
        else:
            v.warning([address], f"A page stays at the web address it had when it was first saved, so this page is "
                                 f"still at /{stem} — changing “{address}” doesn’t move it. Change it back to "
                                 f"{stem}. (For a new address, make a new page with it, then delete this one.)")
    photo = d.get("photo") if isinstance(d.get("photo"), dict) else {}
    image = _str(photo, "image")
    if image and not _str(photo, "alt"):
        v.error(path_of(schema, "photo.alt"), C.ALT_MISSING)
    if image:
        zoom = photo.get("zoom", "auto")
        v.check_fit(path_of(schema, "photo.image"), photo["image"], C.CUSTOM_TOP_PHOTO[0],
                    zoom if isinstance(zoom, str) else "auto", full_width=True, spot="custom-pages")
    sections = d.get("sections")
    if not image and not _str(d, "intro") and not (isinstance(sections, list) and sections):
        v.warning([], "This page has only its title so far. Add a short intro, a top photo or some sections "
                      "(under “More sections”).")


def check_custom_menus(problems, pages):
    """A page set to "Main menu and footer" that doesn't fit in the main menu
    is in the footer only (content.custom_page_links), and the manager is
    told why and what to do. pages: {content key: normalised data} of her pages."""
    schema = C.COLLECTIONS["custom-pages"][1]
    show_in, name_box = label_of(schema, "show_in"), label_of(schema, "menu_title")
    loaded = [{**d, "slug": k.split("/", 1)[1]} for k, d in pages.items()]
    links = C.custom_page_links(loaded)
    names = " and ".join(f"“{C.menu_name(p)}”" for p in links["menu"])

    def warn(p, field, message):
        problems.append({"level": "warning", "where": f"Your page: {p['title'].strip()}", "field": field,
                         "message": message, "file": f"content/custom-pages/{p['slug']}.json"})
    for p, why in links["overflow"]:
        if why == "full":
            warn(p, show_in, f"The main menu has room for {C.MAX_MENU_PAGES} of your pages and already has "
                             f"{names} (the first 2 by page title, A–Z), so this page is in the footer only. To put it in "
                             f"the main menu, set one of those to “{C.SHOW_IN_LABELS['footer']}”.")
        elif why == "long":
            n = len(C.menu_name(p))
            warn(p, name_box, f"This page’s title is {n} characters, and names in the main menu can have up to "
                              f"{C.MENU_NAME_MAX}, so the page is in the footer only for now. Write a shorter "
                              f"“{name_box}” (for example Run Club) to put it in the main menu.")
        else:
            warn(p, name_box, f"Together with {names}, this page’s name doesn’t fit in the main menu, so the page is "
                              f"in the footer only for now. A shorter “{name_box}” for either page makes room.")


# The pages without a content file, as a message names them.
TOOL_NAMES = {"photo-prep": "Prepare a photo", "brand": "Brand kit", "edit": "Edit the website", "order": "Order"}


def site_pages(by_key):
    """{path: (switched on, its name in a message)} for every page the website
    makes: the site's own (render.PAGE_CONFIG, its drafts and switches) and
    the pages of her own. by_key: {content key: normalised data}."""
    import render
    out = {}
    for key, cfg in render.PAGE_CONFIG.items():
        if cfg["out"] == "404":
            continue
        src = cfg.get("content")
        data = by_key.get(src) if src else None
        on = cfg.get("published", True) is not False and (data is None or C.page_published(data))
        if src == "links":
            on = on and isinstance(data, dict) and data.get("enabled") is not False
        label = (C.PAGES.get(src.split("/", 1)[1]) if src and src.startswith("pages/")
                 else C.WHERE.get(src) if src else TOOL_NAMES.get(key, key.capitalize()))
        out["/" if cfg["out"] == "index" else f"/{cfg['out']}"] = (
            on, f"{'' if label.startswith('The ') else 'the '}{label} page")
    for key, d in by_key.items():
        if key.startswith("custom-pages/"):
            stem = key.split("/", 1)[1]
            if C.ADDRESS.fullmatch(stem) and stem not in C.RESERVED_ADDRESSES:
                out[f"/{stem}"] = (d.get("published") is True, f"your page {_page_name(d)}")
    return out


def check_links(problems, found, by_key):
    """Every link to one of the site's own pages (content.note_link: buttons,
    the announcement, /links, events, [words](/a-page) in formatted text).
    found: [(Context, link)]. A page that doesn't exist: an error, with the
    likely fix — a button to "page not found" mustn't go live. A page that's
    switched off: a warning; the link isn't drawn until it's switched on."""
    import difflib
    try:
        pages = site_pages(by_key)
    except ImportError:                 # the page list lives in render.py (needs jinja2)
        return
    for v, link in found:
        path, url = C.site_page(link["url"]), link["url"]
        if path in pages:
            on, name = pages[path]
            if not on:
                problems.append(v.make("warning", link["path"], f"This links to {path} — {name}, which is switched "
                                       "off — so the link isn’t shown on the website for now. It comes back by "
                                       "itself when that page is switched on; or link to another page.",
                                       link["lenient"], link["note"]))
            continue
        if path.lower() in pages:
            hint = f" Web addresses use lowercase letters: write {path.lower()}."
        elif path.startswith("/layers/") and path[len("/layers"):] in pages:
            hint = f" Leave out /layers (that’s only the preview’s address): write {path[len('/layers'):]}."
        else:
            close = difflib.get_close_matches(path, [p for p in pages if p != "/"], n=1, cutoff=0.75)
            hint = (f" Did you mean {close[0]}?" if close else
                    " Check the spelling — for example /menu, /visit, or the web address of one of your own pages.")
        problems.append(v.make("error", link["path"], f"{url} isn’t a page on the website, so this link would lead "
                               f"to “page not found”.{hint}", link["lenient"], link["note"]))


def check_navigation(problems, data_by_key, root):
    """A page switched on that no menu links to can only be found by its address."""
    try:
        import render
    except ImportError:
        return
    linked = {href for links in (render.HEADER_LINKS, render.DRAWER_LINKS, render.FOOTER_LINKS)
              for _, href, _ in links}
    for key, cfg in render.PAGE_CONFIG.items():
        src = cfg.get("content") or ""
        page = data_by_key.get(src)
        if (page is None or "published" not in page or page.get("published") is not True
                or cfg.get("noindex") or f"/{cfg['out']}" in linked):
            continue
        problems.append({"level": "warning", "where": f"Page: {C.PAGES.get(src.split('/', 1)[-1], key)}",
                         "field": "Published", "file": f"content/{src}.json",
                         "message": "This page is published, but no menu on the site links to it yet, so visitors "
                                    f"can only reach it at {render.SITE_URL}/{cfg['out']}. Ask the developer to "
                                    "add it to the navigation."})


# ---------------------------------------------------------------------------
def validate(root=ROOT, today=None):
    """Check every content file. Returns a list of problems (errors first)."""
    root = pathlib.Path(root)
    today = today or hours.shop_today()
    problems = []
    slugs, by_key, links = {}, {}, []
    existing = C.existing_photos(root)
    # her pages, read up front: one page's address check needs the others
    # (the CMS saves a page whose address is taken as "<address>-1")
    custom = {}
    for key, path, schema, _ in C.files(root):
        if key.startswith("custom-pages/"):
            with contextlib.suppress(C.ContentError):
                d = C.read_json(path)
                if isinstance(d, dict):
                    custom[path.stem] = C.normalise(schema, d)
    try:
        specs = json.loads((root / "src-img" / "slot-specs.json").read_text())
    except (OSError, ValueError):
        specs = {}
    for key, path, schema, where in C.files(root):
        rel = _rel(root, path)
        try:
            data = C.read_json(path)
        except C.ContentError as e:
            problems.append({"level": "error", "where": where, "field": "", "message": str(e), "file": rel})
            continue
        if not isinstance(data, dict):
            problems.append({"level": "error", "where": where, "field": "",
                             "message": "This file should hold a group of fields ({ … }). Undo the last change.",
                             "file": rel})
            continue
        # Check the file as the build will read it: the CMS drops empty values
        # ("", [], {}) when it saves, so a missing key means "empty" and gets
        # its default — and then must pass the same checks.
        data = C.normalise(schema, data)
        by_key[key] = data
        coll = key.split("/", 1)[0] if "/" in key and not key.startswith("pages/") else None
        shown, note = True, DRAFT_NOTE
        if key.startswith("pages/") or coll in ("specials", "events", "albums", "custom-pages"):
            shown = data.get("published", True) is not False
        elif key in ("announcement", "instagram"):
            shown = data.get("enabled") is True
        elif key == "links":
            shown = data.get("enabled", True) is not False
        # dated entries the site no longer shows (the build and main.js drop
        # them): their problems are notes too, like a draft's
        if shown and coll == "specials" and _date(data.get("ends")) and _date(data["ends"]) < today:
            shown, note = False, PAST_NOTE
        elif shown and coll == "events" and _date(data.get("date")) and _date(data["date"]) < today:
            shown, note = False, PAST_NOTE
        if coll:          # a nicer "where" once we know the title
            title = data.get("title") or data.get("name")
            if isinstance(title, str) and title.strip():
                where = f"{where.split(':')[0]}: {title.strip()}"
        v = Context(root, where, rel, lenient=not shown, existing=existing, key=key, lenient_note=note)
        for k, f in schema.items():
            v.at = [k]
            f.check(data[k], v, [f.label] if getattr(f, "in_path", True) else [])
        v.at = []
        check_page_photos(key, data, schema, v, specs)
        check_sections(key, data, schema, v)
        if key == "site":
            check_site(data, v)
        elif key == "hours":
            check_hours(data, v)
        elif key == "announcement":
            check_announcement(data, v, today)
        elif key == "instagram":
            check_instagram(data, v)
        elif key == "menu":
            check_menu(data, v, root)
        elif coll == "specials":
            check_special(data, v, today)
        elif coll == "events":
            check_event(data, v)
        elif coll == "albums":
            check_album(data, v)
        elif coll == "custom-pages":
            check_custom_page(data, v, path.stem, custom)
        if coll:
            stem = path.stem
            name_label = schema[C.WEB_NAME_FIELDS[coll]].label
            if not SLUG.fullmatch(stem):
                # The CMS makes the file name from the name and can't rename an
                # entry, so the fix in the CMS is a new entry with a usable name.
                v.error([name_label], f"The file name “{path.name}” can’t be used in a web address (it needs "
                                      "letters or numbers, and only lowercase letters, numbers and dashes). In the "
                                      "CMS, delete this entry and create it again with a name that has letters or "
                                      "numbers — the web address is made from the name.")
            k2 = (coll, stem.lower())
            if k2 in slugs:
                v.error([name_label], f"Two {PLURALS.get(coll, coll)} share the web address “{stem}” ({slugs[k2]} "
                                      f"and {path.name}). Delete one of them and create it again with a different "
                                      "name.")
            slugs[k2] = path.name
        problems += v.problems
        links += [(v, link) for link in v.links]
    check_links(problems, links, by_key)
    check_navigation(problems, by_key, root)
    check_custom_menus(problems, {k: d for k, d in by_key.items() if k.startswith("custom-pages/")})
    links = by_key.get("links")
    if isinstance(links, dict) and links.get("enabled") is False:
        # Not a draft note: the page is printed on things and linked from Instagram.
        problems.append({"level": "warning", "where": C.WHERE["links"], "field": "Publish the page",
                         "file": "content/links.json",
                         "message": "The link-in-bio page is switched off, but your Instagram bio link and the "
                                    "printed QR codes (on the Brand kit page) go to /links — while it’s off, they "
                                    "show “page not found”. Switch it back on, or change the bio link."})
    return sorted(problems, key=lambda p: (p["level"] != "error", bool(p.get("draft"))))


def format_problems(problems):
    lines = []
    for p in problems:
        where = p["where"] + (f" › {p['field']}" if p["field"] else "")
        level = "ERROR" if p["level"] == "error" else "draft" if p.get("draft") else "warning"
        lines.append(f"  {level:7s}  {where}\n           {p['message']}")
    return "\n".join(lines)


def split_problems(problems):
    """(errors, warnings about the live site, notes on drafts that aren't shown)."""
    errors = [p for p in problems if p["level"] == "error"]
    warnings = [p for p in problems if p["level"] == "warning" and not p.get("draft")]
    drafts = [p for p in problems if p["level"] == "warning" and p.get("draft")]
    return errors, warnings, drafts


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>!|~])")


def md_text(s):
    """Text for build-report.md, which GitHub shows as Markdown (the run
    summary, and the public "Website update didn't publish" issue). Messages
    quote what the manager typed, so nothing in them may turn into a link, an
    image, HTML or formatting — and an @handle or #number in an event's name
    must not notify a stranger or link an issue: Markdown specials are
    backslash-escaped, and a word joiner (invisible) follows each @ and #."""
    s = _MD_SPECIAL.sub(r"\\\1", str(s))
    return s.replace("@", "@\u2060").replace("#", "#\u2060").replace("\n", " ")


def write_report(root, problems, status, steps=None, extra=None):
    """build-report.json (for tools) and build-report.md (for people; the CI
    posts it as the "Website update didn't publish" issue). In the .md every
    problem's text goes through md_text()."""
    root = pathlib.Path(root)
    errors, warnings, drafts = split_problems(problems)
    report = {"status": status, "generated": dt.datetime.now(hours.SHOP_TZ).isoformat(timespec="seconds"),
              "errors": len(errors), "warnings": len(warnings), "drafts": len(drafts),
              "problems": problems, "steps": steps or []}
    report.update(extra or {})
    (root / "build-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")

    md = []
    if status == "passed":
        md.append("# Website update: published ✓\n")
        md.append("Everything checked out." + (" A few things to look at when you have a moment:" if warnings else ""))
    else:
        md.append("# Website update didn’t publish\n")
        md.append("The live site has **not** changed. Fix the problem(s) below in the CMS and save again — "
                  "the site publishes automatically once everything checks out.")
    def line(p):
        where = f"**{md_text(p['where'])}**" + (f" › {md_text(p['field'])}" if p["field"] else "")
        return f"- {where}: {md_text(p['message'])}"

    for title, items in (("What needs fixing", errors), ("Worth a look (these don’t stop the update)", warnings)):
        if not items:
            continue
        md.append(f"\n## {title}\n")
        md.extend(line(p) for p in items)
    if drafts:      # content that isn't on the site: folded away, so it never nags
        md.append("\n<details><summary>Not on the site — notes on drafts, hidden items and past dates "
                  f"({len(drafts)})</summary>\n")
        md.extend(line(p) for p in drafts)
        md.append("\n</details>")
    if steps:
        md.append("\n<details><summary>Build steps (for the developer)</summary>\n")
        for s in steps:
            md.append(f"- {s['name']}: {s['status']}" + (f" — {md_text(s['detail'])}" if s.get("detail") else ""))
        md.append("\n</details>")
    (root / "build-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main():
    problems = validate(ROOT)
    errors, warnings, drafts = split_problems(problems)
    if problems:
        print(format_problems(problems))
    write_report(ROOT, problems, "failed" if errors else "passed",
                 steps=[{"name": "validate", "status": "failed" if errors else "ok"}])
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s), {len(drafts)} note(s) on unpublished "
          "content. Report: build-report.md")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
