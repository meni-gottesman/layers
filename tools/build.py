#!/usr/bin/env python3
"""
Builds the whole site — the one command CI and developers run.

  python3 tools/build.py                     # validate → menu → instagram → photos → albums → qr → pages → cleanup
  python3 tools/build.py --check             # validate content only (writes the report, builds nothing)
  python3 tools/build.py --today 2026-11-26  # build as if it were that day (date-based content)
  python3 tools/build.py --force-images      # rebuild every photo even if unchanged
  python3 tools/build.py --offline           # don't fetch the Instagram feed (the last one, or hand-picked)
  python3 tools/build.py --refresh-instagram # fetch the Instagram feed even if the last one is recent

Order matters, and every step must pass before the next one runs:

  1. validate  content/ is checked (tools/validate_content.py). Any error stops
               here, before anything in public/ or data/ is touched.
  2. menu      data/menu-fallback.json is re-made from the CACHED Square store
               data + content/menu.json (no network; the daily menu refresh
               fetches Square with tools/sync-menu-from-store.py).
  3. instagram which posts the homepage shows (tools/instagram.py): the
               hand-picked ones, or the Behold feed — the only network
               request in the build, and made only when the last fetch is
               over 12 hours old or --refresh-instagram (the daily scheduled
               build) asks for it. Any feed problem falls back to the last
               good feed or the hand-picked posts and is noted in the report.
               Runs before the photos because its pictures are photo slots.
  4. images    every photo slot (tools/build-home-media.py), incremental.
  5. albums    the photo albums (tools/build-albums.py), incremental.
  6. qr        the print QR codes (tools/qr.py): menu, order, links, as SVG +
               PNG in public/assets/qr/. Before the pages, because the /brand
               page links them and the page check needs them to exist.
  7. pages     every page is rendered in memory (tools/render.py) and checked:
               each /assets/ file it references must exist. Only then are the
               pages, sitemap.xml and robots.txt written.
  8. cleanup   photo files nothing uses any more (old widths, removed slots,
               unpublished albums) are deleted — only now, after the pages
               were written, so a build that fails at "pages" leaves the
               current pages with every file they point at.

The film is not part of this build (its source clips aren't in the repo):
tools/compose-film.py + tools/build-home-media.py --film.

Always writes build-report.json and build-report.md (plain English, for the
manager: CI posts it as an issue when an update doesn't publish). Exit code 0
when the site was built, 1 when it wasn't.
"""
import argparse
import html.parser
import pathlib
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import content as content_mod  # noqa: E402
import hours  # noqa: E402
import instagram  # noqa: E402
import qr  # noqa: E402
import render  # noqa: E402
import validate_content  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"


class StepFailed(Exception):
    def __init__(self, problems):
        super().__init__("step failed")
        self.problems = problems


def problem(message, field="", where="Website build", level="error"):
    return {"level": level, "where": where, "field": field, "message": message, "file": ""}


# ---------------------------------------------------------------------------
# Output check: every local asset a page references must exist, and links to
# other pages should go somewhere.
# ---------------------------------------------------------------------------
class _Refs(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.assets, self.links = set(), set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if not v:
                continue
            if k in ("srcset", "imagesrcset"):
                for cand in v.split(","):
                    url = cand.strip().split(" ")[0]
                    if url.startswith("/assets/"):
                        self.assets.add(url)
            elif k in ("src", "poster") or (k == "href" and tag == "link"):
                if v.startswith("/assets/"):
                    self.assets.add(v.split("?")[0])
            elif k == "href" and tag == "a" and v.startswith("/") and not v.startswith("//"):
                self.links.add(v.split("#")[0].split("?")[0] or "/")


def check_output(rendered, published_paths):
    problems = []
    for key, page_html in rendered.items():
        if page_html is None:
            continue
        refs = _Refs()
        refs.feed(page_html)
        for url in sorted(refs.assets):
            if not (PUBLIC / url.lstrip("/")).is_file():
                problems.append(problem(f"The {render.PAGE_CONFIG[key]['out']} page refers to {url}, which "
                                        "wasn't built. This is a build problem, not your content — ask the "
                                        "developer.", field=key))
        for link in sorted(refs.links):
            if link in published_paths or (PUBLIC / link.lstrip("/")).is_file():
                continue
            problems.append(problem(f"A link on the {render.PAGE_CONFIG[key]['out']} page goes to {link}, which "
                                    "isn't a page on the site. Check the link.", field=key, level="warning"))
    return problems


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Layers site.")
    ap.add_argument("--check", action="store_true", help="validate content only")
    ap.add_argument("--today", help="build as if today were YYYY-MM-DD")
    ap.add_argument("--force-images", action="store_true", help="rebuild every photo and album image")
    ap.add_argument("--offline", action="store_true", help="don't fetch the Instagram feed")
    ap.add_argument("--refresh-instagram", action="store_true",
                    help="fetch the Instagram feed even if the last one is under 12 hours old")
    args = ap.parse_args(argv)
    today = hours.parse_date(args.today) if args.today else hours.shop_today()
    if args.today and today is None:
        ap.error("--today must be YYYY-MM-DD")

    steps, problems, extra = [], [], {"today": today.isoformat()}
    stale = []          # photo files to delete once the pages are written

    def run(name, fn):
        t = time.time()
        try:
            detail = fn()
        except StepFailed as e:
            problems.extend(e.problems)
            steps.append({"name": name, "status": "failed", "seconds": round(time.time() - t, 1)})
            raise
        except Exception as e:  # an unexpected failure: plain message + the details for the developer
            tb = traceback.format_exc(limit=4)
            msg = (str(e) if isinstance(e, render.BuildError) else
                   f"Something went wrong in the “{name}” step. This is a problem in the site’s code or "
                   f"setup, not your content — ask the developer. ({type(e).__name__}: {e})")
            problems.append(problem(msg, field=name))
            steps.append({"name": name, "status": "failed", "seconds": round(time.time() - t, 1),
                          "detail": tb.strip().splitlines()[-1]})
            print(tb, file=sys.stderr)
            raise StepFailed([]) from None
        steps.append({"name": name, "status": "ok", "seconds": round(time.time() - t, 1),
                      **({"detail": detail} if detail else {})})
        print(f"✓ {name}" + (f" — {detail}" if detail else ""), flush=True)

    def finish(ok):
        validate_content.write_report(ROOT, problems, "passed" if ok else "failed", steps, extra)
        errors, warnings, drafts = validate_content.split_problems(problems)
        if problems:
            print(validate_content.format_problems(errors + warnings + drafts))
        print(f"\n{'Built' if ok else 'NOT built'}: {len(errors)} error(s), {len(warnings)} warning(s)"
              + (f", {len(drafts)} note(s) on unpublished content" if drafts else "") + ". Report: build-report.md")
        return 0 if ok else 1

    # 1 · validate -----------------------------------------------------------
    def validate():
        found = validate_content.validate(ROOT, today)
        problems.extend(found)
        errors, warnings, drafts = validate_content.split_problems(found)
        if errors:
            raise StepFailed([])
        return ", ".join(x for x in (f"{len(warnings)} warning(s)" if warnings else "",
                                     f"{len(drafts)} note(s) on unpublished content" if drafts else "") if x)

    # 2 · menu (offline, from the cached Square data) -----------------------------
    def menu():
        n = content_mod.load_tool("sync-menu-from-store.py").sync(offline=True)
        return ", ".join(f"{k} {v}" for k, v in n.items())

    # 3 · instagram: which posts the homepage shows ----------------------------
    def instagram_step():
        info = {}
        doc, notes = instagram.build(ROOT, offline=args.offline, refresh=args.refresh_instagram, info=info)
        problems.extend(problem(n, field="Behold feed link", where="Instagram", level="warning") for n in notes)
        return f"{len(doc['posts'])} post(s), {doc['source']}" + (
            f", feed {info['how']}" if doc["source"] == "behold" else "")

    # 4 · photos --------------------------------------------------------------
    def images():
        r = content_mod.load_tool("build-home-media.py").build_images(force=args.force_images, today=today,
                                                                     cleanup=False)
        if r["missing"]:
            raise StepFailed([problem(f"The photo for {m} is missing.", field="images") for m in r["missing"]])
        stale.append(("images", r["stale"]))
        return f"{len(r['built'])} built, {len(r['skipped'])} unchanged"

    # 5 · albums --------------------------------------------------------------
    def albums():
        r = content_mod.load_tool("build-albums.py").build(force=args.force_images, cleanup=False)
        if r["missing"]:
            raise StepFailed([problem(f"The album photo {m} is missing.", field="albums") for m in r["missing"]])
        stale.append(("albums", r["stale"]))
        return f"{r['built']} built, {r['skipped']} unchanged"

    # 6 · QR codes for print (written only when they change) -------------------
    def qr_step():
        r = qr.build(content_mod.load_all(ROOT), PUBLIC / "assets" / "qr")
        return f"{r['written']} written, {r['unchanged']} unchanged" if r["written"] else ""

    # 7 · pages: render all in memory, check, then write -------------------------
    def pages():
        site = render.Site(root=ROOT, today=today)
        rendered = site.render_all()
        published = {site.path_of(k) for k, v in rendered.items() if v is not None}
        found = check_output(rendered, published)
        problems.extend(found)
        if any(p["level"] == "error" for p in found):
            raise StepFailed([])
        written, urls = render.write_pages(site, rendered, PUBLIC)
        extra["pages"] = [str(p.relative_to(ROOT)) for p in written]
        return f"{len(written)} pages, sitemap with {len(urls)} URLs"

    # 8 · cleanup: only now that the pages are written ---------------------------
    def cleanup():
        n = 0
        for kind, paths in stale:
            if kind == "images":
                n += content_mod.load_tool("build-home-media.py").remove(paths)
            else:
                content_mod.load_tool("build-albums.py").remove(paths)
                n += len(paths)
        return f"{n} stale photo file(s)/folder(s) removed" if n else ""

    order = [("validate", validate)] if args.check else [
        ("validate", validate), ("menu", menu), ("instagram", instagram_step), ("images", images),
        ("albums", albums), ("qr", qr_step), ("pages", pages), ("cleanup", cleanup)]
    try:
        for name, fn in order:
            run(name, fn)
    except StepFailed:
        return finish(False)
    return finish(True)


if __name__ == "__main__":
    sys.exit(main())
