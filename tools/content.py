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

Labels are everyday words for someone with no technical background ("Photo
description", not "alt text"; "Google title", not "SEO title"; "Order button
text" for the words on a button, so it can't be mistaken for the button's
on/off choice). A label renamed here must be renamed in .pages.yml too
(tests/test_cms_schema.py checks), and in the handbook.

Unknown keys are ignored (the CMS may add its own metadata). Pages CMS removes
empty values ("", null, [], {}) when it saves a file, so the build ALWAYS reads
content through normalise(): a missing key is the same as its default. Image
fields are repo-relative paths under src-img/ ("src-img/uploads/x.jpg"); a
leading "/" is accepted too, because the CMS may write "/src-img/…".

Every key the site reads from these files must also be declared in .pages.yml
(a CMS save deletes undeclared keys). Technical values — tuned crops, cover
focal points, layout flags — therefore live in src-img/slot-specs.json and in
PAGE_CONFIG (tools/render.py), never here.

"More sections" (SECTIONS, a Blocks list of the six SECTION_BLOCKS kinds) is
on the pages in SECTION_FILES and on the pages of her own (COLLECTIONS
"custom-pages"); section_photos names their photos for the photo build, the
validator and the pages alike.
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
        if self.markdown:                 # [words](/a-page) links, checked with the others at the end
            for url in textfmt.links(text):
                note_link(v, path, url)
        n = len(_visible(text) if self.markdown else text)
        if self.max and n > self.max:
            v.error(path, f"This is {n} characters long; the limit is {self.max}. Please shorten it.")
        elif self.warn_max and n > self.warn_max:
            v.warning(path, f"This is {n} characters long. {self.warn_why or f'Try to keep it under {self.warn_max}.'}")


def note_link(v, path, url):
    """Remember a link to one of the site's own pages (/menu, /run-club) for
    the validator's check that the page exists and is switched on
    (validate_content.check_links). That check needs every content file read
    first — the page linked to may be any of them — so the link is kept with
    where it is and whether it's on a draft, and checked at the end."""
    links = getattr(v, "links", None)
    if links is not None and site_page(url) is not None:
        links.append({"path": list(path), "url": url.strip(), "lenient": v.lenient, "note": v.lenient_note})


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
        if url_ok(u, self.allow):
            note_link(v, path, u)
        else:
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

    def normalise(self, value):
        # As for links: a phone keyboard easily adds a space after "17:00",
        # which the CMS's time pattern allows, so the build uses it without.
        return value.strip() if isinstance(value, str) else value

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


class Blocks(Field):
    """A page's "More sections": a list of sections, each of one of a few
    kinds — a Pages CMS `block` list (.pages.yml component `more-sections`).
    An item is a group of fields whose `key` ("type", the CMS's blockKey)
    names its kind: {"type": "photo", "image": …, "alt": …}. Each kind is an
    Obj in `blocks` ({name: Obj(label, fields)}), checked and given its
    defaults like any other group. An item of a kind the site doesn't know
    (only a hand edit can make one) is an error, and the build skips it.

    Unlike List, an item's name is ADDED to the path, not put in place of the
    list's label: "More sections → Section 2 (Photo and text) → Photo". The CMS
    shows the list's label above the items and each item's kind on a badge,
    so the manager sees all three words on the screen."""
    kind = "list of sections"

    def __init__(self, label, blocks, key="type", noun="Section", help=""):
        super().__init__(label, False, [], help)
        self.blocks, self.key, self.noun = blocks, key, noun

    def block_of(self, x):
        """The kind (an Obj) of one item, or None when it isn't one the site knows."""
        name = x.get(self.key) if isinstance(x, dict) else None
        return self.blocks.get(name) if isinstance(name, str) else None

    def item_label(self, i, x):
        b = self.block_of(x)
        return f"{self.noun} {i + 1} ({b.label})" if b else f"{self.noun} {i + 1}"

    def normalise(self, value):
        if not isinstance(value, list):
            return value
        out = []
        for x in value:
            b = self.block_of(x)
            out.append({self.key: x[self.key], **{k: v for k, v in b.normalise(x).items() if k != self.key}}
                       if b else x)
        return out

    def check(self, value, v, path):
        if not isinstance(value, list):
            return v.type_error(path, value, "a list")
        for i, x in enumerate(value):
            sub = path + [self.item_label(i, x)]
            with _at(v, i):
                b = self.block_of(x)
                if b is None:
                    name = x.get(self.key) if isinstance(x, dict) else None
                    v.error(sub, (f"This section is of a kind the website doesn’t know (“{name}”)." if name else
                                  "This section has no kind (text, photo …).")
                            + " Remove it with the bin icon and add it again with “Add an item”.")
                    continue
                b.check(x, v, sub)


ALT_MISSING = ("This photo needs a short description: a few words on what’s in it, for people who can’t see "
               "it (screen readers read it aloud). For example: “Two friends toasting with Layers smoothies "
               "outside the shop”.")
ALT_LABEL = "Photo description"     # a photo's alt text, in the CMS's words


def Alt(label=ALT_LABEL):
    return Text(label, required=True, max=250, empty_msg=ALT_MISSING,
                help="What's in the photo, for people who can't see it.")


def Photo(label, alt=True, full_width=False):
    """A placed photo: the image, its description, and how to frame it."""
    fields = {"image": Image("Photo", required=True, full_width=full_width)}
    if alt:
        fields["alt"] = Alt()
    fields["focus"] = Choice("Focus", FOCUS, help="Which part of the photo to keep when it's cropped.")
    fields["zoom"] = Choice("Zoom", ZOOMS)
    return Obj(label, fields)


SEO_LABEL = "Google and shared links"     # every page's SEO group, in the CMS's words


def _seo(desc_required=True):
    return Obj(SEO_LABEL, {
        "title": Text("Google title", required=True, warn_max=60,
                      warn_why="Search results show about 60 characters, so the end may be cut off."),
        "description": Text("Google description", required=desc_required, warn_max=160,
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
# "More sections": sections the manager adds to a page herself, after the
# page's own content (templates/partials/sections.html). Six kinds only,
# each drawn in the site's own editorial style, so nothing added can look
# off-brand. The kind is stored under "type" (the CMS's blockKey).
# ---------------------------------------------------------------------------
def _section_photo():
    """A photo in a section, as fields of the section itself (the CMS shows
    one box per section rather than a box inside a box)."""
    return {"image": Image("Photo", required=True), "alt": Alt(),
            "focus": Choice("Focus", FOCUS, help="Which part of the photo to keep when it's cropped."),
            "zoom": Choice("Zoom", ZOOMS)}


SECTION_BLOCKS = {
    "text": Obj("Text", {
        "eyebrow": Text("Small label above the heading", warn_max=40,
                        warn_why="It’s a small label: keep it to a few words."),
        "heading": _heading("Heading", required=False),
        "text": Text("Text", markdown=True),
    }),
    "photo": Obj("Photo", {
        **_section_photo(),
        "caption": Text("Caption", max=80),
        "size": Choice("Size", ("wide", "standard")),
    }),
    "photo-text": Obj("Photo and text", {
        **_section_photo(),
        "heading": _heading("Heading"),
        "text": Text("Text", markdown=True),
        "button_label": Text("Button text", warn_max=40, warn_why="Long button labels wrap onto two lines."),
        "button_link": Url("Button link"),
        "photo_side": Choice("Photo side", ("left", "right")),
    }),
    "photos": Obj("Row of photos", {
        "photos": List("Photos", Obj("Photo", _section_photo()), min=2, max=4,
                       item_label=lambda i, x: f"Photo {i + 1}"),
    }),
    "button": Obj("Button", {
        "label": _cta("Button text"),
        "link": Url("Link", required=True),
        "style": Choice("Colour", ("green", "outline")),
    }),
    "quote": Obj("Quote", {
        "quote": Text("Quote", required=True, multiline=True, warn_max=280,
                      warn_why="The quote is set in big letters, so a long one is hard to read. "
                               "Try to keep it under 280 characters."),
        "name": Text("Who said it", warn_max=60),
    }),
}
SECTIONS = Blocks("More sections", SECTION_BLOCKS)


def text_section_has_words(section):
    """A Text section with something in it. One with nothing (picked by
    mistake after "Add an item": the CMS saves it, as it has no required
    box) isn't drawn, and the validator only notes it."""
    return any(str(section.get(k) or "").strip() for k in ("eyebrow", "heading", "text"))

# The content files whose page has "More sections" (each page's own copy and
# photos come first; the sections are drawn after them).
SECTION_FILES = ("pages/home", "pages/story", "pages/how", "pages/what", "pages/day", "pages/catering",
                 "pages/visit", "faq", "menu")

# How the photos in sections are cut: (crop aspect w:h, the output width set
# in tools/build-home-media.py, a full-width spot — 1200 px needed, not 800).
SECTION_PHOTOS = {
    "photo:wide": ("21:9", "full", True),
    "photo:standard": ("3:2", "half", False),
    "photo-text": ("4:5", "tall", False),
    "photos": ("1", "half", False),
}
CUSTOM_TOP_PHOTO = ("21:9", "full", True)       # the optional photo under a page's title


def sections_prefix(key):
    """The photo-slot prefix of a content file's sections: "pages/home" ->
    "blocks/home", "menu" -> "blocks/menu", "custom-pages/summer-menu" ->
    "custom/summer-menu". Slots are "<prefix>_<section>[_<photo>]", counted
    from 1 ("blocks/home_2", "blocks/home_3_1"); "_" can't occur in a page
    key or a web address, so two pages' slots never collide."""
    if key.startswith("custom-pages/"):
        return "custom/" + key.split("/", 1)[1]
    return "blocks/" + key.split("/")[-1]


def section_photos(prefix, sections):
    """Every photo in a list of sections, in order: {slot, photo ({image,
    alt, focus, zoom}), at (where it is in the file: ["sections", 1] or
    ["sections", 2, "photos", 0]), section (its number, from 1), aspect,
    widths, full_width}. The build, the validator and the pages all name the
    photos through this, so they always agree."""
    out = []
    for i, s in enumerate(sections if isinstance(sections, list) else []):
        kind = s.get("type") if isinstance(s, dict) else None
        if kind == "photo":
            spec = SECTION_PHOTOS["photo:standard" if s.get("size") == "standard" else "photo:wide"]
            items = [(f"{prefix}_{i + 1}", s, ["sections", i])]
        elif kind == "photo-text":
            spec = SECTION_PHOTOS["photo-text"]
            items = [(f"{prefix}_{i + 1}", s, ["sections", i])]
        elif kind == "photos":
            spec = SECTION_PHOTOS["photos"]
            items = [(f"{prefix}_{i + 1}_{k + 1}", p, ["sections", i, "photos", k])
                     for k, p in enumerate(s.get("photos") if isinstance(s.get("photos"), list) else [])
                     if isinstance(p, dict)]
        else:
            continue
        for slot, photo, at in items:
            out.append({"slot": slot, "photo": photo, "at": at, "section": i + 1, "aspect": spec[0],
                        "widths": spec[1], "full_width": spec[2]})
    return out


# ---------------------------------------------------------------------------
# "Your own pages" (content/custom-pages/<address>.json): whole pages the
# manager makes herself, at layerssuperfoodbar.com/<address>.
# ---------------------------------------------------------------------------
# Web addresses those pages can't have: every page and staff tool the site
# makes itself (render.PAGE_CONFIG "out" — tests/test_edit_mode.py checks the
# two agree), plus paths the hosting uses (Cloudflare's /cdn-cgi, the /api
# functions, /assets) and a few that would only confuse. .pages.yml's address
# pattern lists the same words (address_pattern(); a test checks that too).
SITE_PATHS = ("menu", "story", "how-we-make-it", "what-you-get", "day-in-the-life", "catering", "faq", "visit",
              "gift-cards", "loyalty", "links", "photo-prep", "brand", "edit", "order", "404")
RESERVED_ADDRESSES = SITE_PATHS + ("index", "home", "api", "assets", "cdn-cgi", "admin", "layers", "sitemap",
                                   "robots", "favicon")
ADDRESS = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def site_page(url):
    """The page of this site a link goes to, as a path ("/menu", "/run-club",
    "/" for the homepage), or None when the link isn't to one of the site's
    pages: another website, an email or phone link, a #part of the same page,
    a file (/assets/qr/menu.png, /sitemap.xml). "/menu/", "/menu#bowls" and
    "/menu?x" all go to "/menu". The validator checks that the page exists
    and is switched on; the pages don't draw a link to one that's switched off."""
    u = str(url or "").strip()
    if not u.startswith("/") or u.startswith(("//", "/\\")):
        return None
    path = re.split(r"[?#]", u, maxsplit=1)[0]
    if path.startswith(("/assets/", "/api/")) or "." in path.rsplit("/", 1)[-1]:
        return None
    return path.rstrip("/") or "/"


# ---------------------------------------------------------------------------
# Her pages in the main menu. The desktop menu is one row in the site's
# column (--wrap, 1240 px): the wordmark, the site's five links, hers, then
# the Order button. A page goes in it only while its name fits there — at
# most MAX_MENU_PAGES pages, names of at most MENU_NAME_MAX characters, and
# together no wider than the row's room — so the menu can never crowd, wrap
# or disappear; any other page set to "Main menu and footer" is in the
# footer only, and the validator says why. render.header_more then picks the
# screen width below which the phone menu takes over (styles.css
# .header--more-<width>): the site's own 1100 px, or later when her names
# need the room.
#
# Widths are estimated from the characters, as the menu shows them
# (uppercase Archivo, semi-condensed, 13 px, .08em letter spacing):
# NAV_CHAR_PX was measured in Chrome (Oct 2026); a character that isn't
# listed counts as wider than any letter. +3% covers kerning and rounding
# (real names came out within 1.5%). If the menu's type changes, measure
# again (docs/dev/CMS.md, "Pages of her own").
# ---------------------------------------------------------------------------
MAX_MENU_PAGES = 2          # pages of her own the main menu has room for (the rest go in the footer)
MENU_NAME_MAX = 18          # characters of a name in the main menu ("Name in the menu" allows no more)
NAV_CHAR_PX = {
    **dict(zip("ABCDEFGHIJKLM", (9.02, 9.12, 9.46, 9.53, 8.79, 8.01, 10.17, 9.54, 4.33, 7.65, 8.99, 7.46, 11.09))),
    **dict(zip("NOPQRSTUVWXYZ", (9.55, 10.13, 8.78, 10.13, 9.39, 8.72, 8.21, 9.45, 8.68, 12.04, 8.98, 8.89, 8.47))),
    **dict(zip("0123456789", (7.74, 7.29, 7.74, 7.75, 7.60, 7.79, 7.74, 7.34, 7.71, 7.74))),
    " ": 3.0, "&": 9.28, "'": 3.77, "’": 4.09, "-": 4.97, ".": 4.39, ",": 4.39, "!": 4.55, "?": 7.87,
    ":": 4.72, "/": 4.73, "(": 5.53, ")": 5.53, "+": 8.57, "#": 8.04, "@": 12.62, "–": 6.73, "—": 12.42,
    "É": 8.79, "È": 8.79, "À": 9.02, "Á": 9.02, "Ü": 9.45, "Ñ": 9.55, "Ç": 9.46,
}
NAV_UNKNOWN_PX = 16.0       # emoji and anything else not measured: wider than any letter
NAV_BASE_PX = 615.7         # the site's five links and the Order button, 20 px apart (.header--more)
NAV_GAP_PX = 20             # before each of her links
NAV_EDGES_PX = 257          # the row's padding (2 × 40), the wordmark (121), its gap (24), 32 px to spare
NAV_ROOM_PX = 1240 - NAV_EDGES_PX     # the widest the links can be, on any screen


def nav_width(name):
    """About how wide a name is in the main menu, in pixels."""
    return round(1.03 * sum(NAV_CHAR_PX.get(c, NAV_UNKNOWN_PX) for c in str(name).strip().upper()), 1)


def nav_needed(names):
    """How wide the main menu's links are with her pages' names in it, in pixels."""
    return round(NAV_BASE_PX + sum(nav_width(n) + NAV_GAP_PX for n in names), 1)


def menu_name(page):
    """A page of her own's name in the main menu: its "Name in the menu", or its title."""
    return str(page.get("menu_title") or "").strip() or str(page.get("title") or "").strip()


def address_pattern():
    """The CMS's check on a web address (.pages.yml): lowercase letters,
    numbers and dashes, and none of the reserved words. A JavaScript regex
    (Pages CMS runs it in the browser); the lookahead is the same in Python."""
    return "^(?!(?:" + "|".join(RESERVED_ADDRESSES) + ")$)[a-z0-9]+(?:-[a-z0-9]+)*$"


SHOW_IN_LABELS = {          # the CMS's option labels (.pages.yml), used in messages
    "footer": "Footer only",
    "menu": "Main menu and footer",
    "none": "Nowhere (just the link)",
}


def custom_page_links(pages):
    """Where the published pages of her own are linked: {"menu": [...],
    "footer": [...], "overflow": [(page, why), ...]}. Pages are taken in A–Z
    order of their titles (as the CMS lists them). A page set to "Main menu
    and footer" is in the main menu while it fits there (see above), else in
    the footer only — "overflow", with why: "full" (MAX_MENU_PAGES are
    there already), "long" (its name is over MENU_NAME_MAX characters) or
    "wide" (with the pages already there, the row would be too wide). The
    validator says so. pages: loaded entries (load_all)."""
    shown = sorted((p for p in pages if p.get("published") is True and str(p.get("title") or "").strip()),
                   key=lambda p: (str(p["title"]).strip().casefold(), p.get("slug", "")))
    menu, overflow = [], []
    for p in shown:
        if p.get("show_in") != "menu":
            continue
        name = menu_name(p)
        if len(menu) >= MAX_MENU_PAGES:
            overflow.append((p, "full"))
        elif len(name) > MENU_NAME_MAX:
            overflow.append((p, "long"))
        elif nav_needed([menu_name(q) for q in menu] + [name]) > NAV_ROOM_PX:
            overflow.append((p, "wide"))
        else:
            menu.append(p)
    return {"menu": menu, "overflow": overflow,
            "footer": [p for p in shown if p.get("show_in") in ("menu", "footer")]}

# ---------------------------------------------------------------------------
# One schema per page. "photos" keys map 1:1 to the photo slots in
# src-img/slot-specs.json (home/hero -> photos.hero, home/hero-m ->
# photos.hero_mobile, home/fresh-1 -> photos.fresh_1 …).
# ---------------------------------------------------------------------------
PAGE_SCHEMAS = {
    "home": {
        "seo": _seo(),
        "photos": Obj("Photos", {
            "hero": Photo("Top photo", full_width=True),
            "hero_mobile": Photo("Top photo on phones", alt=False),
            "fresh_1": Photo("Made fresh — photo 1"),
            "fresh_2": Photo("Made fresh — photo 2"),
            "fresh_3": Photo("Made fresh — photo 3"),
            "bowls": Photo("Bowls photo"),
            "smoothies": Photo("Smoothies photo"),
            "visit": Photo("Visit photo", full_width=True),
        }),
        "hero": Obj("Top of the page", {
            "heading": _heading("Big word"),
            "line": _heading("Line under it"),
            "order_label": _cta("Order button text"),
        }),
        "fresh": Obj("Made fresh", {"statement": _heading("Statement")}),
        "film": Obj("Film", {
            "label": Text("Name of the film", required=True, max=80),
            "description": Text("What the film shows", required=True, max=600,
                                help="Read aloud by screen readers in place of the film."),
        }),
        "products": Obj("Bowls and smoothies", {
            "bowls_label": _heading("Bowls tile text"),
            "smoothies_label": _heading("Smoothies tile text"),
            "menu_label": _cta("Menu link text"),
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
            "albums_label": _cta("Albums link text"),
        }),
        "visit": Obj("Visit", {
            "heading": _heading(),
            "directions_label": _cta("Directions button text"),
            "order_label": _cta("Order button text"),
        }),
        "sections": SECTIONS,
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
            "order_label": _cta("Order button text"),
            "menu_label": _cta("Menu button text"),
        }),
        "sections": SECTIONS,
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
        "story_link_label": _cta("Story link text"),
        "menu_label": _cta("Menu button text"),
        "order_label": _cta("Order button text"),
        "sections": SECTIONS,
    },
    "what": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"hero": Photo("Main photo")}),
        "items": _steps("What we make", "Item"),
        "closing": Obj("Closing", {
            "statement": _heading("Statement"),
            "menu_label": _cta("Menu button text"),
            "order_label": _cta("Order button text"),
        }),
        "sections": SECTIONS,
    },
    "day": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {}),
        "sections": SECTIONS,
    },
    "catering": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "inquiry_label": _cta("Inquiry button text"),
        "photos": Obj("Photos", {"hero": Photo("Main photo", full_width=True)}),
        "intro": Text("Introduction", required=True, markdown=True),
        "form": Obj("Inquiry form", {
            "heading": _heading(),
            "submit_label": _cta("Send button text"),
            "reply_note": Text("Note beside the button"),
        }),
        "sections": SECTIONS,
    },
    "visit": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"hero": Photo("Main photo")}),
        "directions_label": _cta("Directions button text"),
        "order_label": _cta("Order button text"),
        "pickup_note": Text("Pickup note"),
        "getting_here": Obj("Getting here", {
            "heading": _heading(),
            "sections": List("Topics", Obj("Topic", {
                "heading": _heading(), "text": Text("Text", required=True, markdown=True)}),
                min=1, item_label=summary_label("Topic", "heading")),
        }),
        "sections": SECTIONS,
    },
    "gift-cards": {
        "published": Bool("Published", default=False),
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "photos": Obj("Photos", {"hero": Photo("Main photo")}),
        "text": Text("Text", required=True, markdown=True),
        "buy_label": _cta("Buy button text"),
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
        "menu_label": _cta("Menu button text"),
        "home_label": _cta("Home button text"),
        "photos": Obj("Photos", {}),
    },
}

_DAY = lambda name: Obj(name, {"closed": Bool("Closed all day"), "open": Time("Opens"), "close": Time("Closes")})

SCHEMAS = {
    "site": {
        "business": Obj("Address and contact", {
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
        "ordering": Obj("Ordering links", {
            "square_url": Url("Square store link", required=True, allow=("https",)),
            "doordash_url": Url("DoorDash link", allow=("https",)),
            "ubereats_url": Url("Uber Eats link", allow=("https",)),
        }),
        "social": Obj("Social media", {
            "instagram_handle": Text("Instagram handle"),
            "tiktok_url": Url("TikTok link", allow=("https",)),
            "facebook_url": Url("Facebook link", allow=("https",)),
            "yelp_url": Url("Yelp link", allow=("https",)),
            "google_url": Url("Google link", allow=("https",)),
        }),
        "seo": Obj(SEO_LABEL, {
            "default_description": Text("Default Google description", required=True, warn_max=160,
                                        warn_why="Search results show about 160 characters."),
            "share_image": Image("Photo for shared links", help="Shown when a link to the site is shared. "
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
        "note": Text("Note under the hours"),
    },
    "announcement": {
        "enabled": Bool("Show the bar"),
        "message": Text("Message", max=110),
        "link_label": Text("Link text", warn_max=30),
        "link_url": Url("Link"),
        "starts": Date("First day shown"),
        "ends": Date("Last day shown"),
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
            "label": _cta("Button text"),
            "url": Url("Link", required=True),
            "highlight": Bool("Green button"),
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
        "order_label": _cta("Order button text"),
        "items": List("Menu items", Obj("Item", {
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
        "sections": SECTIONS,
    },
    "faq": {
        "seo": _seo(),
        "eyebrow": _heading("Small label above the title"),
        "title": _heading("Title"),
        "items": List("Questions", Obj("Question", {
            "question": Text("Question", required=True, warn_max=120),
            "answer": Text("Answer", required=True, markdown=True),
        }), min=1, item_label=summary_label("Question", "question")),
        "sections": SECTIONS,
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
        # empty: the card's own "Limited time" (templates/partials/specials.html)
        "badge": Text("Small label above the name", warn_max=24),
        "tagline": Text("Tagline", warn_max=80),
        "description": Text("Description", markdown=True),
        "highlights": List("Highlights", Text("Highlight", required=True, warn_max=40),
                           item_label=lambda i, x: f"Highlight {i + 1}"),
        "ingredients": Text("Ingredients", multiline=True),
        "price": Text("Price"),
        "image": Image("Photo"),
        "image_alt": Text(ALT_LABEL, max=250),
        "starts": Date("First day shown"),
        "ends": Date("Last day shown"),
        # none: no button, the availability note instead (not on Square, e.g.
        # Phi Velvet); square: "Order on Square" to the store; link: "Order"
        # to the order link below. ORDER_BUTTON_LABELS = the CMS's option labels.
        "order_button": Choice("Order button", tuple(ORDER_BUTTON_LABELS),
                               help="; ".join(ORDER_BUTTON_LABELS.values())),
        "order_url": Url("Order link", allow=("https",),
                         help=f"Only used when the order button is “{ORDER_BUTTON_LABELS['link']}”."),
        "availability_note": Text("Note instead of a button", default="In store for a limited time.", warn_max=60,
                                  help=f"Shown instead of a button when the order button is "
                                       f"“{ORDER_BUTTON_LABELS['none']}”."),
        "show_on_home": Bool("Show on the homepage", default=True),
        "show_on_menu": Bool("Show on the menu", default=True),
        "published": Bool("Published", default=True),
    }),
    "events": ("Event", {
        "title": Text("Title", required=True, warn_max=60, web_name=True),
        "date": Date("Date", required=True),
        "start_time": Time("Start time"),
        "end_time": Time("End time"),
        "partner": Text("With (partner)"),
        "location": Text("Location"),
        "description": Text("Description", markdown=True),
        "image": Image("Photo"),
        "image_alt": Text(ALT_LABEL, max=250),
        "link_url": Url("Link"),
        "link_label": Text("Link text", warn_max=30),
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
    # A whole page of her own, at /<address> (the file is named after the
    # address when the page is made; the CMS can't rename it afterwards).
    "custom-pages": ("Your page", {
        "title": _heading("Page title"),
        "address": Text("Web address", required=True,
                        help="The end of the page's link: lowercase letters, numbers and dashes."),
        "intro": Text("Short intro", multiline=True, warn_max=300,
                      warn_why="It sits under the title in large type: a sentence or two reads best."),
        "photo": Obj("Top photo", {
            "image": Image("Photo", full_width=True),
            "alt": Text(ALT_LABEL, max=250),
            "focus": Choice("Focus", FOCUS, help="Which part of the photo to keep when it's cropped."),
            "zoom": Choice("Zoom", ZOOMS),
        }),
        "sections": SECTIONS,
        "show_in": Choice("Show it in", tuple(SHOW_IN_LABELS), help="; ".join(SHOW_IN_LABELS.values())),
        # the CMS stops more than MENU_NAME_MAX characters (options.maxlength)
        "menu_title": Text("Name in the menu", max=MENU_NAME_MAX,
                           help="A shorter name for the main menu. Empty = the page title."),
        "google_title": Text("Google title", warn_max=60,
                             warn_why="Search results show about 60 characters, so the end may be cut off."),
        "google_description": Text("Google description", warn_max=160,
                                   warn_why="Search results show about 160 characters, so the end may be cut off."),
        "published": Bool("Published", default=True),
    }),
}

# The field a collection entry's file name — its web address — is made from
# (.pages.yml filename templates), named in messages about the file name.
WEB_NAME_FIELDS = {"specials": "name", "events": "title", "albums": "title", "custom-pages": "address"}


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
        if isinstance(node, Blocks):          # a section: its label is added ("Section 2 (Photo)")
            i = int(part)
            value = value[i] if isinstance(value, list) and i < len(value) else {}
            out.append(node.item_label(i, value))
            node = node.block_of(value) or Obj("", {})
            continue
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
