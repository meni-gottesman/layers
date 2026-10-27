#!/usr/bin/env python3
"""
The GitHub Pages URL-prefix transform.

GitHub serves a project site under /<repo>/ (https://meni-gottesman.github.io/layers/),
while the site itself uses root-absolute URLs (/assets/…, /menu). Production
(Cloudflare Pages) serves at the root and needs no change. This copies the
built public/ to a staging folder and prefixes every root-absolute URL with
the base path: HTML attributes (href, src, action, poster), srcset /
imagesrcset candidates, the menu cards' inline item data (HTML-escaped JSON),
every quoted "/assets/… value (inline JSON such as the albums data, and
attributes such as the film's data-src-narrow), CSS url() and the paths
main.js builds. Vendor scripts are left alone. A .nojekyll file is added so
GitHub doesn't run Jekyll over the output.

  python3 tools/ci/prefix.py public _site --prefix /layers

Used by the "Publish the preview" job in .github/workflows/build-deploy.yml
(with the base path GitHub reports) and by tools/deploy-github-preview.py.
An empty prefix (a custom domain on the preview) copies the site unchanged.

The transform is exactly the one tools/deploy-github-preview.py has always
used (that script now imports it from here), with the base path as a
parameter. The leftover check after it is wider than the transform on
purpose: a new kind of root-absolute reference stops the deploy instead of
shipping a page whose links 404 on the preview.
"""
import argparse
import pathlib
import re
import shutil
import sys

DEFAULT_PREFIX = "/layers"


def _norm(prefix):
    """'/layers', 'layers', '/layers/' → '/layers'; '' or '/' → ''."""
    p = (prefix or "").strip().strip("/")
    if p and not re.fullmatch(r"[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*", p):
        raise ValueError(f"not a usable base path: {prefix!r}")
    return f"/{p}" if p else ""


def _not_done(prefix):
    # A root-absolute path that isn't protocol-relative (//host) and isn't
    # already prefixed (so running the transform twice changes nothing).
    return rf"(?!/|{re.escape(prefix[1:])}/)"


def prefix_html(s, prefix=DEFAULT_PREFIX):
    prefix = _norm(prefix)
    if not prefix:
        return s
    nd = _not_done(prefix)
    # href/src/action/poster="/x" (not protocol-relative, not already prefixed)
    s = re.sub(rf'\b(href|src|action|poster)="/{nd}', rf'\1="{prefix}/', s)

    # every candidate inside srcset / imagesrcset
    def fix_set(m):
        return m.group(1) + re.sub(rf'(^|,\s*)/{nd}', rf'\1{prefix}/', m.group(2)) + '"'
    s = re.sub(r'\b((?:image)?srcset=")([^"]*)"', fix_set, s)
    # the menu cards' inline item data (HTML-escaped JSON)
    s = s.replace('&quot;/assets/', f'&quot;{prefix}/assets/')
    # paths inside inline JSON (the albums data) — and, as a side effect, any
    # other attribute holding an /assets/ path (data-src-narrow on the film)
    s = s.replace('"/assets/', f'"{prefix}/assets/')
    return s


def prefix_css(s, prefix=DEFAULT_PREFIX):
    prefix = _norm(prefix)
    if not prefix:
        return s
    return re.sub(rf'url\((["\']?)/{_not_done(prefix)}', rf'url(\1{prefix}/', s)


def prefix_js(s, prefix=DEFAULT_PREFIX):
    prefix = _norm(prefix)
    if not prefix:
        return s
    for p in ("'/assets/", "'/order", "'/api/"):
        s = s.replace(p, p[0] + prefix + p[1:])
    return s


def transform_file(f, prefix):
    """Prefix one staged file in place (HTML, CSS, and our own JS)."""
    if f.suffix == ".html":
        f.write_text(prefix_html(f.read_text(encoding="utf-8"), prefix), encoding="utf-8")
    elif f.suffix == ".css":
        f.write_text(prefix_css(f.read_text(encoding="utf-8"), prefix), encoding="utf-8")
    elif f.suffix == ".js" and "vendor" not in f.parts:
        f.write_text(prefix_js(f.read_text(encoding="utf-8"), prefix), encoding="utf-8")


# Anything still pointing at the host root after the transform: an HTML
# attribute value or srcset candidate, a CSS url(), or a quoted /assets/ path
# in inline JSON or our JS. Wider than what the transform rewrites, on purpose:
# a new kind of reference makes the deploy stop instead of shipping a 404.
def leftovers(site, prefix=DEFAULT_PREFIX):
    """Unprefixed root-absolute URLs left in a staged site, as
    'path: url' strings (empty list = clean)."""
    prefix = _norm(prefix)
    if not prefix:
        return []
    site = pathlib.Path(site)
    nd = _not_done(prefix)
    attr = re.compile(rf'\s[\w:.-]+="(/{nd}[^"]*)"')
    cand = re.compile(rf'\b(?:image)?srcset="([^"]*)"')
    css = re.compile(rf'url\(["\']?(/{nd}[^)"\']*)')
    quoted = re.compile(rf'(?:&quot;|["\'])(/{nd}(?:assets|api|order)\b[^"\'&]*)')
    out = []
    for f in sorted(site.rglob("*")):
        if not f.is_file() or f.suffix not in (".html", ".css", ".js") or "vendor" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        found = []
        if f.suffix == ".html":
            found += attr.findall(text)
            for v in cand.findall(text):
                found += [c.strip().split(" ")[0] for c in v.split(",")
                          if re.match(rf"/{nd}", c.strip())]
        if f.suffix in (".html", ".css"):
            found += css.findall(text)
        if f.suffix in (".html", ".js"):
            found += quoted.findall(text)
        out += [f"{f.relative_to(site)}: {u[:80]}" for u in dict.fromkeys(found)]
    return out


def prefix_tree(src, dest, prefix=DEFAULT_PREFIX):
    """Copy the built site `src` to `dest` (replaced), add .nojekyll and
    prefix every root-absolute URL. Returns the leftover list (see
    leftovers()); callers stop the deploy when it isn't empty."""
    src, dest = pathlib.Path(src), pathlib.Path(dest)
    if not (src / "index.html").is_file():
        raise FileNotFoundError(f"{src}/index.html is missing — build the site first")
    prefix = _norm(prefix)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    (dest / ".nojekyll").write_text("")
    if prefix:
        for f in dest.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                transform_file(f, prefix)
    return leftovers(dest, prefix)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Copy the built site and prefix its URLs for GitHub Pages.")
    ap.add_argument("src", help="the built site (public/)")
    ap.add_argument("dest", help="where to write the prefixed copy (replaced)")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX,
                    help="base path, e.g. /layers ('' for a site served at the root)")
    args = ap.parse_args(argv)
    try:
        left = prefix_tree(args.src, args.dest, args.prefix)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"error: {e}")
    if left:
        sys.exit("error: unprefixed URLs:\n  " + "\n  ".join(left[:20]))
    n = sum(1 for f in pathlib.Path(args.dest).rglob("*") if f.is_file())
    print(f"{n} files → {args.dest} (base path {_norm(args.prefix) or '/'})")


if __name__ == "__main__":
    main()
