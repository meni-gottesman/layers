"""The GitHub Pages URL-prefix transform (tools/ci/prefix.py): the same
behaviour tools/deploy-github-preview.py always had, and — run on the real
built public/ — no root-absolute URL left unprefixed and no local link or
image that doesn't resolve under /layers/."""
import html.parser
import pathlib
import re
import urllib.parse

import pytest

from ci import prefix
from conftest import ROOT

PUBLIC = ROOT / "public"


# ---------------------------------------------------------------------------
# The rules, one by one (the behaviour of the original deploy script)
# ---------------------------------------------------------------------------
def test_html_attributes():
    s = ('<a href="/menu">m</a><img src="/assets/a.jpg"><form action="/api/catering">'
         '<video poster="/assets/p.jpg"></video><script src="/assets/js/main.js"></script>')
    assert prefix.prefix_html(s) == (
        '<a href="/layers/menu">m</a><img src="/layers/assets/a.jpg"><form action="/layers/api/catering">'
        '<video poster="/layers/assets/p.jpg"></video><script src="/layers/assets/js/main.js"></script>')


def test_leaves_external_protocol_relative_and_done_urls_alone():
    s = ('<a href="https://x.com/a">x</a><a href="//cdn.x/a">c</a><a href="/layers/menu">d</a>'
         '<a href="#top">t</a><a href="mailto:a@b.c">e</a><a href="menu">r</a>')
    assert prefix.prefix_html(s) == s


def test_srcset_candidates():
    s = '<source srcset="/assets/a-640.webp 640w, /assets/a-960.webp 960w" imagesrcset="/x.jpg 1x,/y.jpg 2x">'
    assert prefix.prefix_html(s) == ('<source srcset="/layers/assets/a-640.webp 640w, /layers/assets/a-960.webp '
                                     '960w" imagesrcset="/layers/x.jpg 1x,/layers/y.jpg 2x">')


def test_inline_json_and_escaped_item_data():
    s = ('<div data-item="{&quot;img&quot;:&quot;/assets/img/menu/a.jpg&quot;}"></div>'
         '<script type="application/json">{"src": "/assets/albums/x/01-960"}</script>'
         '<div data-src-narrow="/assets/video/home-film-m.mp4"></div>')
    out = prefix.prefix_html(s)
    assert "&quot;/layers/assets/img/menu/a.jpg&quot;" in out
    assert '"src": "/layers/assets/albums/x/01-960"' in out
    assert 'data-src-narrow="/layers/assets/video/home-film-m.mp4"' in out


def test_css_and_js():
    assert prefix.prefix_css("a{background:url(/assets/i.png)} b{background:url('/x.png')} "
                             "c{background:url(//cdn/x.png)}") == (
        "a{background:url(/layers/assets/i.png)} b{background:url('/layers/x.png')} "
        "c{background:url(//cdn/x.png)}")
    assert prefix.prefix_js("fetch('/api/menu'); x = '/assets/img/face.png'; go('/order'); y = '/menu';") == (
        "fetch('/layers/api/menu'); x = '/layers/assets/img/face.png'; go('/layers/order'); y = '/menu';")


def test_idempotent_and_other_base_paths():
    s = '<a href="/menu"></a><img srcset="/a.jpg 1x">'
    once = prefix.prefix_html(s)
    assert prefix.prefix_html(once) == once
    assert prefix.prefix_html(s, "/layers-site/") == '<a href="/layers-site/menu"></a><img srcset="/layers-site/a.jpg 1x">'
    assert prefix.prefix_html(s, "") == s and prefix.prefix_html(s, "/") == s     # custom domain: no prefix
    with pytest.raises(ValueError):
        prefix.prefix_html(s, '/x" onload="')


def test_matches_the_original_deploy_script_exactly():
    """Byte-for-byte the same output as the transform tools/deploy-github-preview.py
    had before it was moved here (kept verbatim below), on every built file."""
    def old_html(s):
        s = re.sub(r'\b(href|src|action|poster)="/(?!/|layers/)', r'\1="/layers/', s)

        def fix_set(m):
            return m.group(1) + re.sub(r'(^|,\s*)/(?!/|layers/)', r'\1/layers/', m.group(2)) + '"'
        s = re.sub(r'\b((?:image)?srcset=")([^"]*)"', fix_set, s)
        return s.replace('&quot;/assets/', '&quot;/layers/assets/').replace('"/assets/', '"/layers/assets/')

    def old_css(s):
        return re.sub(r'url\((["\']?)/(?!/|layers/)', r'url(\1/layers/', s)

    def old_js(s):
        for p in ("'/assets/", "'/order", "'/api/"):
            s = s.replace(p, p[0] + "/layers" + p[1:])
        return s

    checked = 0
    for f in PUBLIC.rglob("*"):
        if f.suffix == ".html":
            t = f.read_text(encoding="utf-8")
            assert prefix.prefix_html(t) == old_html(t), f
        elif f.suffix == ".css":
            t = f.read_text(encoding="utf-8")
            assert prefix.prefix_css(t) == old_css(t), f
        elif f.suffix == ".js" and "vendor" not in f.parts:
            t = f.read_text(encoding="utf-8")
            assert prefix.prefix_js(t) == old_js(t), f
        else:
            continue
        checked += 1
    assert checked >= 10


# ---------------------------------------------------------------------------
# On the real built site
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    dest = tmp_path_factory.mktemp("pages") / "layers"
    left = prefix.prefix_tree(PUBLIC, dest, "/layers")
    return dest, left


def test_real_site_has_no_unprefixed_urls(staged):
    dest, left = staged
    assert left == []
    assert (dest / ".nojekyll").is_file()
    vendor = next(PUBLIC.glob("assets/js/vendor/*.js"), None)
    if vendor:      # vendor scripts are copied untouched
        assert (dest / vendor.relative_to(PUBLIC)).read_bytes() == vendor.read_bytes()


def test_the_leftover_check_does_catch_unprefixed_urls(tmp_path):
    """The check must fail an untransformed copy — otherwise the test above proves nothing."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "index.html").write_text((PUBLIC / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    (raw / "x.html").write_text('<div data-anything="/assets/a.jpg"></div><p style="background:url(/b.png)">'
                                '<link rel="icon" href="/favicon.png">', encoding="utf-8")
    left = prefix.leftovers(raw, "/layers")
    assert any(x.startswith("index.html: /assets/") for x in left)
    assert {"x.html: /assets/a.jpg", "x.html: /b.png", "x.html: /favicon.png"} <= set(left)


class _Refs(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if not v:
                continue
            if k in ("srcset", "imagesrcset"):
                self.urls.update(c.strip().split(" ")[0] for c in v.split(","))
            elif k in ("href", "src", "poster", "action", "data-src-narrow") or k.startswith("data-src"):
                self.urls.add(v)


def _resolve(dest, url):
    """The file GitHub Pages would serve for a /layers/… URL (directories
    serve index.html, like the clean URLs on the live site)."""
    path = urllib.parse.urlparse(url).path
    assert path.startswith("/layers/") or path == "/layers", url
    rel = path[len("/layers"):].lstrip("/")
    f = dest / rel
    return f if f.is_file() else f / "index.html"


def broken_by_prefix(dest, public):
    """Local links and images that resolve on the site itself (`public`, no
    base path) but not in the prefixed copy (`dest`, under /layers/)."""
    missing = []
    for page in dest.rglob("*.html"):
        refs = _Refs()
        refs.feed(page.read_text(encoding="utf-8"))
        for url in refs.urls:
            if not url.startswith("/") or url.startswith("//"):
                continue
            if url.startswith("/layers/api/"):      # Pages Functions: Cloudflare only, by design
                continue
            plain = public / urllib.parse.urlparse(url).path[len("/layers"):].lstrip("/")
            plain = plain if plain.is_file() else plain / "index.html"
            if not _resolve(dest, url).is_file() and plain.is_file():
                missing.append(f"{page.relative_to(dest)} → {url}")
    return missing


def test_every_local_link_and_image_resolves_under_the_base_path(staged):
    """Everything that resolves on the site itself resolves under /layers/.
    A link the manager typed to a page that doesn't exist ("/vist") is broken
    on both — the build warns about it — so it isn't this test's business:
    the prefix must never break a link, and that is all it judges."""
    dest, _ = staged
    assert broken_by_prefix(dest, PUBLIC) == []


def test_a_broken_link_in_content_is_not_blamed_on_the_prefix(tmp_path):
    site = tmp_path / "public"
    (site / "menu").mkdir(parents=True)
    (site / "index.html").write_text('<a href="/menu">ok</a><a href="/vist">typo</a><img src="/a.png">')
    (site / "menu" / "index.html").write_text("<p>menu</p>")
    (site / "a.png").write_bytes(b"png")
    dest = tmp_path / "pages" / "layers"
    prefix.prefix_tree(site, dest, "/layers")
    assert broken_by_prefix(dest, site) == []                       # the typo is the content's, not the prefix's
    (dest / "a.png").unlink()                                       # a file the prefixed copy lost
    assert broken_by_prefix(dest, site) == ["index.html → /layers/a.png"]


def test_css_urls_resolve(staged):
    dest, _ = staged
    for css in dest.rglob("*.css"):
        for url in re.findall(r'url\(["\']?(/[^)"\']+)', css.read_text(encoding="utf-8")):
            if not url.startswith("//"):
                assert _resolve(dest, url.split("#")[0].split("?")[0]).is_file(), url


def test_missing_build_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        prefix.prefix_tree(tmp_path / "nothing", tmp_path / "out")


def test_cli(tmp_path, capsys):
    prefix.main([str(PUBLIC), str(tmp_path / "site"), "--prefix", "/layers"])
    assert "base path /layers" in capsys.readouterr().out
    assert 'href="/layers/menu"' in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_deploy_script_uses_the_shared_transform():
    src = (ROOT / "tools" / "deploy-github-preview.py").read_text(encoding="utf-8")
    assert "from ci import prefix" in src and "def prefix_html" not in src
    # it must never overwrite the source repo with built files
    assert 'tools" / "build.py' in src
