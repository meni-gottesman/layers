"""
The site's tiny, safe text format for long-form content fields.

The manager writes plain text in the CMS. A handful of markers are understood;
everything else is shown exactly as typed. There is no way to inject HTML: the
input is escaped FIRST, and only then are the markers below turned into tags.

  blank line           -> new paragraph
  single line break    -> <br>
  **bold**             -> <strong>
  *italic* / _italic_  -> <em>
  [text](url)          -> a link, when url is https://…, mailto:…, tel:…, or a
                          site path starting with "/" or "#". Anything else
                          (javascript:, http://, //host, data:) shows as the
                          plain link text.

Links to other sites open in a new tab and carry a screen-reader hint, the
same pattern every hand-written external link on the site uses.

  block(text)   -> one <p> per paragraph (optionally with a class)
  inline(text)  -> the same markers, no paragraphs (for one-line fields)
"""
import html
import re

from markupsafe import Markup

DEFAULT_HINT = " (opens in a new tab)"

# [text](url) — text may not contain "]" or a line break; url has no spaces
# and may hold one level of balanced parentheses (…/Thing_(food)). Matched on
# ESCAPED text, so "&" in a URL arrives as "&amp;" (correct in an attribute)
# and a quote can never close the href early.
_LINK = re.compile(r"\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_STAR_EM = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")
# _x_ only at word edges, so snake_case words and file_names stay as typed.
_UNDER_EM = re.compile(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])")
_TOKEN = "\x00{}\x00"
_TOKEN_RE = re.compile("\x00(\\d+)\x00")


def _safe_url(url):
    """The (escaped) url if it is one we allow, else None."""
    u = html.unescape(url).strip()
    low = u.lower()
    if low.startswith(("https://", "mailto:", "tel:", "#")):
        return url
    # a site path, but never protocol-relative ("//host") or the "/\host" form
    # some browsers also treat as another site
    if u.startswith("/") and not u.startswith(("//", "/\\")):
        return url
    return None


def _emphasis(s):
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _STAR_EM.sub(r"<em>\1</em>", s)
    return _UNDER_EM.sub(r"<em>\1</em>", s)


def _format(escaped, hint_for):
    """Markers -> tags on already-escaped text (no paragraph handling)."""
    links = []

    def link(m):
        text, url = m.group(1), m.group(2)
        safe = _safe_url(url)
        if safe is None:
            out = _emphasis(text)
        elif html.unescape(safe).lower().startswith("https://"):
            hint = hint_for(html.unescape(safe)) if hint_for else DEFAULT_HINT
            out = (f'<a href="{safe}" target="_blank" rel="noopener">{_emphasis(text)}'
                   f'<span class="sr-only">{html.escape(hint)}</span></a>')
        else:
            out = f'<a href="{safe}">{_emphasis(text)}</a>'
        links.append(out)
        return _TOKEN.format(len(links) - 1)

    # Links first, so "*" or "_" inside a URL is never read as emphasis.
    s = _LINK.sub(link, escaped)
    s = _emphasis(s)
    return _TOKEN_RE.sub(lambda m: links[int(m.group(1))], s)


def _clean(text):
    # A NUL could collide with the link placeholders; it has no place in copy.
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def inline(text, hint_for=None):
    """One-line field: markers and line breaks, no paragraphs."""
    lines = [_format(html.escape(ln, quote=True), hint_for) for ln in _clean(text).strip().split("\n")]
    return Markup("<br>".join(lines))


def block(text, p_class=None, hint_for=None):
    """Long-form field: one <p> per paragraph (blank line), <br> for a line break."""
    cls = f' class="{html.escape(p_class, quote=True)}"' if p_class else ""
    paras = [p.strip() for p in re.split(r"\n[ \t]*\n+", _clean(text).strip()) if p.strip()]
    return Markup("\n".join(f"<p{cls}>{inline(p, hint_for)}</p>" for p in paras))


def plain(text):
    """The words a reader sees, with every marker removed (for length checks)."""
    s = _LINK.sub(lambda m: m.group(1), _clean(text))
    s = _BOLD.sub(r"\1", s)
    s = _STAR_EM.sub(r"\1", s)
    return _UNDER_EM.sub(r"\1", s)
