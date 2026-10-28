# The CMS configuration (`.pages.yml`)

For developers. The marketing manager edits `content/` through
[Pages CMS](https://pagescms.org) (the hosted app at app.pagescms.org, v2.1.8
as of Oct 2026). Everything the CMS shows — the sidebar, every field, its
label and help text, what it refuses to save, the buttons — comes from
`.pages.yml` at the repo root. The decisions behind it are in
`docs/dev/CMS_SPEC.md` §8 and §11; this page is the working guide.

Three files have to agree, and `tests/test_cms_schema.py` checks that they do:

| File | Its job |
|---|---|
| `tools/content.py` | The site's own schema: what the build reads, its defaults, the validator's rules and **labels** |
| `.pages.yml` | What the manager sees and what the CMS will save |
| `content/**/*.json` | The content, in the exact format a CMS save writes |

## How `.pages.yml` is organised

**`media`** — one source, `photos`: input and output are both `src-img`, so a
chosen photo is stored as `src-img/uploads/x.jpg`, the same repo-relative path
the build reads. Only `jpg`, `jpeg`, `png` and `webp` are listed or accepted
(HEIC isn't an image type in Pages CMS). `rename: safe` turns
`IMG 1234.JPG` into `img-1234.jpg`, which also keeps extensions lower-case —
the CMS compares extensions case-sensitively.

**`settings`** — `content.merge: false`, spelled out: a save rewrites the file
from the schema (merge is buggy upstream and would hide schema gaps). Commit
identity stays at the default (`app`): with `user`, the manager's email would
be written into the public git history.

**`components`** — reusable field definitions. A field that says
`component: x` gets the component's keys, and its own keys win, so a field can
change the label, description or `required`:

| Component | What it is |
|---|---|
| `time-24h` | `HH:MM` as a pattern-checked string (not a datetime field, which would store a date too); spaces around it are allowed, as for links, and trimmed by the build (`content.Time.normalise`) |
| `calendar-date` | a date stored as `yyyy-MM-dd`, `default: ""` (see the traps) |
| `photo-file` | an image field: media `photos`, picker and uploads in `src-img/uploads`, a note on the 3 MB upload limit (every photo's help ends “Over 3 MB? Shrink it first at layerssuperfoodbar.com/photo-prep.” — the whole address, as the CMS shows help as plain text; spots under 1,200 px say “at least 800 pixels wide”) |
| `photo-focus`, `photo-zoom` | the crop keywords from `tools/content.py` (`FOCUS`, `ZOOMS`), default `auto` |
| `alt-text` | “Photo description” (a photo's alt text), 250 characters |
| `web-link`, `site-link` | links: `https://…` only, or also a page on this site (`/menu`, `#faq`) — the validator's `url_ok` rules |
| `formatted-text` | a multi-line box with the `tools/textfmt.py` cheat sheet |
| `page-photo`, `page-photo-no-alt` | a photo spot: photo + alt + focus + zoom, photo and alt required |
| `draft-photo`, `draft-photo-no-alt` | the same with nothing required, for pages that may be unfinished |
| `seo`, `seo-optional-description`, `seo-draft` | the SEO group, “Google and shared links” (“Google title”, “Google description”), with its three levels of `required` |
| `more-sections` | "More sections": a `block` list (blockKey `type`) of the six section kinds — see [Sections and pages of her own](#sections-and-pages-of-her-own) |

**`content`** — the sidebar, in this order. Labels are the validator's
“where” names (`WHERE` / `PAGES` in `tools/content.py`), so an error in the
build report (“Page: Home › Hero → Big word”) uses the words on the CMS
screen:

| Sidebar | Entry | File(s) |
|---|---|---|
| **This week** › Announcement bar | `announcement` | `content/announcement.json` |
| › Specials | `specials` (collection) | `content/specials/*.json` |
| › Events | `events` (collection) | `content/events/*.json` |
| › Opening hours | `hours` | `content/hours.json` |
| **Menu** | `menu` | `content/menu.json` |
| **Pages** › Home … Page not found | `home`, `story`, `how`, `what`, `day`, `catering`, `visit`, `faq`, `links`, `gift-cards`, `loyalty`, `not-found` | `content/pages/*.json`, `content/faq.json`, `content/links.json` |
| › Your own pages | `custom-pages` (collection) | `content/custom-pages/*.json` |
| **Photo albums** | `albums` (collection) | `content/albums/*.json` |
| **Instagram** | `instagram` | `content/instagram.json` |
| **Business details** | `site` | `content/site.json` |

Within a file, what is changed most comes first — see [Form order and
wording](#form-order-and-wording). Field order is also the key order in the
saved file.

**`actions`** — the sidebar buttons. Each dispatches a workflow on `main`
with a `payload` input (CMS_SPEC §8.10: the workflows check the request
themselves, through `tools/ci/payload.py`):

| Button | Workflow | Notes |
|---|---|---|
| Publish now | `build-deploy.yml` | |
| Refresh menu from Square | `menu-refresh.yml` | |
| Back up now | `backup.yml` | |
| Restore a backup | `restore.yml` | one text field, `backup` (→ `payload.inputs.backup`), default `latest`; `cancelable: false` |
| Undo my last change | `undo.yml` | `cancelable: false` |

Action fields can't have a description, so the guidance (where backup names
come from) is in the confirm dialog's `message`.

## Form order and wording

The manager is a café marketing manager with no technical background, and
the owner asked for an editor in which she can change anything simply. So
every screen is written and ordered for her; `tests/test_cms_wording.py`
checks the rules below.

**Order: most-used first, rarely-needed last.**

| Screen | Order |
|---|---|
| Specials, Events, Photo albums, Your own pages | **Published** first (switching it off is how something comes down; a new entry starts on), then the name and what's filled in most — a special: name, photo, photo description, tagline, description, dates, order button; an event: title, date, times, location; an album: title, photos, then cover and Position; a page: title, web address, “Show it in” and “Name in the menu”, then intro, top photo, sections, and Google last |
| Announcement bar | the switch, the message, the dates, the link, the colour |
| Opening hours | **Special hours** (holidays) first, folded to “date name”; then the weekly hours; the note |
| Menu | **Menu items** first (hide, rename, photo — the item's own boxes, then Focus/Zoom, then the read-only Square boxes, `square_id` last), then the words around the menu, sections, Google |
| Pages | the page from top to bottom (photos together in “Photos”), then **More sections**, then what's rarely needed (Home: the film's spoken texts), then **Google and shared links** |
| Link in bio, Instagram | the buttons / the hand-picked posts first (a post's photo help says the grid shows the first ones, and a post past “Number of posts” is a validator error, since “Add an item” puts it last); the switch that takes the page or section down last |
| Business details | address and contact, ordering links, social media, taglines, then Google; Analytics hidden |

Inside a photo spot: Photo, Photo description, then Focus and Zoom (an
album's Cover focus straight after its Cover photo).

**Words.** Labels are everyday words, the same in `tools/content.py` (the
validator's messages) and in the handbook: “Photo description” (not alt
text), “Google and shared links” / “Google title” / “Google description”
(not SEO), “Top photo” (not hero), “Small label above the title” (not
eyebrow), “Web address” (not slug), “First day shown” / “Last day shown” for
a special's or the announcement's dates and “Start time” / “End time” for an
event's, and “… button text” / “… link text” for the words on a button or
link — so a text box is never labelled like the specials' “Order button”
choice. Help text is one short sentence (≤ 170 characters), with an example
where it helps. A box that can be left empty says so first, **“Optional —
…”**, unless its help says when it's needed (a link goes with its link text,
a photo's description with its photo); a required one shows the CMS's own
“Required” badge. Retired labels are listed in the test, so the handbook
can't send her looking for one.

**Hide, never drop.** A key the manager never needs stays declared with
`hidden: true` (Business details › Analytics): a save still writes it, and
its checks still run. (So if a hand edit ever left a malformed token, she
couldn't save Business details until the developer fixed the file — the
build report names it too. Only hide fields the developer sets.) Never
delete a declaration to hide a field: the next save would delete the data.

**When you change a label**, change it in `tools/content.py` too (the
validator's checks take their labels from the schema — `path_of`/`label_of`
in `tools/validate_content.py` — so they follow), and in
`docs/HANDBOOK.md`. **When you reorder fields**, run `python3
tools/cms_normalize.py` on the live content and on the seed in
`tests/fixtures/seed` (it only moves keys), and keep the menu refresh's
new-item order (`tools/sync-menu-from-store.py`) the same as the item's
fields.

## The rules the config follows

- **Every key the build reads is declared**, with the same `name` and `label`
  as in `tools/content.py`. The only exception is a group with no fields
  (`photos: {}` on pages without photos): it's empty, so a save drops it and
  the defaults layer puts it back.
- **Hard limits only.** `required`, `options.maxlength`, patterns, number
  ranges and list min/max stop a save, so they mirror only what the validator
  treats as an **error** (`max`, `required`, `List(min/max)`). Soft limits
  (`warn_max`: “about 60 characters”) go in the description.
- **Drafts can be saved unfinished.** The Gift Cards and Loyalty pages require
  nothing; specials, events and albums require only their name (and an
  event its date), because those make the file name. The validator reports
  their other problems as “not on the site yet” until they're published.
- **Defaults agree.** A field's CMS `default` equals its `tools/content.py`
  default (a switch without one is off; a choice always has one). Every date
  has `default: ""`.
- **Collections** write `{fields.…}.json` file names, don't allow renaming
  (the slug is the web address and the photo-slot name) or subfolders, and
  hide the file-name box. Single files can't be deleted. The CMS slugifies
  the name (`a–z 0–9 -` only), so a name of only emoji or symbols would give
  an empty file name the CMS can't save or the site can't use: the name /
  title fields carry the pattern `[A-Za-z0-9]` (content.py `web_name=True`,
  the same rule and words in the validator).
- **Links tolerate pasted spaces.** Pages CMS doesn't trim what's typed and a
  pasted link often brings a trailing space or line break, so the link
  patterns allow whitespace around the link (`^\s*…\s*$`) and
  `content.Url.normalise` trims it on the way into the build. Spaces inside a
  link are still refused.
- **Multi-line boxes keep their lines.** A `type: text` field is a
  multi-line box; if it isn't formatted text, it is `Text(multiline=True)` in
  content.py when the site shows it on a page, and the template prints it
  with `|br` (line breaks kept). SEO descriptions and the film's description
  stay one line — the validator says a break shows as a space.
- **Validator names match the CMS's list items.** A list item is named by its
  number and the text its `collapsible.summary` shows ("Question 3 (“How
  late are you open?”)"; menu items exactly as the CMS lists them, "Bowls ·
  Mango Coco") — `content.summary_label` / `menu_item_label`. Change a list's
  summary and the item_label together.
- **The menu list is Square's.** Items can be reordered, renamed, hidden —
  not added (the read-only `square_id` can't be filled) or deleted (it comes
  back under Square's name). The field descriptions say so (`square_id`'s,
  where the CMS shows its “required” error after an “Add an item”); the
  validator's warning points at Undo + "Hide from the website". The refresh
  writes a new item's keys in the item's field order, so the file stays in
  the CMS's format.
- **Descriptions** are for a busy café manager: short, concrete, what it does
  on the site and any limit (see [Form order and wording](#form-order-and-wording)).
  Never on a list field (see the traps).

## Adding a field safely

1. **`tools/content.py`** — add it to the file's schema with its label,
   default and rules (`required`, `max` for a hard limit, `warn_max` for a
   soft one). The validator and the defaults layer pick it up from there.
2. **`.pages.yml`** — declare it in the same place, with the same `name` and
   `label`. Pick the type from the table below, copy only error-level limits,
   set `default` if the content.py default isn't empty/false, and write a
   description. Quote anything YAML could read as a time, date or yes/no.
3. **`tools/validate_content.py`** — only if it needs a check that looks at
   more than one field (e.g. “a link needs a label”).
4. **The template** — use it. A missing key is its default, so templates never
   need `is defined`.
5. **Content** — `python3 tools/cms_normalize.py` (it writes the field's
   default into files where a CMS save would), then `python3 tools/build.py`
   and `pytest -q`.

| `tools/content.py` | `.pages.yml` |
|---|---|
| `Text` | `type: string` (one line) or `text` (multi-line; required for `markdown`/`multiline`) |
| `Text(markdown=True)` | `component: formatted-text` |
| `Url(allow=("https",))` / `Url()` | `component: web-link` / `component: site-link` |
| `Bool` | `type: boolean` + `default` |
| `Int(min, max)` | `type: number`, `options: {min, max}`, `default` |
| `Choice(options)` | `type: select`, `options.values: [{name, label}]` in the same order, `default` |
| `Date` | `component: calendar-date` |
| `Time` | `component: time-24h` |
| `Image` | `component: photo-file` |
| `Photo(...)` | `component: page-photo` (or one of its variants) |
| `Obj` | `type: object` + `fields` |
| `List(Obj)` | `type: object` + `list: {min?, max?, collapsible: {collapsed, summary}}` + `fields` |
| `List(Text)` | the item's type + `list: true` (+ `required: true` if the list needs ≥ 1 item) |
| `Blocks` (`SECTIONS`) | `component: more-sections` |

**Renaming or removing a field** works the same way in reverse. The
normaliser refuses to run while a content file still holds a key that isn't
declared, so remove (or move) the data first.

## Sections and pages of her own

**More sections** (`sections` on Home, Story, How, What, Day, Catering, Visit,
FAQ and Menu, and on every page of her own) is a Pages CMS `block` list,
declared once as the component `more-sections`. "Add an item" shows a
button per kind; the chosen kind is saved under `type` (`blockKey`), first,
then that kind's fields in order:

```json
"sections": [
  {"type": "text", "heading": "A year on Channing Way", "text": "…"},
  {"type": "photo", "image": "src-img/uploads/x.jpg", "alt": "…", "focus": "auto", "zoom": "auto", "size": "wide"}
]
```

The six kinds (`text`, `photo`, `photo-text`, `photos`, `button`, `quote`)
are `content.SECTION_BLOCKS`, drawn by `templates/partials/sections.html` from
the site's own editorial pieces. Their photos are photo slots named by
`content.section_photos` — `blocks/<page>_<n>` (`_<k>` for each photo of a
row), `custom/<address>_<n>` and `custom/<address>_top` — cut at 21:9 (wide),
3:2 (standard), 4:5 (photo and text) or 1:1 (row), with the usual size and
description checks. Validation names them as the CMS shows them: "Page: Home ›
More sections → Section 2 (Photo and text) → Photo" (the list's summary is
`Section {index}`, and the kind is the badge on each item). They are drawn
after the page's own content — on Home before the Visit band, and on Story,
How and What before the closing words and buttons (`.story-close`;
`sections.render(…, before_close=True)`), so nothing she adds reads as an
afterthought below the ending. A Text section with nothing in it (picked by
mistake: it has no required box, so the CMS saves it) isn't drawn, and the
validator only notes it (`content.text_section_has_words`).

**To add a kind of section:** add it to `SECTION_BLOCKS` (and to
`SECTION_PHOTOS` if it has photos), to the component's `blocks` in
`.pages.yml` with the same name, label and fields, and to `sections.html`;
`tests/test_cms_schema.py` checks both sides declare the same kinds and
fields.

**Your own pages** (`custom-pages`) are whole pages at `/<address>`. The
file name is `{fields.address}.json`, made once when the page is first saved
(`rename: false`), and **the page is always at its file's address**. Two
ways the "Web address" box can stop matching it, both warnings (an error
would hold up every other change) that say where the page really is:

- the box was changed after the first Save;
- the address was already another page's — even a switched-off one. Pages
  CMS doesn't refuse a new file whose name exists: its files API (v2.1.8,
  `app/api/[owner]/[repo]/[branch]/files/[path]/route.ts`) saves it as
  `<name>-1.json` unless the client sends `onConflict: "error"`, and the
  entry form never does. The validator recognises `<address>-<n>.json`
  next to `<address>.json` and says which page has the address (the help
  under "Web address" asks for one her other pages don't use).

The address pattern refuses every path the site uses itself
(`content.RESERVED_ADDRESSES`: every `PAGE_CONFIG` output, plus hosting
paths such as `api`, `assets` and `cdn-cgi`; the pattern is
`content.address_pattern()`, and a test keeps the two equal). `render.Site`
adds each page to the site as `custom/<address>` (template `custom.html`;
a top photo is also its picture when the page is shared, `og:image`).
"Show it in" puts it in the footer, in the main menu as well, or nowhere.
A published page is in the sitemap; a deleted one's folder is removed by
`write_pages`, which recognises the folders it made by their `page-custom`
body class.

**The main menu never crowds or disappears.** Her pages go in it in A–Z
order of their titles while they fit (`content.custom_page_links`): at most
`MAX_MENU_PAGES` = 2, a name of at most `MENU_NAME_MAX` = 18 characters
("Name in the menu", `menu_title`, `options.maxlength: 18`; empty = the
title), and together no wider than the row's room at the site's widest
column (`NAV_ROOM_PX`). Any other page set to the main menu is in the footer
only, with a warning saying why ("full", "long" or "wide"). Widths are
estimated from the characters (`NAV_CHAR_PX`, measured in Chrome in the
menu's type — uppercase Archivo semi-condensed, 13 px, .08em — Oct 2026, +3%;
tests pin real names within 5%). `render.header_more` then picks where the
phone menu takes over: the site's own 1100 px when the names fit there (one
short name changes nothing), else the smallest of `HEADER_WIDTHS` (1140,
1180, 1220, 1260 → `.header--more-<width>` in styles.css) that leaves 32 px
to spare beside the wordmark with a 17 px scrollbar. Checked in Chrome at
every cut-over: one line, inside the screen, ≥ 49 px to spare at the first
width the menu shows. **If the menu's type, its links or the Order button
change, measure again** (`NAV_CHAR_PX`, `NAV_BASE_PX` = the site's five links
+ the Order button, 20 px apart).

**Links to the site's own pages** in her content (link fields that allow a
site path — section buttons, the announcement, /links buttons, events — and
`[words](/a-page)` in formatted text) are collected while each file is
checked (`content.note_link`) and checked once every file is read
(`validate_content.check_links`): a page that doesn't exist is an error
(with a suggestion: lowercase, without the preview's `/layers`, or the
closest page — "Did you mean /run-club?"); a page that exists but is
switched off (hers, Gift Cards, Loyalty, /links) is a warning, and the
pages don't draw that link until it's switched on (`render.Site.link_live`,
used by `link_ok`, the templates and the text format). The build's own
check of developer links (`build.check_output`) is unchanged.

## The Edit buttons (staff mode)

`render.REPO` and `render.BRANCH` are the only place the repository is
written: `EDITOR_URL` (`https://app.pagescms.org/meni-gottesman/layers/main`)
and `HANDBOOK_URL` (the guide, linked from /edit) are made from them.
`render.editor_link(key)` turns a content key into the app's own routes
(Pages CMS v2.1.8, `app/(main)/[owner]/[repo]/[branch]/`): `/file/<name>`,
`/collection/<name>`, `/collection/<name>/edit/<path>`,
`/collection/<name>/new`. `<name>` is the entry's `name` here (groups don't
change it; `CMS_FILES` and `CMS_COLLECTIONS` map content keys to names) and
`<path>` is the repo path, encoded like the app's `encodeURIComponent` —
except the extension's dot, written `%2E`
(`content%2Fspecials%2Fphi-velvet%2Ejson`). The app's proxy (`src/proxy.ts`)
treats any address ending in `.<letters>` as a static file and then skips
the `x-return-to` header its sign-in redirect uses, so a signed-out manager
pressing Edit on a special landed on the Projects page instead. Checked with
a minimal Next.js 16.2.1 app (the version the app uses) running that proxy,
the repo layout's sign-in redirect and the entry page: the `.json` link
redirects to plain `/sign-in`; the `%2Ejson` link to
`/sign-in?redirect=…`, `/auth/redirect` returns to it, and the page's
`path` param arrives as `content%2Fspecials%2Fphi-velvet.json` (decoded to
`content/specials/phi-velvet.json`), signed in or not. (If a proxy in front
of the hosted app ever decoded `%2E`, the link would behave as before.)
`tests/test_edit_mode.py` checks that every link on every page resolves to
an entry of this file and an existing content file, and
`tests/test_edit_safety.py` that none ends in an extension. **If an entry
is renamed here, update `CMS_FILES` / `CMS_COLLECTIONS`.**

Templates mark editable regions with `edit_attr(url, label)` (`data-edit`,
`data-edit-label`); `<body>` carries `data-edit-root` and `data-edit-page`.
An Edit link opens a screen, not a box on it (the app can't link deeper),
so a chip's label says where to look when the box isn't near the top (the
menu page's title and notes come after the menu items; on Home, Story, What
and Catering, "(in the editor: Photos › Top photo, then Top of the page)"
and the like).
`main.js` turns staff mode on with `?edit` (remembered in localStorage as
`layers-edit`) and off with `?edit=off`; only then does it add the "✎ Edit"
links and the bar (inserted right after the skip link, so it's early in the
Tab order though it's fixed at the bottom of the screen). In the footer the
text keeps room for the pencil (`.is-editing … padding-right`), so the pencil
never covers the address or the hours. Visitors' pages differ from before
only by those attributes. `/edit` is the staff start page
(`templates/pages/edit.html`), a phone-first quick-update launcher: "What
would you like to change?", a publish-status line, big tiles (one tap each to
the right editor screen, `render.editor_link`; `media:photos` opens the photo
library), then the button that turns the Edit buttons on, the three steps, how
to undo (Actions → Undo my last change, in the editor's sidebar: the app's
/actions page is closed to email collaborators), and **Worth a look** — this
build's warnings (`render.Site.notes`, set by `tools/build.py` after the
content check), each with a link to its screen. It is also a home-screen app:
`public/edit/manifest.webmanifest` (relative paths, so the GitHub Pages
`/layers/` prefix keeps working; the colours are the site's `--ground` and
`--warm-white` tokens, `tests/test_edit_mode.py` checks them).

**The publish status** ("Is my change live?", `publishStatus` in `main.js`)
asks GitHub's public API, from the browser, for the newest run of a publishing
workflow (build-deploy, menu-refresh, undo, restore: the last three call the
first, so their runs are listed under their own names) on the branch, and, only
when it failed, for the open "Website update didn't publish" issue the Actions
bot keeps. The repository and branch are `render.REPO` / `BRANCH` (the card's
`data-repo`; the bar reads them from `data-edit-root`). It runs only on `/edit`
and, in staff mode, in the bar: visitors never call the API. One request every
20 s while a publish runs, for 10 minutes; unauthenticated limits are 60 an
hour per address, and an unchanged answer (304) isn't counted.

**The homepage layout** (`content/pages/home.json` → `layout.sections`, "Page
layout" right after "Top of the page"): an ordered list of section names
(`content.HOME_SECTIONS`: fresh, film, products, specials, community,
instagram, more). `templates/pages/home.html` loops over
`content.home_layout(page)`: unknown names are ignored, a repeat keeps its
first place (the validator warns), nothing usable left means the default order,
and the top photo and Visit stay first and last. The list is wrapped in an
object because Pages CMS repeats a list's own description under every item;
the object's description is shown once. It is not `required`: a file without
it (a restored backup) must stay saveable. The default order renders the same
bytes as the page before the layout existed.

## `tools/cms_normalize.py`

A port of what Pages CMS does when the manager opens a file and presses Save,
driven by `.pages.yml`:

```bash
python3 tools/cms_normalize.py            # rewrite every CMS-managed file
python3 tools/cms_normalize.py --check    # report files not in the CMS's format
python3 tools/cms_normalize.py content/hours.json
```

It refuses (exit 1, lists every problem, writes nothing) when a save would
lose or refuse something: an undeclared key with a value, a value of the
wrong shape, a date in another format, or a value the CMS's own checks
reject. Run it after changing `.pages.yml` or editing content by hand, so a
CMS edit's diff (and “Undo my last change”) is only ever the manager's
change. `tests/test_cms_schema.py` checks the frozen seed content
(tests/fixtures/seed) — the tests never read the live `content/`, which the
manager owns — and CI runs `--check` on the live files as a developer-only
step that never stops a publish.

It was verified on Oct 27 2026 against Pages CMS v2.1.8's own code
(`lib/schema.ts`, `lib/config.ts`, `lib/serialization.ts`, `fields/core/*`,
run under Node with the React components stubbed): byte-identical output for
every content file, and agreement on ~15,000 fuzzed variants (missing keys,
nulls, wrong types, odd dates and paths, undeclared keys). Block lists (the
"More sections") were added on Oct 27 2026 and checked the same way: every
content file — with a section of every kind and two pages of her own — saved
byte-identically by the app's code and by the normaliser, and 13 replayed
edits (adding each kind, a section without its photo, a row of one photo, an
unknown kind, an item added without choosing its kind, a new page with a
reserved or badly written address) saved or refused identically. Only the
field types this site uses are ported; it refuses a config that uses others. **If
Pages CMS is upgraded**, re-check the traps below against the new source
(`sanitizeObject`, `initializeState`, the date/image/select field modules and
the files API route) before trusting the normaliser.

## Pages CMS traps (v2.1.8, from its source)

**Saving**
- A save rewrites the whole file from `.pages.yml`: undeclared keys are
  deleted (zod strips them; `merge` is off).
- Empty values are dropped: `""` and `null` anywhere, and a list or object
  left empty. `false` and `0` are kept. An empty object *inside* a list is kept.
- Output is `JSON.stringify(data, null, 2)`: 2-space indent, **no final
  newline**, keys in field order (integer-like keys first, as in any JS object).
- Opening a file fills every missing field with a default, and the next save
  writes it: a switch becomes `false`, a field with `default:` gets it.
  **A date field without `default: ""` gets today's date.**
- A date that doesn't match `options.format` opens as empty and is blanked by
  the next save — silently. Keep every stored date `yyyy-MM-dd`.
- Booleans are coerced with JavaScript truthiness: the string `"false"` is
  `true`. Store real booleans.

**Checks**
- An optional field with a `pattern` rejects an empty value unless the
  pattern allows it: write `^$|…`. Patterns run as JavaScript regexes — use
  `[0-9]`, not `\d` (Python's `\d` matches other digits too).
- `maxlength` counts UTF-16 units: an emoji counts as 2.
- `required` on a list means “at least one item” (and, for a list of texts,
  each item non-empty).
- A select stores the option's `name`; anything else in the file blocks the
  save with “Invalid option”. There's no free text.
- Image paths must end in an image extension, compared case-sensitively
  (`.JPG` is refused, `.heic` isn't an image type).
- `readonly` and `hidden` fields are still saved.

**Lists and layout**
- The object form of `list` (`{min, max, collapsible}`) must include
  `collapsible` (the config validator requires it). Never use it on a content
  *entry* — a file that is a top-level list shows one blank item instead of
  the data (#399). Field lists are fine at any depth.
- A list field's `description` is never shown, and a list item's field
  descriptions repeat under every item — keep those short.

**Collections**
- A JSON collection needs a `filename` ending in `.json`; the default ends in
  `.md` and every entry vanishes (#413). `{fields.x}` values are slugified.

**Blocks** (`type: block`, the "More sections")
- A block definition may only have `name`, `label`, `description`,
  `component`, `default` and `fields` (the config validator is strict): no
  `type`, `required` or `list` on a block itself.
- An item is `{<blockKey>: <kind>, …fields}`; a save writes the key first,
  then the kind's fields in order, and drops undeclared keys inside it.
- "Add an item" adds an empty item (null) until a kind is chosen; a save
  drops it. An item of a kind the field doesn't have can't be saved
  ("Invalid discriminator value").
- The list's `collapsible.summary` is interpolated with the item's fields
  (missing ones become empty), so it is just `Section {index}`; the kind's
  label is shown as a badge.
- Each block field's description repeats under every section: keep them short.

**Media**
- Uploads over ~3.3 MB fail (413, the host's request limit): the descriptions
  point to the site's Prepare a photo page (`layerssuperfoodbar.com/photo-prep`,
  written out in full: help is plain text, never a link), which shrinks a
  photo in the browser. Until the domain moves, the handbook's “Your links”
  note covers the github.io address; after the move nothing changes.
- The image picker opens in the field's `options.path` (`src-img/uploads`) and
  uploads land there. A collaborator can delete or rename anything in
  `src-img/` from the media screen; undo/restore cover `src-img/`.

**Actions**
- The app doesn't check a dispatch against `.pages.yml`: any CMS user can start
  any workflow that has a `payload` input, on any branch, with any values
  (CMS_SPEC §8.10). Only the five workflows above take `payload`, and each
  checks the branch and allow-lists its inputs.
- Action fields arrive as `payload.inputs.<name>`; they have no description.

**YAML**
- Pages CMS reads `.pages.yml` as YAML 1.2; PyYAML (the tests, the
  normaliser) reads 1.1. Plain `09:00`, `yes`/`no`/`on`/`off` and dates mean
  different things in the two: quote them (a test checks). In the workflow
  files, PyYAML reads the key `on:` as `true`.
- Duplicate keys aren't an error in the CMS (the last one wins): a test
  checks there are none.

**Everything else**
- No preview and no undo inside the app; History shows the last 3 commits.
  The safety net is validation (a failed build never touches the live site),
  “Undo my last change” and the backups.
- Collaborators can switch branches; the workflows only act on `main`.

## Checking a config change against the real app

`tests/test_cms_schema.py` covers what the site needs. Before a bigger change
(new field types, a Pages CMS upgrade) it's worth running the app's own
config validator: copy `lib/config-schema.ts` from the Pages CMS source (pin
the version the hosted app reports at app.pagescms.org/api/app/version),
replace its `fieldTypes` import with the list of core field types, and run
`ConfigSchema.safeParse(YAML.parse(…))` under Node with `zod` and `yaml`.
Unrecognised keys come back as issues too, so “valid” means no warnings
either. The same copy, plus `lib/schema.ts`, `lib/config.ts`,
`lib/serialization.ts` and `fields/core/*` (React components stubbed), can
replay a save of every content file to compare with `tools/cms_normalize.py`.
