"""
Renders every page of the site from content/ through the Jinja2 templates in
templates/ and writes the result to public/.

  python3 tools/build.py          # the whole build (validate, menu, photos, albums, pages)
  python3 tools/build-pages.py    # pages only, from the photos/albums already built

Content (what the manager edits) comes from content/ via tools/content.py.
Technical page settings — output path, header mode, nav item, body class,
preloads, JSON-LD — live in PAGE_CONFIG below, never in editable content.

Templates get one context with ALL the loaded content (site, hours, menu, faq,
pages, specials, events, albums, announcement, instagram, links), the
date-filtered feature views (announcement_active, specials_active,
events_upcoming, special_hours_upcoming, instagram_posts — "today" is the
shop's date, or --today) plus a few helpers:

  pic(slot, sizes=…, eager=False, mobile=None, …)  responsive <picture>; the alt
        text comes from the content field the slot is bound to in
        src-img/slot-specs.json (e.g. home/fresh-1 -> pages/home photos.fresh_1)
  md(text) / md_inline(text)    the safe text format (tools/textfmt.py)
  menu_html(), albums_html(), hours_table()   the menu, albums and hours blocks
  link_target(url), link_hint(url)   new-tab attributes + screen-reader hint
        for links to other sites (none for pages on this site)
  event_when(event), special_rows   dates and times as the site writes them
  delivery_links                [(name, url)] DoorDash / Uber Eats, only those set
  brand_colours(), png_size(url), qr_codes   the /brand staff page: colour
        tokens read from styles.css, logo sizes, the print QR codes (tools/qr.py)

JSON inside <script> (the albums data, schema.org) is written with <, > and &
escaped (script_json), so no text a manager types can end the script early or
switch the HTML parser into another state ("</script>", "<!--<script>").

Chrome edits happen in templates/base.html and templates/partials/ — never in
public/*.html, which are build output.
"""
import hashlib
import json
import pathlib
import re
import sys
import urllib.parse

import jinja2
from markupsafe import Markup, escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import content as content_mod  # noqa: E402
import hours  # noqa: E402
import instagram  # noqa: E402
import qr  # noqa: E402
import textfmt  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE_URL = "https://layerssuperfoodbar.com"
# Where visits are counted (Cloudflare Web Analytics): the live site only.
# The same build is also published as the GitHub Pages preview and opened
# locally; the beacon's loader in templates/base.html checks the hostname, so
# those visits never reach the numbers.
PRODUCTION_HOSTS = (urllib.parse.urlsplit(SITE_URL).hostname, "www." + urllib.parse.urlsplit(SITE_URL).hostname)
GEO = {"@type": "GeoCoordinates", "latitude": 37.86674, "longitude": -122.25940}

# Desktop header: five links after the wordmark, then the Order button.
HEADER_LINKS = [
    ("menu", "/menu", "Menu"),
    ("story", "/story", "Our Story"),
    ("how", "/how-we-make-it", "How We Make It"),
    ("catering", "/catering", "Catering"),
    ("visit", "/visit", "Visit"),
]

# Mobile drawer, in this order.
DRAWER_LINKS = [
    ("menu", "/menu", "Menu"),
    ("story", "/story", "Our Story"),
    ("how", "/how-we-make-it", "How We Make It"),
    ("what", "/what-you-get", "What We Make"),
    ("day", "/day-in-the-life", "Day in the Life"),
    ("catering", "/catering", "Catering"),
    ("faq", "/faq", "FAQ"),
    ("visit", "/visit", "Visit"),
]

FOOTER_LINKS = [
    ("story", "/story", "Our Story"), ("menu", "/menu", "Menu"),
    ("how", "/how-we-make-it", "How We Make It"),
    ("what", "/what-you-get", "What We Make"),
    ("day", "/day-in-the-life", "Day in the Life"),
    ("catering", "/catering", "Catering"),
    ("faq", "/faq", "FAQ"), ("visit", "/visit", "Visit"),
]

HERO_MEDIA_WIDE = "(min-width: 721px) and (orientation: landscape), (min-width: 1101px)"
HERO_MEDIA_NARROW = "(max-width: 720px), (orientation: portrait) and (max-width: 1100px)"

# Technical settings per page. "content" is the content file the page renders
# ("pages/<key>", "menu" or "faq"); "out" the output slug (index/404 sit at the
# root, every other page is <out>/index.html so clean URLs work on any host).
#   header   "hero" = transparent over a full-bleed hero, solid on scroll (Home);
#            "static" = solid from the top (every other page)
#   signoff  False omits the brand sign-off band above the footer (Home)
#   preload  [(slot, target width, sizes, media)] hero images to preload
PAGE_CONFIG = {
    "home": {"content": "pages/home", "out": "index", "template": "home", "nav": "", "header": "hero",
             "body": "page-home", "signoff": False, "jsonld": True,
             "preload": [("home/hero", 1920, "100vw", HERO_MEDIA_WIDE), ("home/hero-m", 960, "100vw", HERO_MEDIA_NARROW)]},
    "menu": {"content": "menu", "out": "menu", "template": "menu", "nav": "menu", "body": "page-menu"},
    "story": {"content": "pages/story", "out": "story", "template": "story", "nav": "story", "body": "page-story"},
    "how": {"content": "pages/how", "out": "how-we-make-it", "template": "how", "nav": "how",
            "body": "page-story page-how"},
    "what": {"content": "pages/what", "out": "what-you-get", "template": "what", "nav": "what", "body": "page-what"},
    "day": {"content": "pages/day", "out": "day-in-the-life", "template": "day", "nav": "day", "body": "page-day"},
    "catering": {"content": "pages/catering", "out": "catering", "template": "catering", "nav": "catering",
                 "body": "page-catering"},
    "faq": {"content": "faq", "out": "faq", "template": "faq", "nav": "faq", "body": "page-faq"},
    "visit": {"content": "pages/visit", "out": "visit", "template": "visit", "nav": "visit", "body": "page-visit"},
    "404": {"content": "pages/404", "out": "404", "template": "404", "nav": "", "body": "page-404", "noindex": True},
    # Unpublished until their "published" switch is turned on in the CMS. They
    # are not in the navigation; adding a nav link is a developer change.
    "gift-cards": {"content": "pages/gift-cards", "out": "gift-cards", "template": "gift-cards", "nav": "gift",
                   "body": "page-gift"},
    "loyalty": {"content": "pages/loyalty", "out": "loyalty", "template": "loyalty", "nav": "loyalty",
                "body": "page-loyalty"},
    # The Instagram "link in bio" page (content/links.json): light chrome, never
    # indexed, not in the navigation or sitemap. Published while "enabled".
    "links": {"content": "links", "out": "links", "template": "links", "nav": "", "body": "page-links",
              "signoff": False, "noindex": True},
    # Staff tools (CMS_SPEC §11): plain developer copy, not editable content,
    # light chrome (templates/tool.html), never indexed, not in the navigation
    # or sitemap, and left out of the visitor analytics (staff visits would
    # skew them). /photo-prep makes a photo small enough for the CMS upload
    # limit in the browser; /brand is the brand kit (logos, colours, type, QR).
    "photo-prep": {"content": None, "out": "photo-prep", "template": "photo-prep", "nav": "photo-prep",
                   "body": "page-tool page-photo-prep", "signoff": False, "noindex": True, "analytics": False,
                   "tool": True,
                   "seo": {"title": "Prepare a photo | Layers staff tools", "description": ""}},
    "brand": {"content": None, "out": "brand", "template": "brand", "nav": "brand", "body": "page-tool page-brand",
              "signoff": False, "noindex": True, "analytics": False, "tool": True,
              "seo": {"title": "Brand kit | Layers staff tools", "description": ""}},
    # Developer draft: the embedded Square store (see templates/pages/order.html).
    "order": {"content": None, "out": "order", "template": "order", "nav": "order", "body": "page-order",
              "signoff": False, "published": False,
              "seo": {"title": "Order | Layers Superfood Bar",
                      "description": "Order Layers smoothies and bowls online for pickup at 2436 Channing Way, "
                                     "Berkeley. Ordering and payment run securely through Square."}},
}
CONFIG_DEFAULTS = {"header": "static", "signoff": True, "jsonld": False, "noindex": False, "preload": [],
                   "analytics": True, "tool": False}

# The /brand page's colour swatches: (CSS token, name, where it's used). The hex
# values are read from the :root tokens in public/assets/css/styles.css at
# build time, so the brand kit can't drift from the site.
BRAND_COLOURS = [
    ("bop", "Layers green", "The brand colour: buttons, labels, the footer."),
    ("ground", "Wall", "The page background, sampled from the shop's limewash wall."),
    ("ink", "Ink", "Headings and text."),
    ("warm-white", "Cream", "Text and the logo on photos and on the green."),
    ("bop-deep", "Deep green", "Pressed and hover states of green buttons."),
    ("stone", "Stone", "Small print and secondary text."),
    ("butter", "Butter", "Light buttons on photos and on the green."),
    ("sand", "Sand", "Thin dividing lines."),
]

# Delivery services shown on Visit and /links when their link is set
# (content/site.json → Ordering): (key, name).
DELIVERY = [("doordash_url", "DoorDash"), ("ubereats_url", "Uber Eats")]


class BuildError(Exception):
    """A problem the build can explain in plain English."""


def script_json(obj):
    """JSON to sit inside a <script> element. "<", ">" and "&" become \\u003c,
    \\u003e and \\u0026 (still the same JSON once parsed), so nothing in the
    content — "</script>", "<!--<script>" — can end the script or change how
    the browser parses the rest of the page."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def line_breaks(text):
    """The `br` filter, for copy typed in a multi-line box that isn't
    formatted text (content.Text multiline=True): each line escaped, the
    manager's line breaks kept as <br>. Text without line breaks comes out
    exactly as {{ text }} would."""
    lines = re.split(r"\r\n|\r|\n", str(text).strip("\r\n"))
    return Markup("<br>\n".join(str(escape(line)) for line in lines))


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _cat_id(name):
    return "cat-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Site:
    """Everything a page render needs: content, photo manifest, slot specs."""

    def __init__(self, content=None, root=ROOT, today=None):
        self.root = pathlib.Path(root)
        self.c = content if content is not None else content_mod.load_all(self.root)
        self.today = today or hours.shop_today()
        man = self.root / "src-img" / "media-manifest.json"
        self.manifest = json.loads(man.read_text()) if man.is_file() else {}
        self.specs = json.loads((self.root / "src-img" / "slot-specs.json").read_text())
        self.square = self.c["site"]["ordering"]["square_url"]
        self.weekly = self.c["hours"]["weekly"]
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.root / "templates")),
            autoescape=True, undefined=jinja2.StrictUndefined,
            trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
        self.env.filters["tel"] = lambda s: re.sub(r"[^\d+]", "", str(s))
        self.env.filters["br"] = line_breaks
        self.env.globals.update(pic=self.pic, md=self.md, md_inline=self.md_inline, faq_answer=self.faq_answer,
                                menu_html=self.menu_html, albums_html=self.albums_html,
                                hours_table=self.hours_table, link_target=self.link_target,
                                link_hint=self.link_hint, event_when=self.event_when,
                                brand_colours=self.brand_colours, png_size=self.png_size)
        self._instagram = None

    # ------------------------------------------------------------------ text
    def hint_for(self, url):
        """Screen-reader hint for an external link: Square links say so, like
        every hand-written Order link on the site."""
        return " (opens Square in a new tab)" if url.startswith(self.square.rstrip("/")) else textfmt.DEFAULT_HINT

    def md(self, text, p_class=None):
        return textfmt.block(text, p_class=p_class, hint_for=self.hint_for)

    def md_inline(self, text):
        return textfmt.inline(text, hint_for=self.hint_for)

    def link_target(self, url):
        """Links to other sites open in a new tab, like every external link on the site."""
        return Markup(' target="_blank" rel="noopener"') if str(url).startswith("https://") else ""

    def link_hint(self, url):
        url = str(url)
        if not url.startswith("https://"):
            return ""
        hint = (" (opens Instagram in a new tab)" if instagram._host(url) in instagram.IG_HOSTS
                else self.hint_for(url))
        return Markup(f'<span class="sr-only">{escape(hint)}</span>')

    def event_when(self, e):
        """("2026-11-08T09:00", "Sat, Nov 8 · 9am–11am") — the <time> value and the words."""
        d = hours.parse_date(e["date"])
        words = f"{d:%a}, {d:%b} {d.day}"
        stamp = e["date"]
        if hours.parse_time(e["start_time"]) is not None:
            stamp += f"T{e['start_time']}"
            words += f" · {hours.t12(e['start_time'])}"
            if hours.parse_time(e["end_time"]) is not None:
                words += f"–{hours.t12(e['end_time'])}"
        return stamp, words

    def faq_answer(self, text):
        """An answer paragraph; "{hours}" becomes the current hours line."""
        html = self.md(text, p_class="body")
        return Markup(str(html).replace("{hours}", str(escape(hours.line(self.weekly)))))

    # ------------------------------------------------------------------ photos
    def photo_for(self, slot):
        """The content photo a slot is bound to ({image, alt, focus, zoom}), or None."""
        spec = self.specs.get(slot) or {}
        binding = spec.get("content")
        if not binding:
            return None
        src, field = binding.split(":", 1)
        doc = self.c["pages"][src.split("/", 1)[1]] if src.startswith("pages/") else self.c[src]
        val = content_mod.get_path(doc, field)
        return {"image": val, "alt": ""} if isinstance(val, str) else val

    def _srcset(self, slot, ext):
        base = f"/assets/img/{slot}"
        return ", ".join(f"{base}-{w}.{ext} {w}w" for w in self.manifest[slot]["widths"])

    def _need(self, slot):
        if slot not in self.manifest:
            raise BuildError(f"The photo for “{slot}” hasn’t been built yet. Run python3 tools/build.py "
                             "(it builds the photos before the pages).")
        return self.manifest[slot]

    def pic(self, slot, sizes="100vw", eager=False, mobile=None, mmedia="(max-width: 720px)", msizes="100vw",
            id=None, class_=None, style=None, alt=None):
        """<picture> with WebP + JPEG srcsets across every width the photo build made."""
        m = self._need(slot)
        widths, aspect = m["widths"], m["aspect"]
        fallback = min(widths, key=lambda w: abs(w - 1440))
        w, h = fallback, round(fallback / aspect)
        if alt is None:
            photo = self.photo_for(slot)
            alt = (photo or {}).get("alt", "")
        extra = ""
        if id:
            extra += f' id="{_esc(id)}"'
        if class_:
            extra += f' class="{_esc(class_)}"'
        if style:
            extra += f' style="{_esc(style)}"'
        load = ' fetchpriority="high"' if eager else ' loading="lazy"'
        out = ["<picture>"]
        if mobile:
            self._need(mobile)
            out.append(f'<source media="{mmedia}" type="image/webp" srcset="{self._srcset(mobile, "webp")}" sizes="{msizes}">')
            out.append(f'<source media="{mmedia}" type="image/jpeg" srcset="{self._srcset(mobile, "jpg")}" sizes="{msizes}">')
        out.append(f'<source type="image/webp" srcset="{self._srcset(slot, "webp")}" sizes="{sizes}">')
        out.append(f'<img src="/assets/img/{slot}-{fallback}.jpg" srcset="{self._srcset(slot, "jpg")}" sizes="{sizes}" '
                   f'width="{w}" height="{h}" alt="{_esc(alt)}"{load} decoding="async"{extra}>')
        out.append("</picture>")
        return Markup("".join(out))

    def _closest(self, slot, target):
        return min(self._need(slot)["widths"], key=lambda w: abs(w - target))

    # ------------------------------------------------------------------ hours
    def hours_table(self):
        rows = "".join(f'<tr data-dow="{d}"><th scope="row">{name}</th><td>{span}</td></tr>'
                       for d, name, span in hours.table_rows(self.weekly))
        return Markup(f'<table class="hours hours--editorial" data-hours><caption class="sr-only">Opening hours'
                      f'</caption><tbody>{rows}</tbody></table>')

    # ------------------------------------------------------------------ menu
    # The menu, from data/menu-fallback.json (written by
    # tools/sync-menu-from-store.py from the public Square store and
    # content/menu.json). Cards carry the Square item id so the live sync can
    # update prices / sold-out in place.
    def menu_html(self):
        data = json.loads((self.root / "data" / "menu-fallback.json").read_text())
        cats = [c for c in data["categories"] if c["items"]]
        chips = "".join(f'<a class="chip" href="#{_cat_id(c["name"])}" data-chip="{_cat_id(c["name"])}">{_esc(c["name"])}</a>'
                        for c in cats)
        # Items hidden in content/menu.json: the live Square data must not add them back
        hidden = data.get("hidden") or []
        hidden_attr = f' data-hidden-ids="{_esc(" ".join(hidden))}"' if hidden else ""
        out = [f'<nav class="chiprail" data-chip-rail aria-label="Menu categories"><div class="wrap chiprail__track" data-chip-track>{chips}</div></nav>',
               f'<div class="wrap menu-wrap"><div id="menu-root" data-menu-root data-menu-page{hidden_attr}>']
        for c in cats:
            cid = _cat_id(c["name"])
            out.append(f'<section class="menu-group menu-group--{c["style"]}" id="{cid}" data-cat-section aria-labelledby="{cid}-h">')
            out.append(f'<header class="cathead"><h2 class="cathead__name" id="{cid}-h">{_esc(c["name"])}</h2></header>')
            if c["style"] == "list":
                out.append('<ul class="menu-list">')
                for it in c["items"]:
                    name = it["name"] + (f" — {it['note']}" if it.get("note") else "")
                    out.append(f'<li class="menu-list__item" data-id="{_esc(it["id"])}"><span class="menu-list__name">{_esc(name)}</span>'
                               f'<span class="menu-list__price">${_esc(it["price"])}</span></li>')
                out.append("</ul></section>")
                continue
            out.append('<div class="menu-grid">')
            for it in c["items"]:
                slot = it.get("slot")
                has_pic = bool(slot and slot in self.manifest)
                sheet_img, small = None, False
                if has_pic:
                    ws = self.manifest[slot]["widths"]
                    sheet_img = f"/assets/img/{slot}-{min(ws, key=lambda w: abs(w - 960))}.jpg"
                    small = max(ws) < 900          # low-res source: the sheet shows it smaller, never stretched
                item = {k: it.get(k) for k in ("id", "kind", "name", "note", "price", "calories", "highlights", "base",
                                                "toppings", "ingredients", "macros", "allergens", "category_id") if it.get(k)}
                item["image"] = sheet_img
                if has_pic and small:
                    item["image_small"] = True
                media = (self.pic(slot, alt="", sizes="(max-width: 720px) 50vw, (max-width: 1100px) 33vw, 25vw")
                         if has_pic else '<img src="/assets/img/face.png" alt="" width="88" height="88" loading="lazy">')
                ph = "" if has_pic else " menu-card__media--ph"
                meta = f'<span class="menu-card__price">${_esc(it["price"])}</span>' if it.get("price") else ""
                if it.get("calories"):
                    meta += f'<span class="menu-card__cal">{it["calories"]} cal</span>'
                note = f'<span class="menu-card__note">{_esc(it["note"])}</span>' if it.get("note") else ""
                out.append(
                    f'<article class="menu-card" data-id="{_esc(it["id"])}" data-item="{_esc(json.dumps(item, ensure_ascii=False))}">'
                    f'<button class="menu-card__open" type="button" aria-label="{_esc(it["name"])} — details">'
                    f'<span class="menu-card__media{ph}">{media}</span>'
                    f'<span class="menu-card__body"><span class="menu-card__name">{_esc(it["name"])}</span>{note}'
                    f'<span class="menu-card__meta">{meta}</span></span></button></article>')
            out.append("</div></section>")
        out.append("</div></div>")
        return Markup("\n".join(out))

    # ------------------------------------------------------------------ albums
    # Cover tiles + an accessible lightbox viewer, from data/albums.json
    # (written by tools/build-albums.py from content/albums/).
    def albums_html(self):
        path = self.root / "data" / "albums.json"
        if not path.exists():
            return ""
        albums = json.loads(path.read_text())
        tiles = []
        for a in albums:
            ws = a["cover_widths"]
            srcset = lambda ext: ", ".join(f'{a["cover"]}-{w}.{ext} {w}w' for w in ws)  # noqa: E731
            sizes = "(max-width: 720px) 50vw, 33vw"
            tiles.append(
                f'<button class="ed-tile album-tile" type="button" data-album="{_esc(a["slug"])}" '
                f'aria-label="Open album: {_esc(a["title"])}, {a["count"]} photos">'
                f'<span class="ed-media"><picture><source type="image/webp" srcset="{srcset("webp")}" sizes="{sizes}">'
                f'<img src="{a["cover"]}-{ws[1]}.jpg" srcset="{srcset("jpg")}" sizes="{sizes}" width="{ws[1]}" height="{round(ws[1] * 1.25)}" '
                f'alt="" loading="lazy" decoding="async"></picture></span>'
                f'<span class="ed-label"><span class="ed-label__name">{_esc(a["title"])}</span>'
                f'<span class="album-tile__count">{a["count"]} photos</span></span></button>')
        data = [{"slug": a["slug"], "title": a["title"],
                 "photos": [{"src": p["src"], "small": p["small"], "w": p["w"], "h": p["h"], "alt": p["alt"]} for p in a["photos"]]}
                for a in albums]
        payload = script_json(data)
        # balanced rows: 5 albums -> 3 + 2, 6 -> 3 + 3, 7 -> 4 + 3 (short rows are centred)
        n = len(albums)
        cols = n if n <= 4 else 3 if n in (5, 6, 9) else 4
        return Markup(
            f'<div class="albums__grid" style="--album-cols:{cols}">{"".join(tiles)}</div>\n'
            f'<script type="application/json" id="albums-data">{payload}</script>\n'
            '<div id="album-viewer" class="viewer" role="dialog" aria-modal="true" aria-labelledby="viewer-title" hidden>'
            '<div class="viewer__top"><p id="viewer-title" class="viewer__title"></p>'
            '<p class="viewer__count" aria-live="polite"></p>'
            '<button class="viewer__close" type="button" data-viewer-close aria-label="Close album">'
            '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button></div>'
            '<figure class="viewer__stage"><picture><source type="image/webp"><img class="viewer__img" alt=""></picture>'
            '<figcaption class="sr-only" data-viewer-alt></figcaption></figure>'
            '<button class="viewer__nav viewer__nav--prev" type="button" data-viewer-prev aria-label="Previous photo">'
            '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 5 8 12 15 19"/></svg></button>'
            '<button class="viewer__nav viewer__nav--next" type="button" data-viewer-next aria-label="Next photo">'
            '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 5 16 12 9 19"/></svg></button>'
            '</div>')

    # ------------------------------------------------------------------ pages
    def page_content(self, key):
        cfg = PAGE_CONFIG[key]
        src = cfg["content"]
        if src is None:
            return {"seo": cfg["seo"], "photos": {}}
        if src == "links":        # no SEO fields: the page is never indexed
            links = self.c["links"]
            return {**links, "photos": {}, "published": links["enabled"] is True,
                    "seo": {"title": links["heading"].strip() or self.c["site"]["business"]["name"],
                            "description": ""}}
        return self.c["pages"][src.split("/", 1)[1]] if src.startswith("pages/") else self.c[src]

    def published(self, key):
        cfg = PAGE_CONFIG[key]
        return cfg.get("published", True) and content_mod.page_published(self.page_content(key))

    def path_of(self, key):
        out = PAGE_CONFIG[key]["out"]
        return "/" if out == "index" else f"/{out}"

    def _social_links(self):
        s = self.c["site"]["social"]
        out = []
        if s["instagram_handle"].strip():
            out.append(("Instagram", f"https://www.instagram.com/{s['instagram_handle'].strip().lstrip('@')}/"))
        for key, label in (("tiktok_url", "TikTok"), ("facebook_url", "Facebook"), ("yelp_url", "Yelp"),
                           ("google_url", "Google")):
            if s[key].strip():
                out.append((label, s[key].strip()))
        return out

    def _hero_image(self):
        return f"{SITE_URL}/assets/img/home/hero-{self._closest('home/hero', 1440)}.jpg"

    def _share_image(self):
        if self.c["site"]["seo"]["share_image"].strip() and "site/share" in self.manifest:
            return f"{SITE_URL}/assets/img/site/share-{self._closest('site/share', 1200)}.jpg"
        return self._hero_image()

    def _jsonld(self):
        b = self.c["site"]["business"]
        ld = {"@context": "https://schema.org", "@type": "Restaurant", "name": b["name"],
              "servesCuisine": ["Smoothies", "Açaí bowls"],
              "address": {"@type": "PostalAddress", "streetAddress": b["street"], "addressLocality": b["city"],
                          "addressRegion": b["region"], "postalCode": b["postal_code"], "addressCountry": "US"},
              "geo": GEO,
              "url": f"{SITE_URL}/", "menu": f"{SITE_URL}/menu",
              "image": self._hero_image(),
              "sameAs": [url for _, url in self._social_links()],
              "potentialAction": {"@type": "OrderAction", "target": self.square},
              "openingHoursSpecification": hours.jsonld(self.weekly)}
        special = hours.jsonld_special(hours.upcoming_special(self.c["hours"], self.today))
        if special:
            ld["specialOpeningHoursSpecification"] = special
        if b["phone"].strip():
            ld["telephone"] = b["phone"].strip()
        return Markup(script_json(ld))

    def brand_colours(self):
        """[{token, name, use, hex}] for the /brand swatches, from the CSS tokens."""
        css = self.root / "public" / "assets" / "css" / "styles.css"
        if not css.is_file():                  # a content-only copy (tests): the code's own stylesheet
            css = ROOT / "public" / "assets" / "css" / "styles.css"
        m = re.search(r":root\s*\{(.*?)\}", css.read_text(encoding="utf-8"), re.S)
        tokens = dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b", m.group(1) if m else ""))
        missing = [t for t, _, _ in BRAND_COLOURS if t not in tokens]
        if missing:
            raise BuildError(f"The brand kit needs the colour token(s) {', '.join(missing)} at the top of "
                             "styles.css. This is a developer problem, not your content.")
        return [{"token": t, "name": n, "use": u, "hex": tokens[t].upper()} for t, n, u in BRAND_COLOURS]

    def png_size(self, url):
        """(width, height) of a PNG under public/ ("/assets/img/x.png"), read from its header."""
        rel = pathlib.Path("public") / url.lstrip("/")
        f = self.root / rel if (self.root / rel).is_file() else ROOT / rel
        head = f.read_bytes()[:24]
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            raise BuildError(f"{url} isn't a PNG file. This is a developer problem, not your content.")
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")

    def qr_codes(self):
        """The print QR codes (tools/qr.py writes the files): name, label, use, url, files."""
        return [{"name": name, "label": qr.CODES[name][0], "use": qr.CODES[name][1], "url": url,
                 "svg": f"/assets/qr/{name}.svg", "png": f"/assets/qr/{name}.png"}
                for name, url in qr.targets(self.c).items()]

    def instagram_doc(self):
        if self._instagram is None:
            self._instagram = instagram.load(self.c, self.root)
        return self._instagram

    def feature_context(self):
        """Date-filtered views of the new-feature content, for the templates."""
        t, c = self.today, self.c
        ann = c["announcement"]
        ig = c["instagram"]
        handle = c["site"]["social"]["instagram_handle"].strip().lstrip("@")
        active = [s for s in c["specials"] if s["published"] and s["name"].strip()
                  and hours.in_window(t, s["starts"], s["ends"])]
        msg = ann["message"].strip()
        return {
            "announcement_active": ann if (ann["enabled"] and msg
                                           and hours.in_window(t, ann["starts"], ann["ends"])) else None,
            # remembers a dismissal per message: a new message shows again
            "announcement_key": hashlib.sha256(f"{msg}|{ann['link_url'].strip()}".encode()).hexdigest()[:12],
            "specials_active": active,
            "specials_home": [s for s in active if s["show_on_home"]],
            "specials_menu": [s for s in active if s["show_on_menu"]],
            "events_upcoming": sorted((e for e in c["events"] if e["published"] and e["title"].strip()
                                       and (d := hours.parse_date(e["date"])) and d >= t),
                                      key=lambda e: (e["date"], e["start_time"])),
            "special_hours_upcoming": hours.upcoming_special(c["hours"], t),
            "special_rows": hours.special_rows(hours.upcoming_special(c["hours"], t)),
            "instagram_on": ig["enabled"] is True,
            "instagram_posts": self.instagram_doc()["posts"] if ig["enabled"] else [],
            "instagram_handle": handle,
            "instagram_url": f"https://www.instagram.com/{handle}/" if handle else "",
        }

    def context(self, key):
        cfg = {**CONFIG_DEFAULTS, **PAGE_CONFIG[key]}
        page = self.page_content(key)
        b = self.c["site"]["business"]
        address = f"{b['street']}, {b['city']}, {b['region']} {b['postal_code']}"
        ctx = dict(self.c)
        ctx.update(self.feature_context())
        if cfg["tool"]:            # staff tools: no customer announcement above their own header
            ctx["announcement_active"] = None
        ctx.update(
            page=page, seo=page["seo"], cfg=cfg, today=self.today,
            canonical=f"{SITE_URL}{self.path_of(key)}",
            share_image=self._share_image(),
            # single-quoted attribute (as main.js has always read it): only & ' < need escaping
            hours_meta=Markup(hours.meta(self.weekly, hours.upcoming_special(self.c["hours"], self.today))
                              .replace("&", "&amp;").replace("'", "&#39;").replace("<", "&lt;")),
            hours_line=hours.line(self.weekly),
            hours_groups=hours.groups(self.weekly),
            preloads=[{"href": f"/assets/img/{slot}-{self._closest(slot, w)}.webp",
                       "srcset": self._srcset(slot, "webp"), "sizes": sizes, "media": media}
                      for slot, w, sizes, media in cfg["preload"]],
            jsonld=self._jsonld() if cfg["jsonld"] else "",
            # the beacon's settings as a JS string, and the hosts it may run on
            analytics_beacon=Markup(script_json(json.dumps(
                {"token": self.c["site"]["analytics"]["cloudflare_web_analytics_token"].strip()}))),
            analytics_hosts=Markup(script_json(list(PRODUCTION_HOSTS))),
            header_links=HEADER_LINKS, drawer_links=DRAWER_LINKS, footer_links=FOOTER_LINKS,
            social_links=self._social_links(),
            delivery_links=[(name, self.c["site"]["ordering"][k].strip()) for k, name in DELIVERY
                            if self.c["site"]["ordering"][k].strip()],
            qr_codes=self.qr_codes(),
            directions_url="https://www.google.com/maps/dir/?api=1&destination="
                           + urllib.parse.quote_plus(address, safe=","),
        )
        return ctx

    def render(self, key):
        try:
            return self.env.get_template(f"pages/{PAGE_CONFIG[key]['template']}.html").render(self.context(key))
        except jinja2.UndefinedError as e:
            raise BuildError(f"The {key} page uses something the content doesn't have ({e}). "
                             "This is a template problem, not your content — ask the developer.") from None

    def render_all(self):
        """{key: html or None (unpublished)} — everything in memory, nothing written yet."""
        return {key: (self.render(key) if self.published(key) else None) for key in PAGE_CONFIG}


def dest_for(out_dir, key):
    out = PAGE_CONFIG[key]["out"]
    return out_dir / f"{out}.html" if out in ("index", "404") else out_dir / out / "index.html"


def write_pages(site, rendered, out_dir):
    """Write rendered pages, unpublish drafts, then sitemap.xml + robots.txt."""
    out_dir = pathlib.Path(out_dir)
    written = []
    for key, html in rendered.items():
        dest = dest_for(out_dir, key)
        if html is None:
            stale = dest.parent if dest.name == "index.html" and dest.parent != out_dir else None
            if stale and stale.is_dir():            # unpublish a page that was turned off
                for f in stale.iterdir():
                    f.unlink()
                stale.rmdir()
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        written.append(dest)
    urls = sorted(SITE_URL + site.path_of(k) for k, html in rendered.items()
                  if html is not None and not PAGE_CONFIG[k].get("noindex"))
    (out_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    (out_dir / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    return written, urls


def main():
    """Pages only (tools/build.py runs this after the menu, photos and albums)."""
    import validate_content
    problems = validate_content.validate(ROOT)
    errors = [p for p in problems if p["level"] == "error"]
    if errors:
        print(validate_content.format_problems(errors))
        sys.exit(1)
    try:
        site = Site()
        rendered = site.render_all()
    except BuildError as e:
        sys.exit(f"error: {e}")
    written, urls = write_pages(site, rendered, ROOT / "public")
    for key, html in rendered.items():
        state = "unpublished" if html is None else str(dest_for(ROOT / "public", key).relative_to(ROOT))
        print(f"  {key:12s} {state}")
    print(f"\n{len(written)} pages built (+ sitemap.xml with {len(urls)} URLs, robots.txt).")


if __name__ == "__main__":
    main()
