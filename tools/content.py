"""
The editable content in content/: where each file lives, what it may contain,
and how it is loaded for the build.

content/ is the ONLY thing the marketing manager edits (through Pages CMS).
Each file has a schema below. One schema does three jobs:

  * validation  — tools/validate_content.py walks it and reports problems in
                  plain English, using the same labels the CMS shows;
  * defaults    — a field the file doesn't have yet is filled with its default,
                  so templates never meet a missing key;
  * documentation — the field labels here are the labels to use in .pages.yml.

Unknown keys are ignored (the CMS may add its own metadata). Pages CMS removes
empty values ("", null, [], {}) when it saves a file, so the build ALWAYS reads
content through normalise(): a missing key is the same as its default. Image
fields are repo-relative paths under src-img/ ("src-img/uploads/x.jpg"); a
leading "/" is accepted too, because the CMS may write "/src-img/…".

Every key the site reads from these files must also be declared in .pages.yml
(a CMS save deletes undeclared keys). Technical values — tuned crops, cover
focal points, layout flags — therefore live in src-img/slot-specs.json and in
PAGE_CONFIG (tools/render.py), never here.
"""
import contextlib
import copy
import json
import pathlib
import re

import hours
import textfmt

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Page files in content/pages/ and the name each one has in the CMS. The menu
# and FAQ pages keep their headings in content/menu.json and content/faq.json.
PAGES = {
    "home": "Home",
    "story": "The Layers Story",
    "how": "How We Make It",
    "what": "What We Make",
    "day": "A Day at Layers",
    "catering": "Catering",
    "visit": "Visit",
    "gift-cards": "Gift Cards",
    "loyalty": "Loyalty",
    "404": "Page not found",
}

# The "where" labels in validation messages (and the CMS's collection names).
WHERE = {
    "site": "Business details",
    "hours": "Opening hours",
    "announcement": "Announcement bar",
    "instagram": "Instagram",
    "links": "Link in bio",
    "menu": "Menu",
    "faq": "FAQ",
}

IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")

# What an Instagram post link and a Behold JSON feed link look like (the
# validator checks content against these; tools/instagram.py checks the feed).
INSTAGRAM_POST = re.compile(r"https://(www\.)?instagram\.com/(p|reel|reels|tv)/[A-Za-z0-9_-]+/?(\?\S*)?")
BEHOLD_FEED = re.compile(r"https://feeds\.behold\.so/[A-Za-z0-9_-]+/?")

# Copy that is still a placeholder: a whole field in [brackets] ("[Step 1 —
# client to supply]"), or the "client to supply" note anywhere in it.
PLACEHOLDER = re.compile(r"^\[.*\]$|client to supply", re.I | re.S)

# A collection entry's name/title becomes its file name and web address
# (Pages CMS slugifies it and keeps only a–z, 0–9 and dashes). A name with no
# letter or number at all ("🎃🎃", or a script slugify drops) gives an empty
# file name, which the CMS can't save or the site can't use — and the CMS can't
# rename an entry afterwards. .pages.yml has the same rule as a pattern, so
# the CMS refuses such a name at save.
WEB_NAME = re.compile(r"[A-Za-z0-9]")
WEB_NAME_MESSAGE = ("Use at least one letter or number (A–Z, 0–9): the name becomes the web address. "
                    "Emoji and symbols alone can’t be used.")

# Photo framing keywords the manager picks, and what they mean to the crop
# (focal point = crop centre, 0–1 of the photo; the crop stays inside the frame).
FOCUS_POINTS = {"auto": (0.5, 0.5), "top": (0.5, 0.0), "bottom": (0.5, 1.0), "left": (0.0, 0.5),
                "right": (1.0, 0.5), "top-left": (0.0, 0.0), "top-right": (1.0, 0.0),
                "bottom-left": (0.0, 1.0), "bottom-right": (1.0, 1.0)}
ZOOM_FACTORS = {"auto": 1.0, "none": 1.0, "a-little": 1.15, "more": 1.35}
FOCUS = tuple(FOCUS_POINTS)
ZOOMS = tuple(ZOOM_FACTORS)

# Photo spots with one slot per entry, so they aren't listed one by one in
# src-img/slot-specs.json: (slot group, crop aspect w:h, output width set in
# tools/build-home-media.py). A spec in slot-specs.json under the same slot
# name ("specials/phi-velvet") adds hand tuning, as for any other slot.
ENTRY_SLOTS = {
    "menu": ("menu", "1", "card"),               # menu cards (content/menu.json items)
    "instagram": ("instagram", "1", "tile"),     # the homepage Instagram grid
    "specials": ("specials", "4:5", "tall"),     # the "Limited time" band and menu card
    "events": ("events", "1", "thumb"),          # the "Coming up" list
}


def parse_aspect(a):
    """'16:10' / '1200:630' / '1' / 2.333 -> width ÷ height."""
    if isinstance(a, (int, float)):
        return float(a)
    w, h = str(a).split(":") if ":" in str(a) else (a, 1)
    return float(w) / float(h)


def framing(tuned, image, focus="auto", zoom="auto", default_edit=None):
    """(focal, zoom, edit) for a photo slot (CMS_SPEC §4). While the content
    still points at the hand-tuned photo with focus and zoom on "auto", the
    tuned focal/zoom/edit are used exactly; otherwise the keywords and the
    default retouch."""
    if tuned and image == tuned.get("image") and focus == "auto" and zoom == "auto":
        return list(tuned.get("focal", [0.5, 0.5])), tuned.get("zoom", 1.0), tuned.get("edit", {})
    return (list(FOCUS_POINTS.get(focus, FOCUS_POINTS["auto"])), ZOOM_FACTORS.get(zoom, 1.0),
            dict(default_edit or {}))


class ContentError(Exception):
    """A content file can't be read at all (missing, or not valid JSON)."""


# ---------------------------------------------------------------------------
# Schema nodes. Each knows its CMS label, its default, and how to check a
# value. Checking is done by tools/validate_content.py (it calls .check()).
# ---------------------------------------------------------------------------
class Field:
    kind = "text"

    def __init__(self, label, required=False, default=None, help=""):
        self.label, self.required, self._default, self.help = label, required, default, help

    def default(self):
        return copy.deepcopy(self._default)

    def normalise(self, value):
        return value

    def check(self, value, v, path):     # v: the validator's Context
        pass


class Text(Field):
    """A string. max -> error above it; warn_max -> warning above it.

    multiline: the CMS gives it a multi-line box and the template keeps the
    manager's line breaks (the `br` filter in tools/render.py), so what she
    types is what shows. Without it (and without markdown) a line break shows
    as a space, and the validator says so.
    web_name: the text a collection entry's file name — its web address — is
    made from (Pages CMS slugifies it: "Phi Velvet" -> phi-velvet.json). It
    needs at least one letter or number, or the file name comes out empty."""

    def __init__(self, label, required=False, max=None, warn_max=None, markdown=False, multiline=False,
                 default="", help="", warn_why="", empty_msg="", web_name=False):
        super().__init__(label, required, default, help)
        self.max, self.warn_max, self.markdown, self.multiline, self.warn_why = max, warn_max, markdown, multiline, warn_why
        self.empty_msg = empty_msg
        self.web_name = web_name

    def check(self, value, v, path):
        if not isinstance(value, str):
            return v.type_error(path, value, "text")
        text = value.strip()
        if self.required and not text:
            return v.error(path, self.empty_msg or f"“{self.label}” can’t be empty — please fill it in.")
        if self.web_name and not WEB_NAME.search(text):
            v.error(path, WEB_NAME_MESSAGE)
        if not self.multiline and not self.markdown and "\n" in text:
            v.warning(path, "This should be a single line; the line break will show as a space.")
        if PLACEHOLDER.search(text):
            short = text if len(text) <= 60 else text[:57].rstrip() + "…"
            v.error(path, f"This still has placeholder text (“{short}”). Replace it with the real wording "
                          "before it goes on the site.")
        n = len(_visible(text) if self.markdown else text)
        if self.max and n > self.max:
            v.error(path, f"This is {n} characters long; the limit is {self.max}. Please shorten it.")
        elif self.warn_max and n > self.warn_max:
            v.warning(path, f"This is {n} characters long. {self.warn_why or f'Try to keep it under {self.warn_max}.'}")


class Url(Field):
    """https://… or a page on this site (/menu, /catering#catering, #section)."""
    kind = "link"

    def __init__(self, label, required=False, help="", allow=("https", "site")):
        super().__init__(label, required, "", help)
        self.allow = allow

    def normalise(self, value):
        # Pages CMS doesn't trim what's typed, and a pasted link often brings a
        # space or a line break with it: the build uses the link without them
        # (.pages.yml's link patterns allow them for the same reason).
        return value.strip() if isinstance(value, str) else value

    def check(self, value, v, path):
        if not isinstance(value, str):
            return v.type_error(path, value, "a link")
        u = value.strip()
        if not u:
            if self.required:
                v.error(path, f"“{self.label}” needs a link — a web address starting with https:// "
                              "or a page on this site such as /menu.")
            return
        if not url_ok(u, self.allow):
            if u.lower().startswith("http://"):
                v.error(path, f"“{u}” starts with http://. Use the secure https:// version of the link.")
            elif "site" in self.allow:
                v.error(path, f"“{u}” isn’t a link the site can use. Use a full web address starting with "
                              "https:// or a page on this site starting with / (for example /menu).")
            else:
                v.error(path, f"“{u}” isn’t a full web address. It should start with https://.")


class Bool(Field):
    kind = "on/off switch"

    def __init__(self, label, default=False, help=""):
        super().__init__(label, False, default, help)

    def check(self, value, v, path):
        if not isinstance(value, bool):
            v.type_error(path, value, "an on/off switch (true or false)")


class Int(Field):
    kind = "number"

    def __init__(self, label, default=0, min=None, max=None, help=""):
        super().__init__(label, False, default, help)
        self.min, self.max = min, max

    def check(self, value, v, path):
        if isinstance(value, bool) or not isinstance(value, int):
            return v.type_error(path, value, "a whole number")
        if (self.min is not None and value < self.min) or (self.max is not None and value > self.max):
            v.error(path, f"{value} is out of range; use a number from {self.min} to {self.max}.")


class Choice(Field):
    kind = "choice"

    def __init__(self, label, options, default=None, help=""):
        super().__init__(label, False, options[0] if default is None else default, help)
        self.options = options

    def check(self, value, v, path):
        if value not in self.options:
            v.error(path, f"“{value}” isn’t one of the choices. Pick one of: {', '.join(self.options)}.")


class Date(Field):
    kind = "date"

    def __init__(self, label, required=False, help=""):
        super().__init__(label, required, "", help)

    def check(self, value, v, path):
        if not isinstance(value, str):
            return v.type_error(path, value, "a date")
        if not value.strip():
            if self.required:
                v.error(path, f"“{self.label}” needs a date.")
            return
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()) or _date(value) is None:
            v.error(path, f"“{value}” isn’t a date. Use the date picker, or write it as YYYY-MM-DD "
                          "(for example 2026-11-26).")


class Time(Field):
    kind = "time"

    def __init__(self, label, required=False, help=""):
        super().__init__(label, required, "", help)

    def check(self, value, v, path):
        if not isinstance(value, str):
            return v.type_error(path, value, "a time")
        if not value.strip():
            if self.required:
                v.error(path, f"“{self.label}” needs a time, for example 09:00.")
            return
        if not re.fullmatch(r"\d{2}:\d{2}", value.strip()) or _minutes(value) is None:
            v.error(path, f"“{value}” isn’t a time. Use the 24-hour format HH:MM — for example 09:00 "
                          "for 9 in the morning or 18:30 for 6:30 in the evening.")


class Image(Field):
    """A photo path under src-img/. min_edge applies to new uploads only."""
    kind = "photo"

    def __init__(self, label, required=False, full_width=False, help=""):
        super().__init__(label, required, "", help)
        self.full_width = full_width

    def check(self, value, v, path):
        if not isinstance(value, str):
            return v.type_error(path, value, "a photo")
        if not value.strip():
            if self.required:
                v.error(path, f"“{self.label}” needs a photo. Choose or upload one.")
            return
        v.check_image(path, value.strip(), full_width=self.full_width)


class Obj(Field):
    kind = "group of fields"

    def __init__(self, label, fields, help="", in_path=True):
        super().__init__(label, False, None, help)
        self.fields = fields
        # in_path=False: the group's own label is left out of message paths
        # ("Saturday → Opens", not "Weekly hours → Saturday → Opens")
        self.in_path = in_path

    def default(self):
        return {k: f.default() for k, f in self.fields.items()}

    def normalise(self, value):
        if not isinstance(value, dict):
            return value
        out = dict(value)
        for k, f in self.fields.items():
            out[k] = f.normalise(out[k]) if k in out else f.default()
        return out

    def check(self, value, v, path):
        if not isinstance(value, dict):
            return v.type_error(path, value, "a group of fields")
        for k, f in self.fields.items():
            sub = path + [f.label] if getattr(f, "in_path", True) else path
            if k not in value:
                if f.required:
                    v.error(sub, f"“{f.label}” is missing — please fill it in.")
                continue
            with _at(v, k):
                f.check(value[k], v, sub)


class List(Field):
    """A list of `item`s. item_label(i, value) names an entry in messages;
    hidden_if(value) marks an entry that isn't on the site (a menu item
    switched to "Hide from the website"): its problems are reported as notes,
    like a draft's, and never stop the update."""
    kind = "list"

    def __init__(self, label, item, min=0, max=None, item_label=None, help="", hidden_if=None, hidden_note=""):
        super().__init__(label, False, [], help)
        self.item, self.min, self.max = item, min, max
        self.item_label = item_label or (lambda i, val: f"{label} {i + 1}")
        self.hidden_if, self.hidden_note = hidden_if, hidden_note

    def normalise(self, value):
        return [self.item.normalise(x) for x in value] if isinstance(value, list) else value

    def check(self, value, v, path):
        if not isinstance(value, list):
            return v.type_error(path, value, "a list")
        if len(value) < self.min:
            v.error(path, f"This needs at least {self.min} entr{'y' if self.min == 1 else 'ies'}; "
                          f"it has {len(value)}.")
        if self.max is not None and len(value) > self.max:
            v.error(path, f"This can have at most {self.max} entries; it has {len(value)}. "
                          "Remove the extra ones.")
        for i, x in enumerate(value):     # "Chapters" -> "Chapter 2 (“Our roots”) → Title"
            hidden = bool(self.hidden_if and self.hidden_if(x)) and hasattr(v, "leniently")
            with _at(v, i), (v.leniently(self.hidden_note) if hidden else contextlib.nullcontext()):
                self.item.check(x, v, path[:-1] + [self.item_label(i, x)])


def _at(v, key):
    """While a field is checked, the validator's Context knows where it is in
    the file (["photos", "hero", "image"]) — that's how a photo knows which
    spot it fills (photo_spot)."""
    at = getattr(v, "at", None)
    if at is None:
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def step():
        at.append(key)
        try:
            yield
        finally:
            at.pop()
    return step()


def summary_label(noun, *keys):
    """An item label for validation messages: its number plus the text Pages
    CMS shows on the collapsed item (the `collapsible.summary` in .pages.yml),
    "Question 3 (“How late are you open?”)", so the manager can find it by
    either."""
    def label(i, x):
        text = " ".join(str(x.get(k) or "").strip() for k in keys) if isinstance(x, dict) else ""
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 40:
            text = text[:39].rstrip() + "…"
        return f"{noun} {i + 1} (“{text}”)" if text else f"{noun} {i + 1}"
    return label


def menu_item_label(i, x):
    """A menu item as the CMS lists it: "Bowls · Mango Coco" (.pages.yml
    summary "{category} · {square_name}")."""
    if isinstance(x, dict):
        text = " · ".join(t for t in (str(x.get(k) or "").strip() for k in ("category", "square_name")) if t)
        if text:
            return text
    return f"Item {i + 1}"


ALT_MISSING = ("This photo needs a short description (alt text) — a few words on what’s in it, for people "
               "who use screen readers. For example: “Two friends toasting with Layers smoothies outside the shop”.")


def Alt(label="Description (alt text)"):
    return Text(label, required=True, max=250, empty_msg=ALT_MISSING,
                help="What's in the photo, for people using screen readers.")


def Photo(label, alt=True, full_width=False):
    """A placed photo: the image, its description, and how to frame it."""
    fields = {"image": Image("Photo", required=True, full_width=full_width)}
    if alt:
        fields["alt"] = Alt()
    fields["focus"] = Choice("Focus", FOCUS, help="Which part of the photo to keep when it's cropped.")
    fields["zoom"] = Choice("Zoom", ZOOMS)
    return Obj(label, fields)


def _seo(desc_required=True):
    return Obj("SEO", {
        "title": Text("Page title", required=True, warn_max=60,
                      warn_why="Search results show about 60 characters, so the end may be cut off."),
        "description": Text("Description", required=desc_required, warn_max=160,
                            warn_why="Search results show about 160 characters, so the end may be cut off."),
    })


def _cta(label="Button label"):
    return Text(label, required=True, warn_max=40, warn_why="Long button labels wrap onto two lines.")


def _heading(label="Heading", required=True):
    return Text(label, required=required, warn_max=80, warn_why="Long headings can wrap awkwardly.")


def _steps(label, item_label, heading_label="Heading"):
    return List(label, Obj(item_label, {"heading": _heading(heading_label),
                                        "text": Text("Text", required=True, multiline=True)}),
                min=1, item_label=summary_label(item_label, "heading"))


PILLARS = List("Principles", Obj("Principle", {
    "name": _heading("Name"), "description": Text("Description", required=True, multiline=True)}),
    min=1, item_label=summary_label("Principle", "name"))

# ---------------------------------------------------------------------------
# One schema per page. "photos" keys map 1:1 to the photo slots in
# src-img/slot-specs.json (home/hero -> photos.hero, home/hero-m ->
# photos.hero_mobile, home/fresh-1 -> photos.fresh_1 …).
# ---------------------------------------------------------------------------
PAGE_SCHEMAS = {
    "home": {
        "seo": _seo(),
        "photos": Obj("Photos", {
            "hero": Photo("Hero photo", full_width=True),
            "hero_mobile": Photo("Hero photo on phones", alt=False),
            "fresh_1": Photo("Made fresh — photo 1"),
            "fresh_2": Photo("Made fresh — photo 2"),
            "fresh_3": Photo("Made fresh — photo 3"),
            "bowls": Photo("Bowls photo"),
            "smoothies": Photo("Smoothies photo"),
            "visit": Photo("Visit photo", full_width=True),
        }),
        "hero": Obj("Hero", {
            "heading": _heading("Big word"),
            "line": _heading("Line under it"),
            "order_label": _cta("Order button"),
        }),
        "fresh": Obj("Made fresh", {"statement": _heading("Statement")}),
        "film": Obj("Film", {
            "label": Text("Name of the film (for screen readers)", required=True, max=80),
            "description": Text("Text description of the film", required=True, max=600,
                                help="Read aloud by screen readers in place of the film."),
        }),
        "products": Obj("Bowls and smoothies", {
            "bowls_label": _heading("Bowls tile"),
            "smoothies_label": _heading("Smoothies tile"),
            "menu_label": _cta("Link label"),
        }),
        "community": Obj("Community", {
            "heading": _heading(),
            "text": Text("Text", required=True, multiline=True),
            "wide": Obj("Wide photo", {
                "photo": Photo("Photo", full_width=True),
                "caption": Text("Caption", required=True, max=80),
            }),
            "squares": List("Square photos", Obj("Square photo", {
                "photo": Photo("Photo"),
                "caption": Text("Caption", required=True, max=80),
            }), min=4, max=4, item_label=summary_label("Square photo", "caption")),
            "albums_label": _cta("Albums link label"),
        }),
        "visit": Obj("Visit", {
            "heading": _heading(),
            "directions_label": _cta("Directions button"),
            "order_label": _cta("Order button"),
        }),
    },
    "story": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {
            "open_1": Photo("Opening photo, left"),
            "open_2": Photo("Opening photo, right"),
            "philosophy": Photo("Wide photo after chapter 2", full_width=True),
            "journey": Photo("Wide photo after chapter 4", full_width=True),
            "make_1": Photo("Closing photo, left"),
            "make_2": Photo("Closing photo, right"),
        }),
        "chapters": List("Chapters", Obj("Chapter", {
            "title": _heading("Title"),
            "lead": Text("Opening sentence", required=True, multiline=True),
            "body": Text("Text", markdown=True),
            "closing_line": Text("Closing line"),
        }), min=1, item_label=summary_label("Chapter", "title")),
        "pillars": PILLARS,
        "closing": Obj("Closing", {
            "statement": _heading("Statement"),
            "order_label": _cta("Order button"),
            "menu_label": _cta("Menu button"),
        }),
    },
    "how": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "lede": Text("Line under the title"),
        "lead": Text("Opening sentence", required=True, multiline=True),
        "body": Text("Text", markdown=True),
        "closing_line": Text("Closing line"),
        "photos": Obj("Photos", {}),
        "pillars": PILLARS,
        "story_link_label": _cta("Story link"),
        "menu_label": _cta("Menu button"),
        "order_label": _cta("Order button"),
    },
    "what": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"hero": Photo("Main photo")}),
        "items": _steps("What we make", "Item"),
        "closing": Obj("Closing", {
            "statement": _heading("Statement"),
            "menu_label": _cta("Menu button"),
            "order_label": _cta("Order button"),
        }),
    },
    "day": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {}),
    },
    "catering": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "inquiry_label": _cta("Inquiry button"),
        "photos": Obj("Photos", {"hero": Photo("Main photo", full_width=True)}),
        "intro": Text("Introduction", required=True, markdown=True),
        "form": Obj("Inquiry form", {
            "heading": _heading(),
            "submit_label": _cta("Send button"),
            "reply_note": Text("Note beside the button"),
        }),
    },
    "visit": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"hero": Photo("Main photo")}),
        "directions_label": _cta("Directions button"),
        "order_label": _cta("Order button"),
        "pickup_note": Text("Pickup note"),
        "getting_here": Obj("Getting here", {
            "heading": _heading(),
            "sections": List("Sections", Obj("Section", {
                "heading": _heading(), "text": Text("Text", required=True, markdown=True)}),
                min=1, item_label=summary_label("Section", "heading")),
        }),
    },
    "gift-cards": {
        "published": Bool("Published", default=False),
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"hero": Photo("Main photo")}),
        "text": Text("Text", required=True, markdown=True),
        "buy_label": _cta("Buy button"),
        "buy_url": Url("Buy button link", required=True, allow=("https",)),
        "fine_print": Text("Small print"),
        "how": Obj("How it works", {"heading": _heading(), "steps": _steps("Steps", "Step")}),
    },
    "loyalty": {
        "published": Bool("Published", default=False),
        "seo": _seo(desc_required=False),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"side": Photo("Photo", alt=False)}),
        "text": Text("How it works, in a few sentences", required=True, multiline=True),
        "join_line": Text("How to join"),
        "how_heading": _heading("Steps heading"),
        "steps": List("Steps", Text("Step", required=True), min=1, item_label=lambda i, x: f"Step {i + 1}"),
    },
    "404": {
        "seo": _seo(desc_required=False),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "lede": Text("Line under the title"),
        "menu_label": _cta("Menu button"),
        "home_label": _cta("Home button"),
        "photos": Obj("Photos", {}),
    },
}

_DAY = lambda name: Obj(name, {"closed": Bool("Closed all day"), "open": Time("Opens"), "close": Time("Closes")})

SCHEMAS = {
    "site": {
        "business": Obj("Business", {
            "name": Text("Name", required=True),
            "street": Text("Street address", required=True),
            "city": Text("City", required=True),
            "region": Text("State", required=True),
            "postal_code": Text("ZIP code", required=True),
            "cross_streets": Text("Cross streets"),
            "phone": Text("Phone"),
            "public_email": Text("Public email",
                                 help="Shown in the footer. Never the catering inbox."),
        }),
        "ordering": Obj("Ordering", {
            "square_url": Url("Square store link", required=True, allow=("https",)),
            "doordash_url": Url("DoorDash link", allow=("https",)),
            "ubereats_url": Url("Uber Eats link", allow=("https",)),
        }),
        "social": Obj("Social", {
            "instagram_handle": Text("Instagram handle"),
            "tiktok_url": Url("TikTok link", allow=("https",)),
            "facebook_url": Url("Facebook link", allow=("https",)),
            "yelp_url": Url("Yelp link", allow=("https",)),
            "google_url": Url("Google link", allow=("https",)),
        }),
        "seo": Obj("SEO", {
            "default_description": Text("Default description", required=True, warn_max=160,
                                        warn_why="Search results show about 160 characters."),
            "share_image": Image("Share image", help="Shown when a link to the site is shared. "
                                                     "Empty = the homepage photo."),
        }),
        "footer_tagline": Text("Footer tagline", required=True),
        "signoff_tagline": Text("Sign-off tagline", required=True),
        "analytics": Obj("Analytics", {"cloudflare_web_analytics_token": Text("Cloudflare Web Analytics token")}),
    },
    "hours": {
        "weekly": Obj("Weekly hours", {d: _DAY(d.capitalize()) for d in
                                        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")},
                      in_path=False),
        "special": List("Special hours", Obj("Special day", {
            "date": Date("Date", required=True),
            "label": Text("Name", help="For example Thanksgiving."),
            "closed": Bool("Closed all day"),
            "open": Time("Opens"),
            "close": Time("Closes"),
        }), item_label=summary_label("Special hours", "date", "label")),
        "note": Text("Note"),
    },
    "announcement": {
        "enabled": Bool("Show the bar"),
        "message": Text("Message", max=110),
        "link_label": Text("Link label", warn_max=30),
        "link_url": Url("Link"),
        "starts": Date("Starts"),
        "ends": Date("Ends"),
        "tone": Choice("Colour", ("green", "butter")),
    },
    "instagram": {
        "enabled": Bool("Show the Instagram section", default=True),
        "heading": _heading(),
        "mode": Choice("Posts to show", ("curated", "auto")),
        "behold_feed_url": Url("Behold feed link", allow=("https",)),
        "count": Int("Number of posts", default=4, min=1, max=12),
        "curated": List("Hand-picked posts", Obj("Post", {
            "image": Image("Photo", required=True),
            "post_url": Url("Instagram post link", required=True, allow=("https",)),
            "alt": Alt(),
        }), item_label=lambda i, x: f"Post {i + 1}"),
    },
    "links": {
        "enabled": Bool("Publish the page", default=True),
        "heading": _heading(),
        "intro": Text("Introduction", markdown=True),
        "buttons": List("Buttons", Obj("Button", {
            "label": _cta("Label"),
            "url": Url("Link", required=True),
            "highlight": Bool("Highlight"),
        }), min=1, item_label=summary_label("Button", "label")),
        "show_specials": Bool("Show specials", default=True),
        "show_events": Bool("Show events", default=True),
    },
    "menu": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "intro": Text("Introduction", markdown=True),
        "status_note": Text("Prices note", required=True),
        "allergen_note": Text("Allergen note", required=True),
        "order_label": _cta("Order button"),
        "items": List("Items", Obj("Item", {
            "square_id": Text("Square ID", required=True),
            "square_name": Text("Name on Square"),
            "category": Text("Category on Square"),
            "display_name": Text("Name on the website", warn_max=40,
                                 warn_why="Long names wrap onto several lines on the menu cards."),
            "note": Text("Note under the name", warn_max=60),
            "photo": Image("Photo", help="Empty = the photo from Square."),
            "focus": Choice("Focus", FOCUS),
            "zoom": Choice("Zoom", ZOOMS),
            "hidden": Bool("Hide from the website"),
        }), item_label=menu_item_label,
            hidden_if=lambda x: isinstance(x, dict) and x.get("hidden") is True,
            hidden_note="(This item is hidden from the website, so it won’t stop the update.)"),
    },
    "faq": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "items": List("Questions", Obj("Question", {
            "question": Text("Question", required=True, warn_max=120),
            "answer": Text("Answer", required=True, markdown=True),
        }), min=1, item_label=summary_label("Question", "question")),
    },
}

# A special's "Order button" choices and the labels the CMS shows for them
# (.pages.yml options), used in validation messages. The first is the default.
ORDER_BUTTON_LABELS = {
    "none": "No button (in store only)",
    "square": "Order on Square",
    "link": "Order (to the order link below)",
}

COLLECTIONS = {
    "specials": ("Special", {
        "name": Text("Name", required=True, warn_max=40, web_name=True),
        "partner": Text("Made with (partner)"),
        "badge": Text("Badge", warn_max=24),
        "tagline": Text("Tagline", warn_max=80),
        "description": Text("Description", markdown=True),
        "highlights": List("Highlights", Text("Highlight", required=True, warn_max=40),
                           item_label=lambda i, x: f"Highlight {i + 1}"),
        "ingredients": Text("Ingredients", multiline=True),
        "price": Text("Price"),
        "image": Image("Photo"),
        "image_alt": Text("Photo description (alt text)", max=250),
        "starts": Date("Starts"),
        "ends": Date("Ends"),
        # none: no button, the availability note instead (not on Square, e.g.
        # Phi Velvet); square: "Order on Square" to the store; link: "Order"
        # to the order link below. ORDER_BUTTON_LABELS = the CMS's option labels.
        "order_button": Choice("Order button", tuple(ORDER_BUTTON_LABELS),
                               help="; ".join(ORDER_BUTTON_LABELS.values())),
        "order_url": Url("Order link", allow=("https",),
                         help=f"Only used when the order button is “{ORDER_BUTTON_LABELS['link']}”."),
        "availability_note": Text("Availability note", default="In store for a limited time.", warn_max=60,
                                  help=f"Shown instead of a button when the order button is "
                                       f"“{ORDER_BUTTON_LABELS['none']}”."),
        "show_on_home": Bool("Show on the homepage", default=True),
        "show_on_menu": Bool("Show on the menu", default=True),
        "published": Bool("Published", default=True),
    }),
    "events": ("Event", {
        "title": Text("Title", required=True, warn_max=60, web_name=True),
        "date": Date("Date", required=True),
        "start_time": Time("Starts"),
        "end_time": Time("Ends"),
        "partner": Text("With (partner)"),
        "location": Text("Location"),
        "description": Text("Description", markdown=True),
        "image": Image("Photo"),
        "image_alt": Text("Photo description (alt text)", max=250),
        "link_url": Url("Link"),
        "link_label": Text("Link label", warn_max=30),
        "published": Bool("Published", default=True),
    }),
    "albums": ("Album", {
        "title": Text("Title", required=True, warn_max=40, web_name=True),
        "order": Int("Position", default=99, min=0, max=999),
        "published": Bool("Published", default=True),
        "cover": Image("Cover photo"),
        "cover_focus": Choice("Cover focus", FOCUS),
        "photos": List("Photos", Obj("Photo", {
            "image": Image("Photo", required=True),
            "alt": Alt(),
        }), item_label=lambda i, x: f"Photo {i + 1}"),
    }),
}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def content_dir(root=ROOT):
    return pathlib.Path(root) / "content"


def image_rel(path):
    """'/src-img/a.jpg' or 'src-img/a.jpg' -> 'src-img/a.jpg' (POSIX, no leading /)."""
    return str(path or "").strip().replace("\\", "/").lstrip("/")


def image_file(path, root=ROOT):
    """The file for an image field, or None when the path leaves src-img/."""
    rel = image_rel(path)
    if not rel.startswith("src-img/") or ".." in rel.split("/"):
        return None
    return pathlib.Path(root) / rel


def url_ok(u, allow=("https", "site")):
    u = u.strip()
    if "https" in allow and re.fullmatch(r"https://[^\s/$.?#][^\s]*", u):
        return True
    if "site" in allow and (u.startswith("#") or (u.startswith("/") and not u.startswith(("//", "/\\")))):
        return " " not in u
    return False


def _date(s):
    return hours.parse_date(s.strip())


def _minutes(s):
    return hours.parse_time(s.strip())


def _visible(text):
    return textfmt.plain(text)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def read_json(path):
    """Parse a content file; ContentError carries a plain-English reason."""
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ContentError("This file is missing.") from None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ContentError(f"This file isn’t valid JSON (line {e.lineno}, column {e.colno}: {e.msg}). "
                           "If you edited it by hand, check for a missing comma or quote; "
                           "otherwise undo the last change.") from None


def normalise(schema, data):
    """Fill every missing key with its default (recursively, through lists)."""
    return Obj("", schema).normalise(data) if isinstance(data, dict) else data


def prune_empty(value):
    """What a Pages CMS save does to a value: drop "", None, [] and {} (recursively)."""
    if isinstance(value, dict):
        out = {k: prune_empty(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in ("", None, [], {})}
    if isinstance(value, list):
        out = [prune_empty(v) for v in value]
        return [v for v in out if v not in ("", None, [], {})]
    return value


def dump_cms_json(data):
    """A content file in the CMS's own output format: empty values dropped,
    2-space indent, no final newline — so a later CMS save shows no churn."""
    return json.dumps(prune_empty(data), indent=2, ensure_ascii=False)


def files(root=ROOT):
    """Every content file: (key, path, schema, where-label). Collections included."""
    c = content_dir(root)
    out = [(k, c / f"{k}.json", SCHEMAS[k], WHERE[k]) for k in SCHEMAS]
    out += [(f"pages/{k}", c / "pages" / f"{k}.json", PAGE_SCHEMAS[k], f"Page: {label}")
            for k, label in PAGES.items()]
    for coll, (noun, schema) in COLLECTIONS.items():
        for p in sorted((c / coll).glob("*.json")) if (c / coll).is_dir() else []:
            out.append((f"{coll}/{p.stem}", p, schema, f"{noun}: {p.stem}"))
    return out


def load_all(root=ROOT):
    """Everything in content/, normalised (defaults filled). Assumes it validated."""
    c = content_dir(root)
    data = {k: normalise(SCHEMAS[k], read_json(c / f"{k}.json")) for k in SCHEMAS}
    data["pages"] = {k: normalise(PAGE_SCHEMAS[k], read_json(c / "pages" / f"{k}.json")) for k in PAGES}
    for coll, (_, schema) in COLLECTIONS.items():
        items = []
        for p in sorted((c / coll).glob("*.json")) if (c / coll).is_dir() else []:
            item = normalise(schema, read_json(p))
            item["slug"] = p.stem
            items.append(item)
        data[coll] = items
    return data


def page_published(page):
    """Pages without a "published" switch are always published."""
    return page.get("published", True) is not False


def code_fingerprint(path):
    """A hash of a Python file's CODE — comments and docstrings don't count, so
    documenting the photo pipeline never forces every photo to be rebuilt.

    It hashes the SOURCE TEXT with comments and docstrings cut out (and blank
    lines and trailing spaces dropped), not a dump of the syntax tree: the
    tree's printed form changes between Python versions (it did in 3.13), and
    the fingerprints are committed in the photo manifests, so CI on 3.12 and a
    laptop on 3.14 must compute the same value or every photo is rebuilt.
    Comment positions come from tokenize and docstring positions from ast,
    both stable across versions. tests/test_slots.py pins the value."""
    import ast
    import hashlib
    import io
    import tokenize
    src = pathlib.Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = src.split("\n")
    starts, pos = [], 0                     # character offset where each line starts
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1

    def offset(line, col_bytes=None, col_chars=None):
        if col_chars is None:               # ast columns count UTF-8 bytes
            col_chars = len(lines[line - 1].encode("utf-8")[:col_bytes].decode("utf-8", "ignore"))
        return starts[line - 1] + col_chars

    cut = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:    # tokenize columns count characters
            cut.append((offset(tok.start[0], col_chars=tok.start[1]), offset(tok.end[0], col_chars=tok.end[1])))
    for node in ast.walk(ast.parse(src)):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            d = body[0]
            cut.append((offset(d.lineno, d.col_offset), offset(d.end_lineno, d.end_col_offset)))
    kept, at = [], 0
    for a, b in sorted(cut):
        if a > at:
            kept.append(src[at:a])
        at = max(at, b)
    kept.append(src[at:])
    code = "\n".join(ln.rstrip() for ln in "".join(kept).split("\n") if ln.strip())
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


def load_tool(filename, root=ROOT):
    """Import one of the hyphenated tools/ scripts (e.g. "build-albums.py") as a module."""
    import importlib.util
    path = pathlib.Path(root) / "tools" / filename
    name = path.stem.replace("-", "_")
    if name not in _TOOLS:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TOOLS[name] = mod
    return _TOOLS[name]


_TOOLS = {}


def get_path(obj, dotted):
    """get_path(page, "community.squares.0.photo") — the binding format in slot-specs.json."""
    for part in dotted.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def field_labels(schema, dotted, data):
    """The CMS labels for a dotted content path, exactly as validation
    messages show them: ("community.squares.0.photo") -> ["Community",
    "Square photo 1", "Photo"]. A list item's label replaces the list's own
    label, as in List.check."""
    node, out, value = Obj("", schema), [], data
    for part in dotted.split("."):
        if isinstance(node, List):
            i = int(part)
            value = value[i] if isinstance(value, list) and i < len(value) else {}
            out[-1:] = [node.item_label(i, value)]
            node = node.item
            continue
        node = node.fields[part]
        if getattr(node, "in_path", True):
            out.append(node.label)
        value = value.get(part, {}) if isinstance(value, dict) else {}
    return out


def crop_size(size, aspect, zoom=1.0):
    """(w, h) of the crop the photo build cuts from a (w, h) photo: the
    largest frame of that aspect, shrunk by zoom (build-home-media.focal_crop)."""
    w, h = size
    cw, ch = (h * aspect, h) if w / h > aspect else (w, w / aspect)
    return round(cw / zoom), round(ch / zoom)


def photo_spot(key, at):
    """The spot a photo field fills, as src-img/existing-photos.json names it.

    key: the content file ("pages/home", "site", "menu", "specials/phi-velvet");
    at: where the field is in it (["photos", "hero", "image"]).
    A page (or site) photo is named by its content binding, the format of
    src-img/slot-specs.json: "pages/home:photos.hero",
    "pages/home:community.squares.0.photo", "site:seo.share_image". A photo in
    a list of like spots is named by the kind of spot: "menu" (a menu card),
    "instagram", "specials", "events", "albums" (album photos and covers)."""
    parts = [str(p) for p in at]
    if parts and parts[-1] == "image":
        parts = parts[:-1]
    if key.startswith("pages/") or key == "site":
        return f"{key}:{'.'.join(parts)}"
    return key.split("/", 1)[0]


def existing_photos(root=ROOT):
    """Photos placed by hand before the CMS (src-img/existing-photos.json):
    {photo path: set of spots it was placed and checked in}. The upload size
    rule doesn't apply to a photo IN those spots — anywhere else it is checked
    like any other photo (a small Square product photo picked for the
    homepage hero must not slip through)."""
    p = pathlib.Path(root) / "src-img" / "existing-photos.json"
    try:
        photos = json.loads(p.read_text()).get("photos", {})
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(photos, dict):
        return {}
    return {str(k): set(v) for k, v in photos.items() if isinstance(v, list)}
