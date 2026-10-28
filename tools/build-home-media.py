#!/usr/bin/env python3
"""
Builds every photograph and the film for the site.

  python3 tools/build-home-media.py            # photos + film
  python3 tools/build-home-media.py --images   # photos only
  python3 tools/build-home-media.py --film     # film only
  python3 tools/build-home-media.py --only home/hero,menu/strawesome
  python3 tools/build-home-media.py --images --force   # rebuild even if unchanged

Each place a photo appears is a "slot". Two files describe a slot:

  content/…               WHICH photo: the manager's choice, edited in the CMS
                          (pages/<page>.json photos, menu.json items, site.json
                          share image), with a focus and zoom keyword.
  src-img/slot-specs.json HOW it is cut (technical, not in the CMS):

  "home/hero": {
    "content": "pages/home:photos.hero",         # the content field it reads
    "aspect": "16:10",                           # w:h, or a number
    "widths": "full",                            # a size set below
    "max_width": 1920,                           # optional cap
    "tuned": {                                   # today's hand-tuned crop + retouch
      "image": "src-img/originals/prep-cap-topdown.jpg",
      "focal": [0.58, 0.5],                      # crop centre, 0–1 of the photo
      "zoom": 1.0,                               # >1 crops tighter around the focal point
      "edit": {"wb": 0.3, "exposure": 0.35, …}   # retouch recipe, see photo_edit.py
    }
  }

The rule (CMS_SPEC §4): while the content still points at tuned.image and its
focus and zoom are "auto", the tuned focal/zoom/edit are used exactly, so the
output is identical to the hand-tuned original. Any other photo is cropped by
its focus keyword (auto = centre, top, bottom-left, …) and zoom keyword (auto /
none = 1.0, a-little = 1.15, more = 1.35) and gets the gentle default retouch.

Menu photos come from data/menu-fallback.json (one square slot per item with a
photo); their tuning is the slot spec with the item's "square_id". A Square
product photo without tuning gets the studio recipe Square photos always had.

Entries with a photo each (content.ENTRY_SLOTS) get their slots here too:
  instagram/<n>     the homepage Instagram grid, from data/instagram.json
                    (tools/instagram.py): an album photo keeps its album
                    retouch, a Behold download is shown as posted (crop and
                    sharpen only), any other photo gets the gentle retouch;
  specials/<slug>   each published special that is on today;
  events/<slug>     each published upcoming event with a photo.
And the photos people add under "More sections" (section_slots):
  blocks/<page>_<n> a section photo on one of the site's pages ("_<k>" for
                    each photo of a row);
  custom/<address>_<n> / _top   the sections and the top photo of a page of
                    the manager's own.
A slot-specs.json entry under the same name adds hand tuning (tuned.image …).

The build is incremental: each slot's fingerprint (source bytes, spec, edit,
pipeline code) is stored in src-img/media-manifest.json and an unchanged slot
is skipped. Outputs a slot no longer makes (a width that went away, a renamed
menu item, a photo removed from the content) are deleted — by tools/build.py
only AFTER the pages have rendered and passed their check (cleanup=False
hands the list back), so a failed build never leaves public/ with pages that
point at deleted files.

Outputs <slot>-<w>.webp and .jpg in public/assets/img/<group>/ for each width
(never upscaled), with no metadata (no GPS), and src-img/media-manifest.json,
which tools/render.py reads to build responsive <picture> markup.

Requires Pillow and numpy (pip3 install -r requirements.txt). OpenCV
(opencv-python-headless) enables noise reduction; ffmpeg on PATH is needed for
the film.
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("error: Pillow is required — pip3 install Pillow numpy")
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import content as content_mod  # noqa: E402
import hours  # noqa: E402
import instagram  # noqa: E402
import photo_edit  # noqa: E402
import photo_load  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src-img"
OUT = ROOT / "public" / "assets" / "img"
SPECS_FILE = SRC / "slot-specs.json"
MANIFEST = SRC / "media-manifest.json"
MENU_DATA = ROOT / "data" / "menu-fallback.json"

WIDTHS = {
    "full":   (960, 1440, 1920, 2560),   # full-bleed bands
    "half":   (640, 960, 1440, 1920),    # half-width tiles (1x2 pairs, 3-up rows on phones)
    "tall":   (480, 720, 960, 1280),     # portrait tiles in 3-up rows
    "phone":  (640, 960, 1280, 1440),    # art-directed phone crops
    "card":   (480, 720, 960, 1440),     # menu photos
    "tile":   (480, 720, 960),           # the Instagram grid (4 across, 2 on phones)
    "thumb":  (240, 480),                # small thumbnails (the events list)
    "share":  (1200,),                   # the social share card (1200×630)
}
# Folders (slot groups) the stale-file sweep looks after.
GROUPS = {"home", "menu", "story", "catering", "visit", "what", "gift", "loyalty", "site",
          "instagram", "specials", "events", "blocks", "custom"}
JPEG_Q, WEBP_Q = 82, 80
# Bump when the crop/resize/encode code in this file changes its output, so
# every slot is rebuilt once. (Code changes in photo_edit.py are picked up by
# hash; comment and docstring edits there are not, and don't need to be.)
PIPELINE_VERSION = 1

# Retouch for a photo nobody has tuned yet: a gentle, safe correction.
GENTLE_EDIT = {"wb": 0.4, "levels": 0.4, "highlights": 0.15, "denoise": 1}
# Square product photos are studio shots: keep their colour, light house grade.
MENU_EDIT = {"wb": 0, "levels": 0.2, "contrast": 0.04, "vibrance": 0, "house": 0.4}
# The album retouch (tools/build-albums.py EDIT): an album photo reused in the
# Instagram grid looks the same as it does in its album.
ALBUM_EDIT = {"wb": 0.5, "levels": 0.5, "denoise": 1.5}
# A post downloaded from the Instagram feed was already edited for Instagram:
# shown as posted (crop, resize and output sharpening only).
AS_POSTED = {"wb": 0, "levels": 0, "contrast": 0, "vibrance": 0, "house": 0}

parse_aspect = content_mod.parse_aspect


def focal_crop(im, aspect, fx, fy, zoom=1.0):
    """Largest crop of the aspect (shrunk by zoom), centred on (fx, fy), inside the frame."""
    w, h = im.size
    if w / h > aspect:
        cw, ch = h * aspect, h
    else:
        cw, ch = w, w / aspect
    cw, ch = round(cw / zoom), round(ch / zoom)
    left = min(max(round(fx * w - cw / 2), 0), w - cw)
    top = min(max(round(fy * h - ch / 2), 0), h - ch)
    return im.crop((left, top, left + cw, top + ch))


def framing(spec, image, focus="auto", zoom="auto", default_edit=GENTLE_EDIT):
    """(focal, zoom, edit): the tuned values while the content still points at
    the tuned photo with auto framing, else the keywords + the default retouch
    (content.framing)."""
    return content_mod.framing(spec.get("tuned"), image, focus, zoom, default_edit)


def _job(spec, image, focal, zoom, edit):
    return {"src": image, "aspect": spec.get("aspect", 1), "widths": spec.get("widths", "half"),
            "max_width": spec.get("max_width"), "focal": focal, "zoom": zoom, "edit": edit}


def page_slots(content, specs):
    """Slots bound to a content field (pages, site share image). Photos of
    unpublished pages, and empty photo fields, make no slot."""
    slots = {}
    for slot, spec in specs.items():
        if slot.startswith("_") or not isinstance(spec, dict) or not spec.get("content"):
            continue
        src, field = spec["content"].split(":", 1)
        if src.startswith("pages/"):
            doc = content["pages"][src.split("/", 1)[1]]
            if not content_mod.page_published(doc):
                continue
        else:
            doc = content[src]
        val = content_mod.get_path(doc, field)
        photo = {"image": val} if isinstance(val, str) else val
        image = content_mod.image_rel(photo.get("image"))
        if not image:
            continue
        focal, zoom, edit = framing(spec, image, photo.get("focus", "auto"), photo.get("zoom", "auto"))
        slots[slot] = _job(spec, image, focal, zoom, edit)
    return slots


def menu_slots(content, specs, menu_data=None):
    """One square slot per menu item that has a photo (data/menu-fallback.json,
    or the menu_data file given)."""
    menu_data = pathlib.Path(menu_data) if menu_data else MENU_DATA
    if not menu_data.exists():
        return {}
    by_id = {s["square_id"]: s for s in specs.values() if isinstance(s, dict) and s.get("square_id")}
    entries = {it.get("square_id"): it for it in content["menu"]["items"]}
    slots = {}
    for cat in json.loads(menu_data.read_text())["categories"]:
        for it in cat["items"]:
            if not it.get("slot") or not it.get("image_source"):
                continue
            spec = by_id.get(it["id"], {"aspect": "1", "widths": "card"})
            entry = entries.get(it["id"], {})
            image = content_mod.image_rel(it["image_source"])
            default = MENU_EDIT if image.startswith("src-img/menu/") else GENTLE_EDIT
            focal, zoom, edit = framing(spec, image, entry.get("focus", "auto"), entry.get("zoom", "auto"), default)
            slots[it["slot"]] = _job({**spec, "aspect": spec.get("aspect", "1"), "widths": spec.get("widths", "card")},
                                     image, focal, zoom, edit)
    return slots


def _entry_job(specs, slot, kind, image, default_edit):
    """A job for a per-entry slot (content.ENTRY_SLOTS), honouring a hand-tuned
    spec under the same slot name if there is one."""
    _, aspect, widths = content_mod.ENTRY_SLOTS[kind]
    spec = {"aspect": aspect, "widths": widths, **(specs.get(slot) or {})}
    focal, zoom, edit = framing(spec, image, "auto", "auto", default_edit)
    return _job(spec, image, focal, zoom, edit)


def entry_slots(content, specs, today=None, root=ROOT):
    """Instagram tiles, specials and events (see the module docstring)."""
    today = today or hours.shop_today()
    slots = {}
    for post in instagram.load(content, root)["posts"]:
        image = content_mod.image_rel(post["image"])
        edit = (ALBUM_EDIT if image.startswith("src-img/albums/") else
                AS_POSTED if image.startswith("src-img/instagram/") else GENTLE_EDIT)
        slots[post["slot"]] = _entry_job(specs, post["slot"], "instagram", image, edit)
    for s in content["specials"]:
        image = content_mod.image_rel(s["image"])
        if image and s["published"] and hours.in_window(today, s["starts"], s["ends"]):
            slot = f"specials/{s['slug']}"
            slots[slot] = _entry_job(specs, slot, "specials", image, GENTLE_EDIT)
    for e in content["events"]:
        image, day = content_mod.image_rel(e["image"]), hours.parse_date(e["date"])
        if image and e["published"] and day and day >= today:
            slot = f"events/{e['slug']}"
            slots[slot] = _entry_job(specs, slot, "events", image, GENTLE_EDIT)
    return slots


def section_slots(content, specs):
    """The photos in "More sections" (content.section_photos names them:
    blocks/<page>_<n>[_<k>]) on every published page that has sections, and
    on each published page of her own (custom/<address>_<n>[_<k>], plus its
    top photo custom/<address>_top). Cropped by their focus and zoom with the
    gentle retouch; a slot-specs.json entry under the same name adds tuning."""
    def job(slot, photo, aspect, widths):
        image = content_mod.image_rel(photo.get("image"))
        if not image:
            return
        spec = {"aspect": aspect, "widths": widths, **(specs.get(slot) or {})}
        focal, zoom, edit = framing(spec, image, photo.get("focus", "auto"), photo.get("zoom", "auto"))
        slots[slot] = _job(spec, image, focal, zoom, edit)

    slots = {}
    owners = [(key, content["pages"][key.split("/", 1)[1]] if key.startswith("pages/") else content[key])
              for key in content_mod.SECTION_FILES]
    owners += [(f"custom-pages/{p['slug']}", p) for p in content.get("custom-pages", [])]
    for key, doc in owners:
        if not content_mod.page_published(doc):
            continue
        prefix = content_mod.sections_prefix(key)
        for p in content_mod.section_photos(prefix, doc.get("sections")):
            job(p["slot"], p["photo"], p["aspect"], p["widths"])
        if key.startswith("custom-pages/"):
            job(f"{prefix}_top", doc["photo"], *content_mod.CUSTOM_TOP_PHOTO[:2])
    return slots


def all_slots(root=ROOT, today=None):
    """Every photo slot of the site at `root` (its content, slot specs and menu data)."""
    root = pathlib.Path(root)
    content = content_mod.load_all(root)
    specs = json.loads((root / "src-img" / "slot-specs.json").read_text())
    slots = page_slots(content, specs)
    slots.update(menu_slots(content, specs, root / "data" / "menu-fallback.json"))
    slots.update(entry_slots(content, specs, today, root))
    slots.update(section_slots(content, specs))
    return slots


_CODE = None


def code_version():
    """Changes whenever the pipeline would produce different pixels."""
    global _CODE
    if _CODE is None:
        h = content_mod.code_fingerprint(ROOT / "tools" / "photo_edit.py")
        _CODE = f"{PIPELINE_VERSION}:{JPEG_Q}:{WEBP_Q}:{h}"
    return _CODE


def fingerprint(job, src_file):
    rungs = list(WIDTHS[job["widths"]]) if isinstance(job["widths"], str) else list(job["widths"])
    key = {"src": hashlib.sha256(src_file.read_bytes()).hexdigest(), "aspect": str(job["aspect"]),
           "rungs": rungs, "max_width": job["max_width"], "focal": job["focal"], "zoom": job["zoom"],
           "edit": job["edit"], "code": code_version()}
    # Only a photo that needs converting on the way in (a colour profile other
    # than sRGB, transparency, 16-bit) has a load signature: every ordinary
    # photo keeps the fingerprint it always had (tools/photo_load.py).
    load = photo_load.signature(src_file)
    if load:
        key["load"] = load
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:20]


def _outputs(slot, widths):
    group, name = slot.split("/", 1)
    return [OUT / group / f"{name}-{w}.{ext}" for w in widths for ext in ("webp", "jpg")]


def _stale_in_group(group, keep):
    """<name>-<w>.webp/.jpg files in a group folder that `keep` ({name: set of
    widths}) doesn't list. "(.*)": even a file with an empty name part
    ("-337.jpg") is matched, so nothing can linger."""
    d = OUT / group
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir()):
        m = re.fullmatch(r"(.*)-(\d+)\.(webp|jpg)", f.name)
        if m and int(m.group(2)) not in keep.get(m.group(1), ()):
            out.append(f)
    return out


def _stale_widths(slot, made):
    """This slot's files for widths it no longer makes."""
    group, name = slot.split("/", 1)
    out = []
    for f in sorted((OUT / group).glob(f"{name}-*")):
        m = re.fullmatch(re.escape(name) + r"-(\d+)\.(webp|jpg)", f.name)
        if m and int(m.group(1)) not in made:
            out.append(f)
    return out


def remove(paths):
    """Delete stale outputs (files, then folders left empty). Returns the count of files."""
    n = 0
    for f in paths:
        if f.is_file():
            f.unlink()
            n += 1
    for d in sorted({f.parent for f in paths}, reverse=True):
        if d.is_dir() and d != OUT and not any(d.iterdir()):
            d.rmdir()
    return n


def make_slot(slot, s, src):
    """Crop, retouch and save every width of one slot. Returns the widths made."""
    aspect = parse_aspect(s.get("aspect", 1))
    im = photo_load.open_rgb(src)          # upright, 8-bit sRGB, transparency on white
    fx, fy = s.get("focal", [0.5, 0.5])
    im = focal_crop(im, aspect, fx, fy, s.get("zoom", 1.0))
    rungs = [w for w in WIDTHS[s.get("widths", "half")] if w <= (s.get("max_width") or 99999)]
    widths = [w for w in rungs if w <= im.width]
    # A crop smaller than the largest rung is also served at its own width,
    # instead of being snapped down to the rung below (never upscaled).
    if len(widths) < len(rungs) and (not widths or im.width > max(widths) * 1.15):
        widths.append(im.width)
    top = max(widths)
    if im.width > top * 1.15:                     # work at delivery resolution
        im = im.resize((top, round(top / aspect)), Image.LANCZOS)
    edit = s.get("edit", {})
    im = photo_edit.finish(im, edit)
    group, name = slot.split("/", 1)
    dest = OUT / group
    dest.mkdir(parents=True, exist_ok=True)
    made = []
    for tw in sorted(set(widths)):
        th = round(tw / aspect)
        r = photo_edit.output(im, tw, th, edit, im.width)
        # saved without exif/icc: no camera metadata (GPS) reaches the site
        r.save(dest / f"{name}-{tw}.webp", "WEBP", quality=WEBP_Q, method=6)
        r.save(dest / f"{name}-{tw}.jpg", "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
        made.append(tw)
    return made, aspect


def build_images(only=None, force=False, today=None, cleanup=True):
    """Build changed slots, skip unchanged ones, find stale outputs.
    Returns {"built": [...], "skipped": [...], "stale": [paths], "removed": n,
    "missing": [...]}. With cleanup=True the stale files are deleted here
    ("removed" counts them); tools/build.py passes False and deletes
    report["stale"] itself once the pages are safely written."""
    slots = all_slots(today=today)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    report = {"built": [], "skipped": [], "stale": [], "removed": 0, "missing": []}
    for slot, s in slots.items():
        if only and slot not in only:
            continue
        src = ROOT / s["src"]
        if not src.is_file():
            print(f"  ! missing source for {slot}: {s['src']}")
            report["missing"].append(f"{slot}: {s['src']}")
            continue
        fp = fingerprint(s, src)
        old = manifest.get(slot, {})
        if (not force and old.get("fp") == fp and old.get("widths")
                and all(f.is_file() for f in _outputs(slot, old["widths"]))):
            report["skipped"].append(slot)
            continue
        made, aspect = make_slot(slot, s, src)
        report["stale"] += _stale_widths(slot, made)
        manifest[slot] = {"widths": made, "aspect": round(aspect, 4), "fp": fp}
        report["built"].append(slot)
        print(f"  {slot:28s} {aspect:5.3f}  {s['src'][8:46]:38s} widths {made}", flush=True)
    if not only:
        # Slots that no longer exist (renamed menu item, photo cleared, page
        # unpublished): drop them from the manifest and delete their files.
        for slot in [k for k in manifest if k not in slots]:
            del manifest[slot]
        for g in sorted({k.split("/", 1)[0] for k in manifest} | GROUPS):
            keep = {k.split("/", 1)[1]: set(v["widths"]) for k, v in manifest.items() if k.split("/", 1)[0] == g}
            report["stale"] += _stale_in_group(g, keep)
    report["stale"] = sorted(set(report["stale"]))
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    if cleanup:
        report["removed"] = remove(report["stale"])
    print(f"  {len(report['built'])} built, {len(report['skipped'])} unchanged (skipped), "
          f"{len(report['stale'])} stale file(s) {'removed' if cleanup else 'to remove'}")
    return report


# ---------------------------------------------------------------------------
# Film
# ---------------------------------------------------------------------------
FILMS = {   # source stem in src-video/ -> (max width, CRF, poster widths, poster time in s)
    "home-film":   (2400, 26, (960, 1440, 1920, 2400), 1.2),
    "home-film-m": (1080, 26, (540, 720, 1080), 2.0),   # the team waving hello, facing camera
}


def build_film():
    """Silent, looping, web-ready MP4s + responsive posters for the film band."""
    if not shutil.which("ffmpeg"):
        sys.exit("error: ffmpeg is required for the film")
    out = ROOT / "public" / "assets" / "video"
    out.mkdir(parents=True, exist_ok=True)
    for stem, (max_w, crf, poster_ws, poster_at) in FILMS.items():
        src = next((ROOT / "src-video" / f"{stem}{e}" for e in (".mp4", ".mov", ".m4v")
                    if (ROOT / "src-video" / f"{stem}{e}").is_file()), None)
        if src is None:
            print(f"  ! no src-video/{stem}.(mp4|mov) — skipped")
            continue
        vf = f"scale='min({max_w},iw)':-2:flags=lanczos,format=yuv420p"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-an", "-vf", vf,
                        "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", str(crf),
                        "-movflags", "+faststart", str(out / f"{stem}.mp4")], check=True)
        frame = out / f"_{stem}-frame.png"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(poster_at), "-i", str(src),
                        "-frames:v", "1", str(frame)], check=True)
        with Image.open(frame) as im:
            im = im.convert("RGB")
            made = []
            for w in [w for w in poster_ws if w <= im.width] or [im.width]:
                r = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
                r.save(out / f"{stem}-poster-{w}.webp", "WEBP", quality=WEBP_Q, method=6)
                r.save(out / f"{stem}-poster-{w}.jpg", "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
                made.append(w)
        frame.unlink()
        print(f"  video/{stem}.mp4  {(out / f'{stem}.mp4').stat().st_size / 1024:7.0f} KB   posters {made}")


def main():
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    flags = {a for a in args if a.startswith("--") and a not in ("--only", "--force")}
    if not flags or "--images" in flags:
        print("photography")
        r = build_images(only, force="--force" in args)
        if r["missing"]:
            sys.exit(f"error: {len(r['missing'])} photo(s) missing — run python3 tools/validate_content.py")
    if (not flags and not only) or "--film" in flags:
        print("film")
        build_film()
    print("done.")


if __name__ == "__main__":
    main()
