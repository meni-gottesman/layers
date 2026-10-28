# Layers Superfood Bar — website

Production build of an **editorial, multi-page site** in the format of Happier
Grocery, told with Layers' own photography, film and copy. Static front end on
**Cloudflare Pages**, plus two **Pages Functions** for the menu and the
catering form.

Everything a visitor reads comes from **`content/`** — JSON files the
marketing manager edits through **Pages CMS** (`.pages.yml`; how it's set up:
[docs/dev/CMS.md](docs/dev/CMS.md); her guide: [docs/HANDBOOK.md](docs/HANDBOOK.md)).
She starts at **/edit**, which turns on **Edit buttons on the website
itself** (each opens that part of the page in the editor), can add **sections
of six kinds** to any main page and make **whole pages of her own** — all in
the site's own design ([Editing](#editing-edit-buttons-sections-and-pages-of-her-own)).
Pages are rendered from **`templates/`** (Jinja2) by **`tools/build.py`**.
`public/*.html` is build output: edit content, templates or tools, never the
output. Every save in the CMS is a commit to `main`; GitHub Actions checks it,
builds the site and publishes it — see [Publishing](#publishing) and
[docs/SETUP.md](docs/SETUP.md).

Design system: **Archivo** (one family, semi-condensed for display, labels and
navigation), the shop's limewash wall **#E5E0D8** as the ground, **Birds of
Paradise green #3A4A2C** as the brand colour, and square corners. Tokens live at
the top of `public/assets/css/styles.css`. Editorial components are in its "V3"
(Home and Story) and "V4" (inner pages and menu) blocks; later rules win.

```bash
pip3 install -r requirements.txt  # CI installs the exact versions in requirements.lock
python3 tools/build.py            # validate → menu → instagram → images → albums → qr → pages → cleanup
python3 -m pytest -q              # tests (against frozen seed content, never content/)
```

**Published pages:** Home, Menu, The Layers Story, How We Make It, What We
Make, A Day at Layers, Catering, FAQ, Visit and 404 — plus **/links**, the
Instagram "link in bio" page (light chrome, never indexed, not in the
navigation or sitemap; `content/links.json`, on while "enabled"; the build
warns when it's switched off, because the printed QR codes point at it).

**Staff pages** (developer copy in the templates, not CMS content; light
chrome `templates/tool.html`; noindex, not in the navigation or sitemap, no
analytics, no announcement bar): **/edit** is the start page for changing the
website (turns on the Edit buttons, links straight into the editor);
**/photo-prep** shrinks a photo in the
browser — nothing is uploaded — to a JPEG of at most 2,400 px and under 3 MB,
the hosted CMS's upload limit (`public/assets/js/staff.js`); **/brand** is the
brand kit: logo downloads, the colour tokens (read from `styles.css` at build
time), Archivo, the print QR codes and photo do's and don'ts.

**Unpublished (built only when switched on):** Gift Cards and Loyalty — each
has `"published": false` in its `content/pages/*.json`. Gift Cards waits on
Square eGift Cards being switched on (the old eGift link is disabled) and on a
photo; Loyalty waits on the programme details. An unpublished page is left out
of the sitemap and its old output is removed; adding a published page to the
navigation is a developer change (`HEADER_LINKS`/`DRAWER_LINKS` in
`tools/render.py`) — the build report warns when a page is switched on that no
menu links to, and a page still holding placeholder copy ("[… client to
supply]") can't be published.

```
.pages.yml                   Pages CMS configuration (docs/dev/CMS.md)
.github/workflows/           publish, menu refresh, backups, restore, undo, keep-alive (docs/SETUP.md)
content/                     ← the ONLY thing the manager edits (Pages CMS)
  site.json                    business details, ordering + social links, SEO default, analytics
  hours.json                   weekly hours + special/holiday hours
  menu.json                    menu page copy + how each Square item is shown
  faq.json                     FAQ page copy + questions and answers
  pages/<page>.json            copy + photos per page (home, story, how, what, day,
                               catering, visit, gift-cards, loyalty, 404)
  albums/<slug>.json           photo albums
  announcement.json            the thin bar above the header (dates, dismissible)
  instagram.json               the homepage Instagram grid: hand-picked posts or a Behold feed
  links.json                   the /links page
  specials/<slug>.json         limited-time drinks/bowls: homepage band, top of /menu, /links
  events/<slug>.json           "Coming up": homepage community section and /links
  custom-pages/<address>.json  pages she makes herself, at /<address> ("Your own pages")
templates/                   Jinja2: base.html (chrome), tool.html (staff pages), partials/ (sections.html =
                               "More sections"), pages/<page>.html (custom.html = her own pages, edit.html = /edit)
public/                      deployed as-is (build output + hand-written assets)
  assets/css/styles.css        design system
  assets/js/main.js            header, drawer, film, menu sheet + live merge, open-now, form, motion,
                               announcement bar, dated specials/events between builds, staff mode (Edit buttons)
  assets/js/staff.js           /photo-prep and /brand only
  assets/js/vendor/            GSAP + ScrollTrigger, self-hosted
  assets/img/<group>/          every photo, WebP + JPEG at several widths (built)
  assets/albums/<slug>/        album photos + covers (built)
  assets/video/                homepage film + posters (built)
  assets/data/                 menu-fallback.json, served to /api/menu
  assets/qr/                   print QR codes (menu, order, links), SVG + 1024 px PNG (built)
functions/api/menu.js        GET  /api/menu      — Square catalog (live prices / sold-out)
functions/api/catering.js    POST /api/catering  — inquiry delivery
data/                        menu-fallback.json, albums.json, instagram.json (built) + the cached Square store snapshot
src-img/originals/           full-resolution photos placed on the site
src-img/albums/<NN-slug>/    the album photos
src-img/menu/                Square product photos (downloaded by the menu sync)
src-img/uploads/             where CMS uploads land
src-img/instagram/           the last Behold feed + its photos (not in git; kept in the CI cache)
src-img/existing-photos.json photos placed before the CMS, each with the spots it was checked in
                             (exempt from the size rule there only)
src-img/slot-specs.json      TECHNICAL photo specs: aspect, sizes, today's tuned crop + retouch
src-img/media-manifest.json  built photo widths + fingerprints (incremental builds)
src-img/album-manifest.json  built album photo fingerprints
src-img/PROVENANCE.json      where each original came from (Drive, Wix, Square, Instagram post)
src-img/library/             full-size photos not currently placed (not in git)
src-video/clips/             the client's clips used in the film; film.json = the cut
tools/                       build scripts, local dev server; tools/ci/ = the workflows' helpers
tests/                       pytest; tests/fixtures/seed/ = the frozen seed content the tests use
docs/                        HANDBOOK.md (the manager), SETUP.md (owner/developer), dev/ (specs, CMS notes)
requirements.txt             what the build needs (lower bounds); requirements.lock = CI's exact versions
```

## The build

`python3 tools/build.py` is the single entry point (CI runs exactly this):

1. **validate** — `tools/validate_content.py` checks every content file (also
   runnable alone). Any error stops the build *before anything in `public/` or
   `data/` is touched*.
2. **menu** — `data/menu-fallback.json` is re-made offline from the cached
   Square data + `content/menu.json`.
3. **instagram** — `tools/instagram.py` picks the homepage posts: the
   hand-picked ones, or the Behold feed — the build's only network request,
   made only when the last fetch is over 12 hours old or `--refresh-instagram`
   (the daily scheduled build) asks; Behold's free plan counts every request.
4. **images** — every photo slot (`tools/build-home-media.py`), incremental.
5. **albums** — `tools/build-albums.py`, incremental.
6. **qr** — the print QR codes (`tools/qr.py`, segno): menu, order (the
   Square store link in `site.json`) and links, written only when they change.
7. **pages** — every page rendered in memory (`tools/render.py`), then
   checked (every `/assets/` file it references must exist) and only then
   written, with `sitemap.xml` and `robots.txt`.
8. **cleanup** — photo files nothing uses any more (old widths, removed
   slots, unpublished albums) are deleted, only now: a build that fails at
   "pages" leaves the current pages with every file they point at.

Every run writes **`build-report.json`** and **`build-report.md`** (plain
English, for the manager — CI posts it when an update doesn't publish). Exit
code 1 means nothing was published. `--check` validates only; `--today
YYYY-MM-DD` builds as if it were another day (date-based content);
`--force-images` rebuilds every photo; `--offline` skips the Instagram feed
(the last fetched one is reused); `--refresh-instagram` fetches it even if
it's recent.
Run the suite on the oldest supported Python too: `tests/test_compat.py`
compiles every file with a Python 3.11 if it finds one (`PYTHON311=…`).

`python3 tools/build-pages.py` re-renders the pages alone (template work).

## Content

`tools/content.py` holds one **schema per content file**. It drives the
validator's checks and messages, fills defaults (so templates never meet a
missing key), and its field labels are the labels to use in `.pages.yml`.
Pages CMS **deletes undeclared keys and empty values** when it saves, so the
build always reads content through that defaults layer (a missing key equals
its default), every key the site reads must be declared in `.pages.yml`, and
technical values stay out of content (`src-img/slot-specs.json`,
`PAGE_CONFIG` in `tools/render.py`).

Validation problems are `{level, where, field, message, file}` with the CMS's
labels, e.g. `Opening hours › Saturday → Opens: “9am” isn’t a time. Use the
24-hour format HH:MM …`; a list item is named by its number and the text the
CMS shows on it (`Question 3 (“How late are you open?”)`, `Bowls · Mango
Coco`). Errors block publishing, warnings don't. Content that isn't shown — an
unpublished page, special, event or album, a switched-off announcement, a
special whose end date has passed, a past event, a menu item set to "Hide
from the website" — can't break the site, so its errors are reported as
warnings marked `"draft": true`; the report folds those into a separate "Not
on the site" section, so the manager's "Worth a look" list only holds things
that are live. User text in `build-report.md` is Markdown-escaped (and `@`/`#`
defused), because GitHub shows it — the issue is public.

Pages CMS saves a file in its own format (empty values dropped, keys in field
order, no final newline). `tools/cms_normalize.py` does the same from
`.pages.yml`, so after editing content by hand run `python3
tools/cms_normalize.py` (CI runs `--check` as a developer-only step that never
stops a publish). (The three seed SEO descriptions on Menu, Story and Catering are
over 160 characters and stay as warnings until the owner approves shorter
ones — they are the owner's approved copy.)

Copy vs. developer text: everything a visitor reads is in `content/`. Screen-
reader landmark names on sections ("Bowls and smoothies", "Photo albums", "Catering
inquiry" …), button-chrome labels ("Order on Square", "Follow @handle",
"Coming up", "Special hours") and form fields stay in the templates as
developer copy; the film's own name and description are content
(`pages/home.json` → `film.label`, `film.description`).

Long text fields (story chapters, FAQ answers, the catering intro, getting-here
notes) use a tiny safe format, `tools/textfmt.py`: blank line = paragraph, line
break = `<br>`, `**bold**`, `*italic*`, `[text](https://… | /page | #id |
mailto: | tel:)`. The input is escaped first; there is no way to write HTML.
External links open in a new tab with a screen-reader hint. `{hours}` in an
FAQ answer becomes the current hours line.

## Editing: Edit buttons, sections and pages of her own

- **Edit buttons (staff mode).** Every region of every page carries
  `data-edit="<editor link>" data-edit-label="Edit the opening hours"`
  (`render.edit_attr`); `<body>` carries `data-edit-root` (the editor) and
  `data-edit-page` (this page's own screen). With `?edit` in the address
  (the /edit page's "Show Edit buttons on the website"; remembered in this
  browser, `?edit=off` to stop), `main.js` adds a small "✎ Edit" link in
  each region's corner (it opens the editor in a new tab) and a bar: "Edit
  this page · Open the editor · Hide edit buttons". An album's link is in
  the album viewer. Without the switch nothing is added and nothing is
  fetched: visitors' pages differ from before only by the attributes. The
  repository is written **once, `render.REPO` / `render.BRANCH`**
  (`EDITOR_URL`, and the guide's link on /edit); `render.editor_link` builds
  Pages CMS's own routes from it (`/file/<name>`,
  `/collection/<name>[/edit/<path>|/new]`; an entry's `.json` is written
  `%2Ejson` so signing in on the way returns her to it), and a test checks
  every link against `.pages.yml`. /edit also lists the last build's
  warnings ("Worth a look"), each linked to its screen.
- **More sections.** Home, Story, How We Make It, What We Make, A Day at
  Layers, Catering, Visit, FAQ and Menu (and her own pages) have
  `sections`: a list of six kinds — Text, Photo (wide or standard), Photo
  and text, Row of photos (2–4), Button, Quote — drawn after the page's own
  content (Home: after Instagram, before the Visit band; Story, How, What:
  before the closing words) by
  `templates/partials/sections.html` from the site's own editorial pieces.
  Their photos are slots `blocks/<page>_<n>[_<k>]` built like every other
  photo (21:9, 3:2, 4:5, 1:1). No sections = the page is exactly as before.
- **Your own pages** (`content/custom-pages/<address>.json`): title,
  address, intro, top photo, sections, where it's linked (footer, main menu
  and footer, or nowhere), a shorter "Name in the menu", Google title and
  description, Published. Rendered at `/<address>` (its file's address,
  whatever the box says later) with the site chrome
  (`templates/pages/custom.html`), in the sitemap while published. An
  address the site uses itself is refused (`content.RESERVED_ADDRESSES`), and
  one never replaces a site page even unchecked. The main menu takes her
  pages only while they fit (2 at most, names up to 18 characters, measured
  widths); the phone menu takes over no sooner than the names need
  (`render.header_more`).
- **Links to the site's own pages** in her content are checked: one to a
  page that doesn't exist stops the update (with "Did you mean …?"); one to
  a page that's switched off isn't drawn until the page is back.

- **Written for a non-technical editor.** Every CMS screen starts with what
  is changed most (Published first in a collection, holidays before the
  weekly hours, the menu items before the menu's headings) and ends with
  what's rarely needed (a photo's Focus/Zoom, the film's spoken texts,
  “Google and shared links”); labels are everyday words (“Photo
  description”, “Google title”, “Order button text”), and a box that can be
  left empty says so first (“Optional — …”). Analytics is hidden (still declared, so a save
  keeps it). `tests/test_cms_wording.py` keeps it that way.

How the CMS side works (the `block` field, its traps, how a kind of section
is added, the form order and wording rules): [docs/dev/CMS.md](docs/dev/CMS.md#sections-and-pages-of-her-own).

## Hours, address, ordering

Opening hours live in **one place**, `content/hours.json` (24h `HH:MM`, a day
can be `"closed": true`). They are rendered into the footer, the Visit table,
the homepage line, the FAQ, schema.org data and a `<meta name="layers-hours">`
tag that drives the "Open now" label. **Special hours** (holidays: a date, a
name, closed or other times) win over the weekly hours on their date: the next
60 days are listed under the Visit table, sent to search engines as
`specialOpeningHoursSpecification`, and added to the meta payload as a
`"special"` map, so "Open now" says "Closed today" on Thanksgiving. The
optional hours note shows under the table. The current values come from Layers'
Square business hours, which Google and Yelp match. Address, cross streets,
the Square store link (https://layerssuperfoodbar.square.site) and social
links are in `content/site.json`.

## Menu

```bash
python3 tools/sync-menu-from-store.py   # pull the public Square store (no credentials)
python3 tools/build.py
```

The sync reads Layers' public Square Online catalog and writes
`data/menu-fallback.json`, keeping names, prices, calories, ingredients,
nutrition and allergen sentences verbatim. It deliberately **drops Square's
dietary tags**, because several contradict the items' own allergen lines. The
build renders the menu from that file, so it ships complete with no Square
token.

`content/menu.json` decides how each Square item is shown: the name and note
on the site (empty = Square's), a photo (empty = Square's upload), crop focus
and zoom, and whether it's hidden. Hidden ids are listed in the built menu
data, so neither `/api/menu` nor the page's live merge can bring a hidden item
back once Square is connected. Each card's photo slot is named after its shown
name; two items never share one (a duplicate or letter-less name gets an id
suffix, and the validator warns about duplicate names). **List order = menu order** within each
category. A live sync appends items Square has added (with empty fields) and
refreshes the read-only `square_name`/`category`, keeping the manager's edits;
items Square dropped are skipped with a warning. A Square photo stays tied to
its item id, so renaming an item on the site keeps its photo. The build runs
the sync with `--offline` (cached data, no network).

Once `SQUARE_ACCESS_TOKEN` is set, `/api/menu` returns live catalog data. The
page then marks sold-out items on the existing cards (matched by Square item id)
and adds any brand-new item. It never swaps the curated photos or details for
Square thumbnails. Prices come from the sync script, because the store's
displayed price includes a required +$0.25 option that the Catalog API leaves
out. Re-run the sync when prices change.

## Ordering

Every "Order" button opens Layers' Square Online store in a new tab, as the
client asked. Square runs the cart, pickup time and payment. A menu item's
button opens the store at that item's category (`<store>/#<category id>`):
the store has no per-item URLs, and its product links 404. An embedded version
of the store is kept as a developer draft (`templates/pages/order.html`,
never published) in case it's wanted later.

## Instagram, specials, events, the announcement bar

- **Instagram** (`content/instagram.json`): a grid of posts on the homepage,
  before the Visit band, each linking to its post. *Hand-picked* mode uses
  photos already in `src-img/`; *auto* mode reads a Behold JSON feed
  (`https://feeds.behold.so/<id>`) **at build time only** — Behold's free plan
  counts every feed request and pauses at 1,200 a month, so visitors' browsers
  never call it. The post link must be on instagram.com and the image on
  behold.pictures; the images are downloaded to `src-img/instagram/` and built
  like every other photo (slots `instagram/1…`). Any feed problem, or fewer
  than 3 usable posts, falls back to the hand-picked posts and the report says
  why. No posts at all → just the "Follow @handle" link.
- **Specials** (`content/specials/`): a "Limited time" band after the products
  on the homepage, cards at the top of /menu and on /links (one special: photo
  beside text; several: a row). **Order button** (`order_button`): `none`
  (the default) shows the availability note instead ("In store for a limited
  time."), `square` → "Order on Square" to the store, `link` → "Order" to the
  special's `order_url`. Dates are honoured at build time and, for the end
  date, by main.js between builds (a row left with one card is laid out as a
  single special).
- **Events** (`content/events/`): "Coming up" in the homepage community
  section (above "See every album") and on /links, soonest first; past events
  drop out.
- **Announcement bar** (`content/announcement.json`): above the header on
  every page while switched on and between its dates (checked again in the
  browser), dismissible and remembered per message. On Home the header joins
  the flow under the bar so it isn't covered.

- **Delivery links** (`site.json` → `ordering.doordash_url` / `ubereats_url`):
  a quiet "Delivery: DoorDash · Uber Eats" line under the Visit buttons and
  "Delivery on …" buttons on /links; nothing when empty.
- **Analytics** (`site.json` → Cloudflare Web Analytics token): the beacon is
  loaded only on the live hostnames (`PRODUCTION_HOSTS` in `tools/render.py`),
  never on the GitHub Pages preview or localhost, and never on staff pages.

A daily scheduled build keeps all of these current.

## Albums

The photo albums on "A Day at Layers" are `content/albums/<slug>.json`: title,
position (`order`), `published`, cover photo + focus, and the photos with their
alt texts, in order. Photos can live anywhere under `src-img/` (the originals
are in `src-img/albums/<NN-slug>/`, CMS uploads in `src-img/uploads/`). Each
photo gets a light retouch and is saved at 960 and 1600 px, plus a 4:5 cover;
`data/albums.json` (same shape as always) feeds the page. Tiles open an
accessible full-screen viewer (arrow keys, swipe, Escape).

## Photography

```bash
python3 tools/build-home-media.py --images           # every photo (incremental)
python3 tools/build-home-media.py --only home/hero,menu/strawesome
```

Each place a photo appears is a **slot**. *Which* photo is content (e.g.
`content/pages/home.json` → `photos.hero`, with `focus`/`zoom` keywords). *How*
it is cut is technical, in `src-img/slot-specs.json`:

```json
"home/hero": {"content": "pages/home:photos.hero", "aspect": "16:10", "widths": "full",
              "tuned": {"image": "src-img/originals/prep-cap-topdown.jpg", "focal": [0.58, 0.5],
                        "zoom": 1.0, "edit": {"wb": 0.3, "exposure": 0.35, "shadows": 0.3, "denoise": 1}}}
```

- **The tuned rule.** While the content points at `tuned.image` with focus and
  zoom on `auto`, the hand-tuned focal/zoom/edit are used exactly. A new photo
  (or a changed focus/zoom) is cropped by the keywords — focus `auto`
  (centre), `top`, `bottom-left`, …; zoom `auto`/`none` 1.0, `a-little` 1.15,
  `more` 1.35 — and gets a gentle default retouch. Menu photos are tuned by
  `square_id`; Square's own product photos keep the studio recipe.
- **Crop.** The largest frame of that aspect around the focal point; `zoom`
  tightens it.
- **Retouch.** `tools/photo_edit.py` does white balance (with highlight
  protection), exposure, levels, shadows/highlights, contrast, vibrance, a
  light house grade so five cameras read as one set, noise reduction, and
  sharpening tuned per output size. Outputs carry no camera metadata (no GPS).
- **Output sizes.** Photos are never upscaled. A crop that falls between two
  standard widths is also served at its own width.
- **Incremental.** Each slot's fingerprint (source bytes, spec, edit, pipeline
  code) is in `src-img/media-manifest.json`; unchanged slots are skipped and
  stale outputs (a width that went away, a renamed menu item) are deleted.
- **In templates**, `{{ pic("home/bowls", sizes="…") }}` expands to a
  `<picture>` with WebP + JPEG srcsets; the alt text comes from the content
  field the slot is bound to.
- **Photo sizes.** Every photo a content field points at — an upload, or a
  file added to any `src-img/` folder — must be big enough for its spot
  *after* the crop (the spot's shape and the zoom): 1200 px wide for
  full-width spots, 800 px elsewhere; a crop keeping under half the photo (a
  portrait photo in a wide band) gets a warning. It must also open completely
  (a damaged upload is named in the report, not discovered by the photo
  build). Photos placed before the CMS are listed in
  `src-img/existing-photos.json` with the spots they were checked in, and are
  exempt **there only** — a small Square product photo picked for the hero is
  refused like any other.
- **Colour.** `tools/photo_load.py` opens every source photo as 8-bit sRGB:
  a Display P3 (iPhone) photo is converted rather than washed out,
  transparency is flattened onto white, 16-bit grayscale is scaled. Ordinary
  photos go through exactly as before, so their fingerprints don't change.
- **Per-entry slots.** Instagram posts (`instagram/<n>`, square), specials
  (`specials/<slug>`, 4:5) and events (`events/<slug>`, square thumbnail) get
  slots from `content.ENTRY_SLOTS`; the photos in "More sections" and on her
  own pages get `blocks/<page>_<n>[_<k>]`, `custom/<address>_<n>[_<k>]` and
  `custom/<address>_top` (`content.section_photos`); a `slot-specs.json`
  entry with the same name adds tuning (the Phi Velvet studio shot keeps the
  studio recipe).

**To swap a photo:** in the CMS, choose the new photo in that spot (it lands in
`src-img/uploads/`) and pick a focus; or by hand, put the file under `src-img/`
and point the content field at it. No HTML or CSS changes. To hand-tune it,
set the slot's `tuned` block in `src-img/slot-specs.json`.

Requires Python 3 with Pillow and numpy. OpenCV (`opencv-python-headless`)
enables noise reduction, and `pillow-heif` reads iPhone HEIC files.

## Film

```bash
python3 tools/compose-film.py               # cut the film from src-video/film.json
python3 tools/build-home-media.py --film    # encode for the web + posters
```

The client's footage is almost all vertical phone video, so the wide film is a
**triptych**: three vertical columns that each loop their own clips with soft,
staggered crossfades. Each column shows phone footage near its native
resolution instead of blowing it up to 2.33:1. Phones get a single vertical
column. Each loop is seamless. The column order keeps duplicate subjects (two
yoga takes, two packed-shop takes) off screen at the same time.

The film plays only while on screen, downloads nothing until then, stays on its
poster for reduced-motion and Save-Data visitors, and has a pause toggle
(WCAG 2.2.2). To change the cut, edit `src-video/film.json`. Each clip takes
`start`, crop centre `x`/`y`, `zoom`, `speed` and a light `grade`.

## Local development

```bash
tools/sync-preview.sh /path/to/scratch/layers-preview   # mirror outside ~/Desktop
python3 /path/to/scratch/layers-preview/tools/devserver.py 8961
```

The dev server serves `public/` with clean URLs and stubs both Functions.
Append `?menu=square`, `?menu=down` or `?menu=fallback` to exercise each menu
path.

## Tests

`python3 -m pytest -q` checks the site's **code**. Every test that needs
content reads the frozen seed in `tests/fixtures/seed/` (today's content, data
and photo specs, plus the seed photos by git blob id) — never `content/` — so
no edit the manager makes can fail a test and hold up her update; the build's
validation is what judges content. A seed photo deleted from the media library
is read back from git history by `tests/conftest.py`. When a developer change
makes a seed assertion wrong, update the fixture deliberately (conftest.py says
how). `tests/test_compat.py` compiles every file with a Python 3.11 if it
finds one (`PYTHON311=…`).

## Publishing

Everything runs in GitHub Actions (setup and day-to-day operations:
**[docs/SETUP.md](docs/SETUP.md)**):

- **`build-deploy.yml`** — on every push to `main` (each CMS save), every
  morning, and "Publish now": `tools/build.py`, the tests, the hosting limits,
  then the same build to **GitHub Pages** (the preview, under `/layers/`; URLs
  prefixed by `tools/ci/prefix.py`) and **Cloudflare Pages** (the live site,
  with the `/api` Functions), via `wrangler pages deploy` — **Direct Upload**.
  The Cloudflare project must be created as Direct Upload, **not** connected
  to the repo with Git integration: it can never be switched afterwards, and
  a Git-connected project would serve the committed `public/` (CMS edits and
  uploaded photos would never appear). A failed build never touches either
  site; it opens a "Website update didn't publish" issue with the
  plain-English report.
- **`menu-refresh.yml`** (daily, "Refresh menu from Square"), **`backup.yml`**
  (weekly releases, "Back up now"), **`restore.yml`**, **`undo.yml`** — the
  CMS's buttons; **`keep-alive.yml`** keeps the schedules from being switched
  off.

`tools/deploy-github-preview.py` (the old hand-run preview push) refuses to
push to a repository that holds the site's source; with the workflows in
place it isn't needed.

The Pages Functions read these bindings (Cloudflare → the project →
*Settings → Variables and Secrets*):

| Name | Required | What it is |
|---|---|---|
| `SQUARE_ACCESS_TOKEN` | for live prices | Square API token. Without it the built menu is served as-is. |
| `CATERING_TO` | yes | Destination inbox for inquiries. **Secret**, never rendered client-side. |
| `CATERING_FROM` | yes | Verified sender address on the email provider. |
| `RESEND_API_KEY` | yes | Transactional email key. |
| `TURNSTILE_SECRET` | recommended | Server-side CAPTCHA. Skipped when unset. |
| `RATE_LIMIT` | optional | KV namespace for per-IP throttling. |
| `MENU_TTL` | optional | Edge cache seconds for the menu. Default 300. |

## Full-resolution photos

This repository is a public demo, so it keeps **web masters** only: page
photos at most 4096 px on the long edge, album photos at most 3200 px —
larger than anything the site serves (2560 px). The camera originals live in
the private repository **meni-gottesman/layers-photos** (same layout:
`originals/`, `albums/<NN-slug>/`). To refresh the masters from it:

```bash
python3 tools/make-web-masters.py --from ../layers-photos [--dry-run]
python3 tools/build.py      # rebuilds only the photos that changed
```

It rewrites a master only when the archive copy is newer, converts to sRGB
and drops metadata (phone photos carry GPS). Photos uploaded through the CMS
land in `src-img/uploads/` at whatever size the manager prepared (≤ 3 MB via
/photo-prep).

## Notes for whoever picks this up next

- **The catering destination inbox is never in client output.** It exists only
  as the `CATERING_TO` binding. The client asked for this explicitly.
- **Facts on the site are sourced.** The copy is the owner's approved text,
  Square's own item descriptions, Layers' own Instagram FAQ, or verified public
  facts (hours, transit, parking). Don't add claims about catering minimums,
  loyalty mechanics or allergens without the owner.
- **Motion degrades to legible, always.** `requestAnimationFrame` is throttled
  to zero in background tabs, on bfcache restore and in low-power mode, so every
  animated element is also recoverable by a `setTimeout` sweep. Do not
  "simplify" these into a single rAF-dependent path.
