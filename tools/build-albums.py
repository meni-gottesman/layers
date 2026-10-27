#!/usr/bin/env python3
"""
Builds the photo albums on "A Day at Layers" from content/albums/*.json.

  python3 tools/build-albums.py && python3 tools/build-pages.py
  python3 tools/build-albums.py --force      # rebuild even if unchanged

Each album is one file in content/albums/ (edited in the CMS):

  content/albums/run-clubs.json
    {"title": "Run clubs", "order": 2, "published": true,
     "cover": "src-img/albums/02-run-clubs/10.jpg", "cover_focus": "auto",
     "photos": [{"image": "src-img/albums/02-run-clubs/01.jpg", "alt": "…"}, …]}

Albums show in "order" (then by file name); photos in list order. The file
name is the album's slug (its folder under /assets/albums/). Photos can live
anywhere under src-img/ — the original album photos are in
src-img/albums/<NN-slug>/, new uploads land in src-img/uploads/. An album
that is unpublished or has no photos is left out. The cover is a 4:5 crop of
the chosen photo (the first one when none is chosen); its hand-tuned focal
point lives in src-img/slot-specs.json ("album-cover/<slug>") and is used
while the cover is still that photo with cover_focus "auto".

Each photo gets the site's light retouch (white balance, levels, the house
grade) and is saved as WebP + JPEG at 960 and 1600 px wide (never upscaled,
no camera metadata), plus the cover tile at 480/720/960. The build is
incremental: every photo and cover has a fingerprint in
src-img/album-manifest.json and is skipped when unchanged; files an album no
longer uses, and the folders of albums that were removed or unpublished, are
deleted — by tools/build.py only after the pages are written (cleanup=False
hands the list back), so a failed build never strands a page. Writes
data/albums.json, which tools/render.py renders on the albums page.
"""
import hashlib
import json
import pathlib
import shutil
import sys

from PIL import Image
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import content as content_mod  # noqa: E402
import photo_edit  # noqa: E402
import photo_load  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "assets" / "albums"
DATA = ROOT / "data" / "albums.json"
MANIFEST = ROOT / "src-img" / "album-manifest.json"
SPECS = ROOT / "src-img" / "slot-specs.json"
EDIT = {"wb": 0.5, "levels": 0.5, "denoise": 1.5}
SIZES = (960, 1600)
COVER = (480, 720, 960)
PIPELINE_VERSION = 1      # bump when the code below changes its output


def save(im, base):
    im.save(f"{base}.webp", "WEBP", quality=80, method=6)
    im.save(f"{base}.jpg", "JPEG", quality=82, optimize=True, progressive=True)


def _fp(src, *extra):
    h = hashlib.sha256(src.read_bytes()).hexdigest()
    code = content_mod.code_fingerprint(ROOT / "tools" / "photo_edit.py")
    # a load signature only for photos tools/photo_load.py has to convert, so
    # every ordinary album photo keeps the fingerprint it always had
    load = photo_load.signature(src)
    key = json.dumps([h, EDIT, SIZES, COVER, PIPELINE_VERSION, code, *extra] + ([load] if load else []),
                     sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def make_photo(f, dest, n):
    """One album photo at each size. Returns {nominal width: (w, h)}."""
    im = photo_load.open_rgb(f)            # upright, 8-bit sRGB, transparency on white
    im.thumbnail((SIZES[-1], SIZES[-1]), Image.LANCZOS)
    im = photo_edit.finish(im, EDIT)
    srcs = {}
    for w in SIZES:
        if w > im.width and srcs:
            continue
        tw = min(w, im.width)
        r = photo_edit.output(im, tw, round(im.height * tw / im.width), EDIT, im.width)
        save(r, dest / f"{n:02d}-{w}")
        srcs[w] = r.size
    return srcs


def make_cover(f, dest, focal):
    """4:5 crop of the cover photo around the focal point."""
    c = photo_load.open_rgb(f)
    fx, fy = focal
    aspect = 4 / 5
    cw, ch = (round(c.height * aspect), c.height) if c.width / c.height > aspect else (c.width, round(c.width / aspect))
    left = min(max(round(fx * c.width - cw / 2), 0), c.width - cw)
    top = min(max(round(fy * c.height - ch / 2), 0), c.height - ch)
    c = photo_edit.finish(c.crop((left, top, left + cw, top + ch)).resize((COVER[-1], round(COVER[-1] / aspect)), Image.LANCZOS), EDIT)
    for w in COVER:
        save(photo_edit.output(c, w, round(w / aspect), EDIT, c.width), dest / f"cover-{w}")


def _files_exist(dest, names):
    return all((dest / f"{b}.{ext}").is_file() for b in names for ext in ("webp", "jpg"))


def build(force=False, cleanup=True):
    """Returns {"built": n, "skipped": n, "stale": [paths], "missing": [...]};
    stale files/folders are deleted here unless cleanup=False."""
    content = content_mod.load_all(ROOT)
    specs = json.loads(SPECS.read_text()) if SPECS.exists() else {}
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    report = {"built": 0, "skipped": 0, "stale": [], "missing": []}
    albums_out, new_manifest = [], {}
    for a in sorted(content["albums"], key=lambda a: (a["order"], a["slug"])):
        if not a["published"] or not a["photos"]:
            continue
        slug, title = a["slug"], a["title"]
        dest = OUT / slug
        dest.mkdir(parents=True, exist_ok=True)
        prev = manifest.get(slug, {})
        prev_photos = prev.get("photos", [])
        keep, photos, man_photos = set(), [], []
        for n, ph in enumerate(a["photos"], 1):
            f = content_mod.image_file(ph["image"], ROOT)
            if f is None or not f.is_file():
                print(f"  ! missing photo in album {slug}: {ph['image']}")
                report["missing"].append(f"{slug}: {ph['image']}")
                continue
            fp = _fp(f)
            old = prev_photos[n - 1] if n - 1 < len(prev_photos) else {}
            names = [f"{n:02d}-{w}" for w in old.get("sizes", {})]
            if not force and old.get("fp") == fp and names and _files_exist(dest, names):
                srcs = {int(w): tuple(wh) for w, wh in old["sizes"].items()}
                report["skipped"] += 1
            else:
                srcs = make_photo(f, dest, n)
                report["built"] += 1
            keep.update(f"{n:02d}-{w}" for w in srcs)
            big = max(srcs)
            photos.append({"src": f"/assets/albums/{slug}/{n:02d}-{big}", "small": f"/assets/albums/{slug}/{n:02d}-{min(srcs)}",
                           "w": srcs[big][0], "h": srcs[big][1],
                           "alt": ph["alt"].strip() or f"{title}, photo {n}"})
            man_photos.append({"fp": fp, "sizes": {str(w): list(wh) for w, wh in srcs.items()}})
        if not photos:
            continue
        # cover: the chosen photo, else the first; tuned focal while unchanged
        cover = content_mod.image_rel(a["cover"]) or content_mod.image_rel(a["photos"][0]["image"])
        cf = content_mod.image_file(cover, ROOT)
        if cf is None or not cf.is_file():
            cover = content_mod.image_rel(a["photos"][0]["image"])
            cf = content_mod.image_file(cover, ROOT)
        tuned = (specs.get(f"album-cover/{slug}") or {}).get("tuned")
        focal, _, _ = content_mod.framing(tuned, cover, a["cover_focus"], "auto")
        cover_fp = _fp(cf, focal)
        names = [f"cover-{w}" for w in COVER]
        if force or prev.get("cover_fp") != cover_fp or not _files_exist(dest, names):
            make_cover(cf, dest, focal)
            report["built"] += 1
        else:
            report["skipped"] += 1
        keep.update(names)
        for old in sorted(dest.iterdir()):         # photos the album no longer has
            if old.name.rsplit(".", 1)[0] not in keep:
                report["stale"].append(old)
        albums_out.append({"slug": slug, "title": title, "count": len(photos), "cover": f"/assets/albums/{slug}/cover",
                           "cover_widths": list(COVER), "photos": photos})
        new_manifest[slug] = {"photos": man_photos, "cover_fp": cover_fp}
        print(f"  {slug:24s} {len(photos):3d} photos")
    # albums removed or unpublished: their folders go
    if OUT.is_dir():
        for d in sorted(OUT.iterdir()):
            if d.is_dir() and d.name not in new_manifest:
                report["stale"].append(d)
    DATA.write_text(json.dumps(albums_out, indent=1, ensure_ascii=False) + "\n")
    MANIFEST.write_text(json.dumps(new_manifest, indent=1, sort_keys=True) + "\n")
    if cleanup:
        remove(report["stale"])
    print(f"{len(albums_out)} albums -> {DATA.relative_to(ROOT)}  "
          f"({report['built']} images built, {report['skipped']} unchanged)")
    return report


def remove(paths):
    """Delete stale album files and folders (the list build() returns)."""
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()


def main():
    r = build(force="--force" in sys.argv)
    if r["missing"]:
        sys.exit(f"error: {len(r['missing'])} album photo(s) missing — run python3 tools/validate_content.py")


if __name__ == "__main__":
    main()
