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
| `time-24h` | `HH:MM` as a pattern-checked string (not a datetime field, which would store a date too) |
| `calendar-date` | a date stored as `yyyy-MM-dd`, `default: ""` (see the traps) |
| `photo-file` | an image field: media `photos`, picker and uploads in `src-img/uploads`, a note on the 3 MB upload limit |
| `photo-focus`, `photo-zoom` | the crop keywords from `tools/content.py` (`FOCUS`, `ZOOMS`), default `auto` |
| `alt-text` | “Description (alt text)”, 250 characters |
| `web-link`, `site-link` | links: `https://…` only, or also a page on this site (`/menu`, `#faq`) — the validator's `url_ok` rules |
| `formatted-text` | a multi-line box with the `tools/textfmt.py` cheat sheet |
| `page-photo`, `page-photo-no-alt` | a photo spot: photo + alt + focus + zoom, photo and alt required |
| `draft-photo`, `draft-photo-no-alt` | the same with nothing required, for pages that may be unfinished |
| `seo`, `seo-optional-description`, `seo-draft` | the SEO group with its three levels of `required` |

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
| **Photo albums** | `albums` (collection) | `content/albums/*.json` |
| **Instagram** | `instagram` | `content/instagram.json` |
| **Business details** | `site` | `content/site.json` |

Within a file the fields follow the page from top to bottom, photos first and
**SEO last** (the manager rarely needs it). Field order is also the key order
in the saved file.

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
  back under Square's name). The field descriptions say so; the validator's
  warning points at Undo + "Hide from the website".
- **Descriptions** are for a busy café manager: short, concrete, what it does
  on the site and any limit. Never on a list field (see the traps).

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

**Renaming or removing a field** works the same way in reverse. The
normaliser refuses to run while a content file still holds a key that isn't
declared, so remove (or move) the data first.

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
nulls, wrong types, odd dates and paths, undeclared keys). Only the field
types this site uses are ported; it refuses a config that uses others. **If
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

**Media**
- Uploads over ~3.3 MB fail (413, the host's request limit): the descriptions
  point to `/photo-prep`, which shrinks a photo in the browser.
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
