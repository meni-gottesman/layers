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

    def _add(self, level, path, message):
        if level == "error" and self.lenient:
            level = "warning"
            message += " " + self.lenient_note
        prob = {"level": level, "where": self.where, "field": " → ".join(p for p in path if p),
                "message": message, "file": self.file}
        if self.lenient:
            prob["draft"] = True          # not on the site: reported apart from the manager's list
        self.problems.append(prob)

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


def check_window(d, v, start_key="starts", end_key="ends", start_label="Starts", end_label="Ends", today=None):
    a, b = _date(d.get(start_key)), _date(d.get(end_key))
    if a and b and b < a:
        v.error([end_label], f"The end date ({d[end_key]}) is before the start date ({d[start_key]}). "
                             "Check the dates.")
    elif b and today and b < today:
        v.warning([end_label], f"This ended on {d[end_key]}, so it no longer shows on the site.")


def check_link_pair(d, v, url_key, label_key, url_label, label_label):
    if _str(d, url_key) and not _str(d, label_key):
        v.error([label_label], f"Add a label for the link — the words people tap (the link is set in "
                               f"“{url_label}”).")
    if _str(d, label_key) and not _str(d, url_key):
        v.error([url_label], f"“{d[label_key]}” needs a link. Add one, or clear the label.")


def check_site(d, v):
    b = d.get("business") if isinstance(d.get("business"), dict) else {}
    email = _str(b, "public_email")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
        v.error(["Business", "Public email"], f"“{email}” doesn’t look like an email address.")
    phone = _str(b, "phone")
    if phone and not re.fullmatch(r"\+?[\d\s().-]{7,20}", phone):
        v.error(["Business", "Phone"], f"“{phone}” doesn’t look like a phone number. Use digits, for example "
                                       "(510) 555-0123.")
    social = d.get("social") if isinstance(d.get("social"), dict) else {}
    handle = _str(social, "instagram_handle")
    if handle and not re.fullmatch(r"@?[A-Za-z0-9._]{1,30}", handle):
        v.error(["Social", "Instagram handle"], f"“{handle}” isn’t an Instagram handle. Write just the name, "
                                                "for example layerssuperfoodbar — no @ or web address.")
    # delivery links show on Visit and /links under the service's name, so a
    # link to somewhere else would be labelled wrongly
    ordering = d.get("ordering") if isinstance(d.get("ordering"), dict) else {}
    for key, label, host in (("doordash_url", "DoorDash link", "doordash.com"),
                             ("ubereats_url", "Uber Eats link", "ubereats.com")):
        u = _str(ordering, key)
        h = (urllib.parse.urlsplit(u).hostname or "") if u.startswith("https://") else ""
        if h and not (h == host or h.endswith("." + host)):
            v.warning(["Ordering", label], f"“{u}” doesn’t look like a {label.rsplit(' ', 1)[0]} link "
                                           f"({host}). It shows on the site as “{label.rsplit(' ', 1)[0]}”, so "
                                           "check it’s the right link.")
    an = d.get("analytics") if isinstance(d.get("analytics"), dict) else {}
    token = _str(an, "cloudflare_web_analytics_token")
    if token and not re.fullmatch(r"[0-9a-fA-F]{32}", token):
        v.error(["Analytics", "Cloudflare Web Analytics token"],
                "This doesn’t look like a Cloudflare Web Analytics token, which is 32 letters and numbers "
                "(0–9, a–f). Copy it again from Cloudflare → Web Analytics → your site.")


def check_announcement(d, v, today):
    if d.get("enabled") is True and not _str(d, "message"):
        v.error(["Message"], "The bar is switched on but has no message. Write one, or switch the bar off.")
    check_link_pair(d, v, "link_url", "link_label", "Link", "Link label")
    check_window(d, v, today=today)


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
    usable = [p for p in curated if _str(p, "image") and _str(p, "post_url")]
    shows = min(count, len(usable)) if d.get("mode") != "auto" or not feed else count
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
            v.warning(["Items"], f"{len(missing)} Square item(s) aren’t in this list "
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
    check_window(d, v, today=today)
    if _str(d, "image"):
        v.check_fit(["Photo"], d["image"], C.ENTRY_SLOTS["specials"][1], spot="specials")
    if _str(d, "image") and not _str(d, "image_alt"):
        v.error(["Photo description (alt text)"], "Describe the photo in a few words for people using screen "
                                                  "readers — for example, what’s in the cup.")
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
    o, c = _mins(d.get("start_time")), _mins(d.get("end_time"))
    if o is not None and c is not None and c <= o:
        v.error(["Ends"], f"The end time ({d['end_time']}) is not after the start time ({d['start_time']}). "
                          "Times use the 24-hour clock, so 6pm is 18:00.")
    if _str(d, "end_time") and not _str(d, "start_time"):
        v.error(["Starts"], "Add a start time too (or clear the end time).")
    if _str(d, "image") and not _str(d, "image_alt"):
        v.error(["Photo description (alt text)"], "Describe the photo in a few words for people using screen "
                                                  "readers.")
    check_link_pair(d, v, "link_url", "link_label", "Link", "Link label")


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
    slugs, by_key = {}, {}
    existing = C.existing_photos(root)
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
        if key.startswith("pages/") or coll in ("specials", "events", "albums"):
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
        if coll:
            stem = path.stem
            name_label = schema["name" if "name" in schema else "title"].label
            if not SLUG.fullmatch(stem):
                # The CMS makes the file name from the name and can't rename an
                # entry, so the fix in the CMS is a new entry with a usable name.
                v.error([name_label], f"The file name “{path.name}” can’t be used in a web address (it needs "
                                      "letters or numbers, and only lowercase letters, numbers and dashes). In the "
                                      "CMS, delete this entry and create it again with a name that has letters or "
                                      "numbers — the web address is made from the name.")
            k2 = (coll, stem.lower())
            if k2 in slugs:
                v.error([name_label], f"Two {coll} share the web address “{stem}” ({slugs[k2]} and {path.name}). "
                                      "Delete one of them and create it again with a different name.")
            slugs[k2] = path.name
        problems += v.problems
    check_navigation(problems, by_key, root)
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
