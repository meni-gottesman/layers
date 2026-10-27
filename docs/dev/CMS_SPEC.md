# Layers site — editable content, safe publishing, backups (build spec)

Status: implementation spec, Oct 27 2026. Audience: the developers doing the
work. The end user is a **non-technical marketing / social media manager**
at a Berkeley café. Every decision below favours "they can't break it" over
flexibility.

## 0. Ground rules (apply to every task)

- **Never** add tool or vendor credits anywhere: code comments, commit
  messages, docs, page footers, handbook. The footer credit stays "Site by Meni
  Gottesman’s Web Services".
- **Never** commit secrets. The catering destination inbox exists only as the
  server-side `CATERING_TO` binding and must never appear in any client output,
  content file or doc example.
- **Don't invent facts.** Copy on the site is the owner's approved text, Square's
  item text, or sourced public facts. Seed content = what the site says today.
- **Design is final.** The current HTML/CSS output was reviewed in detail. The
  refactor must reproduce it (see §7 acceptance), and new features must use the
  existing design system (Archivo, limewash `#E5E0D8` ground, green `#3A4A2C`,
  square corners, tokens at the top of `public/assets/css/styles.css`).
- Python ≥ 3.11 compatible (CI runs 3.12; local is 3.14). Dependencies live in
  `requirements.txt` (Pillow, numpy, opencv-python-headless, pillow-heif, jinja2,
  segno). No Node build step.
- All user-entered text is **escaped**. Long-form text supports a tiny, safe
  markdown subset only (§3.3). No raw HTML from content, ever.
- Image paths in content are repo-relative POSIX paths under `src-img/`
  (e.g. `src-img/uploads/new-bowl.jpg`). The build must also accept the same
  path with a leading `/` (the CMS may write `/src-img/...`).

## 1. Architecture

```
content/                ← the ONLY thing the manager edits (via Pages CMS)
  site.json               business details, ordering + social links, SEO defaults, analytics
  hours.json              weekly hours + special/holiday hours
  announcement.json       the thin bar at the top of every page
  instagram.json          the Instagram section
  links.json              the /links "link in bio" page
  menu.json               how Square items are shown (names, notes, photos, order, hide)
  faq.json                questions and answers
  pages/<page>.json       copy + photos for each page (home, story, how, what, day,
                          catering, visit, gift-cards, loyalty, 404)
  specials/<slug>.json    limited-time drinks/bowls (collection)
  events/<slug>.json      run clubs, collabs, pop-ups (collection)
  albums/<slug>.json      photo albums (collection)
src-img/
  originals/              placed photos (web masters)
  albums/<NN-slug>/       existing album photos (referenced from content/albums/*.json)
  uploads/                everything uploaded through the CMS lands here
  slot-specs.json         TECHNICAL per-slot crop specs (not editable; see §4)
templates/              Jinja2 templates (base layout, partials, one per page)
tools/build.py          single entry point: validate → menu (offline) → images → albums
                        → instagram → pages → extras (QR, links) → output check
tools/validate_content.py   friendly validation (also importable)
data/menu-fallback.json     written by tools/sync-menu-from-store.py (Square)
public/                 build output + hand-written static assets (css/js/vendor/video/icons)
.pages.yml              Pages CMS configuration
.github/workflows/      build+deploy, menu refresh, backups, restore, undo
docs/HANDBOOK.md        the manager's guide;   docs/SETUP.md  the owner/dev setup guide
```

Flow: manager saves in Pages CMS → commit to `main` → GitHub Actions runs
`python3 tools/build.py` → **only if it passes**, the site is deployed. A failed
build never touches the live site; the failure is reported in plain English
(§6). A daily scheduled build keeps date-based content (announcements, specials,
events, holiday hours, Instagram) current.

## 2. Content schema (exact shapes; seed values = today's site)

Conventions: dates are `YYYY-MM-DD`; times are 24h `HH:MM`; every optional
string may be `""`; every image field is a path string (`""` = none);
`published`/`enabled` booleans default as noted. Unknown keys are ignored by the
build (never an error) so the CMS can't break the build by adding metadata.

### 2.1 `content/site.json`
```json
{
  "business": {
    "name": "Layers Superfood Bar",
    "street": "2436 Channing Way", "city": "Berkeley", "region": "CA", "postal_code": "94704",
    "cross_streets": "Between Telegraph Ave and Dana St",
    "phone": "", "public_email": ""
  },
  "ordering": {
    "square_url": "https://layerssuperfoodbar.square.site",
    "doordash_url": "", "ubereats_url": ""
  },
  "social": {
    "instagram_handle": "layerssuperfoodbar",
    "tiktok_url": "", "facebook_url": "", "yelp_url": "", "google_url": ""
  },
  "seo": {
    "default_description": "Layers Superfood Bar — real food, functional fuel. Smoothies and bowls made fresh at 2436 Channing Way, Berkeley.",
    "share_image": ""
  },
  "footer_tagline": "A Berkeley superfood bar. Clean smoothies and bowls, made fresh.",
  "signoff_tagline": "Always pure, never watered down.",
  "analytics": { "cloudflare_web_analytics_token": "" }
}
```
`public_email` is a PUBLIC contact address only (shown in the footer if set) —
never the catering inbox. Social links render in the footer "Follow" column only
when set. `share_image` empty → the homepage hero.

### 2.2 `content/hours.json`
```json
{
  "weekly": {
    "monday":    {"closed": false, "open": "09:00", "close": "18:00"},
    "tuesday":   {"closed": false, "open": "09:00", "close": "18:00"},
    "wednesday": {"closed": false, "open": "09:00", "close": "18:00"},
    "thursday":  {"closed": false, "open": "09:00", "close": "18:00"},
    "friday":    {"closed": false, "open": "09:00", "close": "18:00"},
    "saturday":  {"closed": false, "open": "09:00", "close": "16:00"},
    "sunday":    {"closed": false, "open": "09:00", "close": "16:00"}
  },
  "special": [
    {"date": "2026-11-26", "label": "Thanksgiving", "closed": true, "open": "", "close": ""}
  ],
  "note": ""
}
```
Seed `special` as an EMPTY list (don't invent holidays). Rendering: everything
`HOURS` drives today (footer, Visit table, homepage line, JSON-LD, the
`layers-hours` meta for "Open now") now comes from here. Special hours: the Visit
page lists upcoming special days (next 60 days) under the weekly table; JSON-LD
gets `specialOpeningHoursSpecification`; the open-now script honours a special
day for today (extend the meta payload with a `special` map keyed by date).

### 2.3 `content/announcement.json`
```json
{"enabled": false, "message": "", "link_label": "", "link_url": "", "starts": "", "ends": "", "tone": "green"}
```
`message` ≤ 110 chars. `tone`: `green` | `butter`. Shows as a thin bar above the
header on every page while enabled and today ∈ [starts, ends] (empty = open-ended),
dismissible (remembered per message in localStorage, wrapped in try/catch). Dates
are checked at build time AND in JS at runtime (so it disappears on its end date
even before the next build).

### 2.4 `content/specials/<slug>.json` (collection)
```json
{
  "name": "Phi Velvet", "partner": "Cal Alpha Phi", "badge": "Limited time",
  "tagline": "Strong. Radiant. Nourished.",
  "description": "",
  "highlights": ["Beauty-Boosting Antioxidants", "21g Plant Protein", "Empowered Wellness"],
  "ingredients": "Strawberry, Raspberry, Banana, Cacao nibs, Cacao powder, Plant-based protein, Almond milk, Lactose-free Greek yogurt",
  "price": "", "image": "src-img/originals/special-phi-velvet-cup.jpg",
  "image_alt": "The Phi Velvet: a strawberry-raspberry smoothie swirled with Greek yogurt and topped with cacao nibs, in a Layers cup",
  "starts": "", "ends": "", "order_url": "",
  "show_on_home": true, "show_on_menu": true, "published": true
}
```
Phi Velvet is real (client's Drive "Layers / Menu" folder, Oct 19 2026 poster:
"Cal Alpha Phi × Layers … Available for a limited time"). It is not on Square,
so no price and no order link unless provided; the CTA falls back to the Square
store. Rendering: homepage band ("Limited time") after the products section, and
a card at the top of /menu. Several active specials → a row of cards. None → the
band is absent (no placeholder).

### 2.5 `content/events/<slug>.json` (collection)
```json
{"title": "", "date": "2026-11-08", "start_time": "09:00", "end_time": "", "partner": "",
 "location": "Layers, 2436 Channing Way", "description": "", "image": "", "image_alt": "",
 "link_url": "", "link_label": "", "published": true}
```
Seed with NO events (don't invent). Rendering: when upcoming published events
exist, a compact "Coming up" list appears in the homepage community section
(above "See every album") and on /links; past events disappear automatically.

### 2.6 `content/instagram.json`
```json
{"enabled": true, "heading": "Follow along", "mode": "curated", "behold_feed_url": "", "count": 4,
 "curated": [{"image": "src-img/...", "post_url": "https://www.instagram.com/p/<code>/", "alt": "..."}]}
```
`mode`: `auto` (Behold JSON feed fetched AT BUILD TIME; images downloaded and
processed like every other photo; no third-party requests from visitors) or
`curated` (hand-picked posts). Auto falls back to curated if the feed is empty or
unreachable; if neither yields posts, render only the "Follow @handle" call to
action, no empty grid. Section sits on the homepage before the Visit band.
Seed `curated` with these posts (images already in the repo, none of them used
on the homepage):
- `src-img/albums/04-the-regulars/04.jpg` → https://www.instagram.com/p/DeFwOJmj8zc/ ("the regulars lately")
- `src-img/albums/03-community/12.jpg` → https://www.instagram.com/p/Dd4xpEAktac/ (Layers × Tri Delta)
- `src-img/albums/02-run-clubs/14.jpg` → https://www.instagram.com/p/DeKbt0joBZx/ (She Runs Berkeley)
- `src-img/albums/02-run-clubs/16.jpg` → https://www.instagram.com/p/DeIBhzaIEcx/ (INSYNC)
Reuse the album alt texts.

### 2.7 `content/links.json`
```json
{"enabled": true, "heading": "Layers Superfood Bar", "intro": "",
 "buttons": [{"label": "Order on Square", "url": "https://layerssuperfoodbar.square.site", "highlight": true},
             {"label": "See the menu", "url": "/menu", "highlight": false},
             {"label": "Catering", "url": "/catering", "highlight": false},
             {"label": "Visit us", "url": "/visit", "highlight": false}],
 "show_specials": true, "show_events": true}
```
`/links` page: the link-in-bio page for Instagram. Minimal, mobile-first, uses
the site chrome lightly (wordmark + buttons). `noindex`. Excluded from nav and sitemap.

### 2.8 `content/menu.json`
How Square items are presented. Square remains the source of truth for names,
prices, ingredients and allergens (`data/menu-fallback.json`).
```json
{"intro": "",
 "items": [{"square_id": "WCXFIIWG7UHLHK4YSLDSIWNZ", "square_name": "Berry Much Love U (Classic Acai)",
            "display_name": "", "note": "Classic Açaí", "photo": "", "focus": "auto", "zoom": "auto", "hidden": false}]}
```
Migrate everything in `tools/menu-overrides.json` (rank → list order within its
category, name → display_name, note, image → photo, focal/zoom/edit → keep as
technical tuning in `src-img/slot-specs.json` under the item's slot). Include
EVERY Square item (all categories) so the manager can hide/rename anything.
`square_id`/`square_name` are read-only in the CMS. Items Square adds later are
appended by the menu refresh; ids that disappear from Square are ignored with a
warning. `tools/menu-overrides.json` is retired after migration (sync reads
content/menu.json instead).

### 2.9 `content/faq.json`
`{"items": [{"question": "...", "answer": "..."}]}` — migrate the 8 current Q&As
verbatim (answers use the markdown subset; internal links like `[menu](/menu)`).

### 2.10 `content/albums/<slug>.json` (collection)
```json
{"title": "Behind the counter", "order": 1, "published": true,
 "cover": "src-img/albums/01-behind-the-counter/06.jpg", "cover_focus": "auto",
 "photos": [{"image": "src-img/albums/01-behind-the-counter/01.jpg", "alt": "..."}]}
```
Migrate from `src-img/albums/*/album.json` (keep current order, covers,
cover_focal as technical tuning). `tools/build-albums.py` reads content/albums.
New uploads may live anywhere under `src-img/`.

### 2.11 `content/pages/<page>.json`
One file per page: `home, story, how, what, day, catering, visit, gift-cards,
loyalty, 404`. Every page has:
```json
{"seo": {"title": "...", "description": "..."}, "photos": {"<name>": {"image": "...", "alt": "...", "focus": "auto", "zoom": "auto"}}, ...copy fields}
```
Copy fields are page-specific; extract EVERY human-readable string currently in
`src-pages/*.html` (headings, statements, paragraphs, captions, button labels
that are content rather than UI chrome, the film's text description). Structural
repetition becomes lists (e.g. story chapters: `[{title, lead, body, closing_line}]`;
community photo story: a fixed `wide` item + exactly four `squares`, each
`{photo, caption}`). `gift-cards` and `loyalty` carry `"published": false` (today's
drafts). Decided Oct 27 2026: screen-reader landmark names on sections
("Bowls and smoothies", "Photo albums" …) and UI-chrome labels ("Order on
Square", "Follow @handle", "Coming up") are developer copy and stay in the
templates; the film's accessible name and description are content
(`pages/home.json` `film.label`, `film.description`). Photo keys map 1:1 to today's slots: `home/hero` → `pages/home.json`
`photos.hero`; `home/hero-m` → `photos.hero_mobile`; `home/fresh-1` → `photos.fresh_1`, etc.

## 3. Rendering

### 3.1 Templates
Jinja2 (`autoescape=True`, `StrictUndefined`). `templates/base.html` holds the
chrome now in `build-pages.py` (head, header, drawer, sign-off, footer) driven
by `content/site.json` + `hours.json`. One template per page; page META that is
technical (header mode, nav key, body class, preloads, jsonld flag) moves into
the template or a small `PAGE_CONFIG` in the builder — NOT into editable content.
`{{pic ...}}` becomes a Jinja macro/global `pic(slot, sizes=..., eager=False, mobile=None, ...)`
whose alt text comes from the page content (`photos.<name>.alt`).

### 3.2 Menu, albums, hours
Same output markup as today; data sources change as in §2. The menu card JSON
(`data-item`) and `/api/menu` live-merge behaviour are unchanged.

### 3.3 Safe markdown subset (`tools/textfmt.py`)
Input is escaped first, then: blank line → paragraph; single newline → `<br>`;
`**bold**` → `<strong>`; `*italic*`/`_italic_` → `<em>`; `[text](url)` → link
where url is `https://`, `mailto:`, `tel:` or a site path starting with `/` or
`#` (anything else → plain text). External links get `target="_blank" rel="noopener"`
plus the sr-only "(opens in a new tab)" hint. Nothing else (no headings, images,
HTML). Unit-tested, including hostile input (`<script>`, `javascript:` URLs,
unbalanced markers).

## 4. Photos: editable vs technical

`src-img/slot-specs.json` (technical, not in the CMS): per slot `aspect`,
`widths` set, optional `max_width`, and `tuned`: `{image, focal, zoom, edit}` —
today's carefully tuned crop/retouch for today's photo.
Build rule per slot: if the content's image equals `tuned.image` and
focus/zoom are `auto` → use the tuned focal/zoom/edit exactly (output identical to
today). Otherwise → `focus` (`auto`=center, `top`, `bottom`, `left`, `right`,
`top-left`, `top-right`, `bottom-left`, `bottom-right`) and `zoom` (`auto`/`none`
= 1.0, `a-little` = 1.15, `more` = 1.35) with the gentle default retouch
`{"wb": 0.4, "levels": 0.4, "highlights": 0.15, "denoise": 1}`.
Uploads: accept JPEG/PNG/WebP/HEIC; strip metadata (GPS) in outputs; reject
images under 1200 px on the long edge for full-width slots and under 800 px for
others (friendly error: which photo, how big it is, how big it must be).
The image build is **incremental**: each slot/album records a fingerprint of
(source bytes hash, spec, edit, code version) and is skipped when unchanged;
stale outputs for a slot are removed when its widths change.

## 5. Validation (`tools/validate_content.py`)

Runs first in `tools/build.py`; also `python3 tools/validate_content.py` alone.
Produces a list of problems, each `{level: error|warning, where, field, message}`
with `where`/`field` using the SAME labels the CMS shows (e.g. where="Opening
hours", field="Saturday → Opens"). Messages are plain English and say how to fix
it ("Saturday's opening time is after its closing time. Check the times."). Errors
block publishing; warnings don't. Writes `build-report.json` and a human
`build-report.md`. Checks at least: required fields, max lengths (announcement
110, SEO title 60 → warning, description 160 → warning, captions 80, alt
required for every placed photo), URL format (https or site path), dates/times
parse, close > open, end ≥ start, image files exist + minimum size, Instagram
post URLs look like Instagram post/reel links, Behold URL format, analytics token
is 32 hex chars, duplicate slugs, special/event dates, menu `square_id`s known.

## 6. Publishing, safety net, backups (GitHub Actions)

- `build-deploy.yml` — reusable (`workflow_call`) + `push` to main +
  `schedule` daily ~06:00 Pacific + `workflow_dispatch`. Steps: checkout, setup
  Python 3.12 with pip cache (exact versions from `requirements.lock`), restore
  the image cache and the last Instagram feed, `python3 tools/build.py` (the
  scheduled run adds `--refresh-instagram`), `python -m pytest -q`, then deploy.
  The tests check the code against frozen seed content (`tests/fixtures/seed`),
  never the live `content/`, so a manager's edit can't fail them:
  - GitHub Pages (this repo's Pages, base path `/layers`, reusing the URL-prefix
    logic from `tools/deploy-github-preview.py`, refactored into an importable
    function) — the client preview.
  - Cloudflare Pages via wrangler **only if** `CLOUDFLARE_API_TOKEN` and
    `CLOUDFLARE_ACCOUNT_ID` secrets exist (production, root path, with
    `functions/`). Skipped silently otherwise.
  - On failure: open (or update) a single GitHub issue titled
    "Website update didn't publish" whose body is `build-report.md`; close it on
    the next success.
- `menu-refresh.yml` — daily + dispatch: run the Square sync; if menu data or
  `content/menu.json` changed, commit them, then call `build-deploy.yml`
  (commits made with GITHUB_TOKEN do not trigger `push` workflows).
- `backup.yml` — weekly (Sunday) + dispatch: zip `content/`, `src-img/`
  (excluding library), `data/`, `templates/`, and the built `public/` into a GitHub
  Release `backup-YYYY-MM-DD-HHMM`; keep the newest 12 weekly backups and,
  counted separately, the newest 6 made with "Back up now" (the release title
  says which), so button presses never push out the weekly history.
- `restore.yml` — dispatch with a backup name (or "latest"): restores `content/`,
  the photos in `src-img/` and `data/` from that release, commits "Restore from
  backup …", calls `build-deploy.yml`. Never touches templates/tools, nor the
  developer files in `src-img/` (slot-specs, existing-photos, PROVENANCE, the
  photo manifests — keeping today's manifests makes every restored photo
  rebuild).
- `undo.yml` — dispatch: reverts the most recent commit that changed `content/`
  or the photos in `src-img/` (any image under it, uploads or not) — never
  code, and never `src-img/`'s specs or manifests, which count as code — then
  calls `build-deploy.yml`.
- Pages CMS **actions** (buttons in the CMS sidebar) dispatch: "Publish now",
  "Refresh menu from Square", "Back up now", "Restore a backup" (field: backup
  name, default "latest"), "Undo my last change". Workflows dispatched from Pages
  CMS receive a `payload` input (JSON string) — accept it, and also plain inputs
  for manual runs.
- Keep-alive: GitHub disables scheduled workflows in public repos after 60 days
  without activity. `keep-alive.yml` runs WEEKLY: it re-enables any workflow
  GitHub switched off for inactivity (never one switched off by hand) and,
  after 45 quiet days, pushes an empty heartbeat commit — weekly, so the
  heartbeat lands by day 52 at the latest (a monthly run could miss day 60).
- Logs of a public repo are public: no workflow prints the Pages CMS payload
  (it holds the manager's email) and no commit carries her name.

## 7. Acceptance (refactor)

1. With the seeded content, `python3 tools/build.py` regenerates every page; a
   normalised diff (collapse whitespace, ignore attribute order) of each
   `public/**/*.html` against the pre-refactor output (git `HEAD` before the
   work) shows **no differences** except the intended ones (hours/menu data
   sources, new feature hooks that render nothing while their content is empty).
2. Image outputs for unchanged slots are byte-identical or skipped (incremental).
3. `pytest -q` passes (markdown subset, validator messages, hours logic,
   special-hours/announcement date windows, slot rule, menu ordering).
4. A deliberately broken content file (bad time, missing alt, 300-char
   announcement, missing image) fails the build with the friendly messages and
   leaves `public/` untouched.

## 8. Pages CMS constraints (verified Oct 27 2026 — see docs/dev/research-2026-10-27.json)

Pages CMS v2.1.8 (hosted at app.pagescms.org, repo hunvreus/pagescms). These
change how content files must be designed:

1. **A save rewrites the whole file from the schema.** Keys not declared in
   `.pages.yml` are deleted (`settings.content.merge` is off and buggy — keep it
   off). So every key the site reads from a CMS-managed file MUST be declared,
   and technical values (tuned crops, cover focal points, layout flags) MUST live
   outside CMS-managed files (`src-img/slot-specs.json`, builder config).
2. **Empty values are removed** (`""`, `null`, `[]`, `{}`); files are written
   with 2-space indent, no final newline, keys in field order. The build must
   read every content file through a defaults layer (`tools/content.py`:
   schema-derived defaults deep-merged under the file) so a missing key ==
   its default. Booleans: `"false"` strings coerce to true in the CMS — store
   real booleans.
3. **JSON collections need `filename` ending in `.json`** (e.g.
   `filename: "{primary}.json"` or `"{fields.slug}.json"`), else entries vanish.
4. **Never use the object form of `list` (`{min,max,...}`) at a file's top
   level** (bug #399). Use it only inside an object field, and always include
   `collapsible`.
5. Optional string/text fields with `pattern` reject blanks → write patterns as
   `^$|<regex>`; `minlength` only on required fields. Per-type settings go
   under `options:` (`maxlength`, `min`, `values`, `format`...).
6. Date fields: `options.format: yyyy-MM-dd` (times: use a `string` with a
   `^$|^([01]\d|2[0-3]):[0-5]\d$` pattern, not a datetime), `default: ""` so
   new dates start blank. Existing values must match the format.
7. Select stores `name`; no free text. Image fields store the media `output`
   prefix + path; HEIC is not an image category → extensions jpg/jpeg/png/webp.
8. **Uploads over ~3.3 MB fail (413)** on the hosted app. Provide a no-upload
   in-browser "prepare a photo" page on the site (`/photo-prep`, noindex): pick a
   photo → it is resized to 2400 px long edge JPEG ~85% in the browser
   (canvas), shows the new size, offers Download. The handbook links to it.
9. Collaborators can delete/rename anything in a media folder and can switch
   branches. Media: `input: src-img`, `output: src-img`, default upload path
   `src-img/uploads`, image extensions only. The undo/restore workflows cover
   the photos in `src-img/` as well as `content/`. Workflows only act on `main`.
10. **Actions are not checked server-side**: any CMS user can dispatch any
   workflow that has a `payload` input, on any branch, with any values. Only the
   five safe workflows accept `payload`; each verifies `github.ref ==
   refs/heads/main`, allow-lists inputs, and reads the payload in Python from
   the run's event file (`$GITHUB_EVENT_PATH`, tools/ci/payload.py) — never
   `${{ }}` inside `run:` (injection), and not through a step's `env:` either:
   GitHub prints a step's environment in its log, logs of a public repo are
   public, and the payload includes the manager's email address.
11. No preview, no in-app undo; History shows the last 3 commits. Our "Undo my
   last change" action + validation + backups are the safety net.
12. Hosted app GitHub App permissions: Administration, Actions, Contents
   (read/write) — install on this repo only. Collaborator invites expire after
   24 h; sign-in codes after 5 min.
13. Before go-live, normalise every CMS-managed file to the CMS's own output
   format (`tools/cms_normalize.py`, driven by `.pages.yml`) so later diffs only
   show real edits; a test simulates a CMS save (drop undeclared + empty keys,
   reorder) on every content file of the frozen seed (tests/fixtures/seed —
   tests never read the live content/) and asserts the built site is
   unchanged. CI runs `cms_normalize.py --check` on the live files as a
   developer-only step that never blocks a publish.

## 9. Instagram (verified)

Behold (behold.so) free plan: JSON feed `https://feeds.behold.so/<id>`, ≤ 6
posts, refreshed daily, no branding, Behold refreshes the Instagram token;
needs an Instagram Business/Creator account authorised by the manager. **Every
feed request counts toward 1,200 views/month and the feed pauses at the cap**,
so visitors' browsers must NEVER call it. Fetch it in the build: the daily
scheduled build always fetches; every other build reuses a feed fetched in the
last 12 hours (kept with its photos in `src-img/instagram/`, in the CI cache),
so a busy day of saves costs one or two extra requests (≈ 30–90 a month); a
failed fetch keeps the last good feed for 3 days; the whole fetch has a 60 s
deadline. Use `posts[].sizes.*` (WebP on behold.pictures; for
videos these are thumbnails), validate permalink host (instagram.com) and image
host (behold.pictures), re-host the images through the normal photo pipeline,
alt = `altText` or first line of `prunedCaption` or "Instagram post from
@layerssuperfoodbar". Any error / < 3 posts → the last good feed (< 3 days old), else the curated posts. The section
pre-renders static HTML (no client fetch). List semantics: `role="list"`.

## 10. Hosting (verified)

Build once in Actions; deploy the same build to GitHub Pages (preview, under
`/layers/`, via the URL-prefix transform) and, when secrets exist, to
Cloudflare Pages via `cloudflare/wrangler-action` Direct Upload from the repo
root (`wrangler pages deploy public` picks up `functions/`) — pinned to a full
commit (v4.1.3, `953926a2…`), not the movable `v4` tag, because it is handed
the Cloudflare token. Jobs that push check out with `persist-credentials:
false` and give the token only to the step that saves. Pin
actions/checkout@v7, setup-python@v7, cache@v6, configure-pages@v6,
upload-pages-artifact@v5 (`include-hidden-files: true` for `.nojekyll`),
deploy-pages@v5. Deploy job permissions: `pages: write`, `id-token: write`.
Build-job concurrency `cancel-in-progress: true`; deploy jobs `false`.
GitHub Pages needs a public repo on GitHub Free → keep backups free of anything
private (they are public too). Cron is UTC (the workflows set `timezone:
America/Los_Angeles`); schedules auto-disable after 60 days without activity
in public repos → the weekly keep-alive job (§6).

## 11. Phase B decisions (Oct 27, after the core landed)

- **Specials order button:** new key `order_button` on specials: `none` |
  `square` | `link` (default `none`). `square` → "Order on Square" to the store;
  `link` → "Order" to `order_url`; `none` → no button, and a small line
  "In store for a limited time" instead (copy key `availability_note`, default
  "In store for a limited time."). Phi Velvet → `none` (it isn't on Square).
- **Delivery links:** when `ordering.doordash_url` / `ubereats_url` are set,
  show them on Visit (a quiet "Delivery: DoorDash · Uber Eats" line under the
  order buttons) and as buttons on /links. Nothing when empty.
- **Staff tool pages (noindex, not in nav/sitemap, plain developer copy, not
  CMS-editable):** `/photo-prep` (§8.8) and `/brand` (brand kit: logo
  downloads, the colour tokens, Archivo, the QR codes, 4–5 photo do's/don'ts).
- **QR codes:** the build writes `public/assets/qr/{menu,order,links}.svg` and
  `.png` (1024 px, dark ink on white, 4-module quiet zone) with segno; a test
  decodes each PNG with OpenCV's QRCodeDetector and checks the URL. Production
  base URL `https://layerssuperfoodbar.com`; order QR → the Square store.
- **CMS workflow file names (fixed):** `build-deploy.yml` ("Publish now"),
  `menu-refresh.yml`, `backup.yml`, `restore.yml`, `undo.yml`.
- `build-report.json` / `build-report.md` are build artifacts → gitignored.
- **Photo storage (owner decision):** this repo is a public demo. Full-size
  camera originals will move to a separate private repo; this repo keeps web
  masters (≤ 4096 px originals, ≤ 3200 px albums). Not part of Phase B — the
  owner's maintainer does it at publish time.
