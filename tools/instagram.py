"""
The homepage Instagram section: which posts it shows, decided at BUILD time.

  python3 tools/build.py                       # the "instagram" step (reuses a feed < 12 h old)
  python3 tools/build.py --refresh-instagram   # fetch the feed now (the daily scheduled build)
  python3 tools/build.py --offline             # no network: the last feed, or hand-picked posts

content/instagram.json (edited in the CMS) picks the mode:

  curated   the hand-picked posts in the file: a photo already in src-img/,
            the post's link and a description (alt text).
  auto      the latest posts from a Behold JSON feed (https://feeds.behold.so/<id>).

Behold's free plan counts EVERY request to the feed toward 1,200 views a month
and pauses the feed at the cap (CMS_SPEC §9). So visitors' browsers never call
it, and neither does every build: the build fetches it, downloads each post's
image from behold.pictures into src-img/instagram/ (not in git; CI keeps the
folder in its cache) and notes when (src-img/instagram/feed.json). The images
go through the normal photo pipeline as the slots instagram/1, instagram/2 …
and the page is static HTML.

How often the feed is requested (REUSE_FOR, KEEP_ON_ERROR):

  * the daily scheduled build passes --refresh-instagram: it always fetches;
  * any other build (a CMS save, Publish now, Undo …) reuses the last fetched
    feed and its downloaded photos while they're under 12 hours old, and
    fetches only after that — so a busy editing day costs at most one or two
    extra requests, never one per save (about 30–90 a month in all);
  * a feed that can't be fetched keeps the last good one for up to 3 days
    (the report says so), then falls back to the hand-picked posts;
  * a changed feed link or number of posts is always fetched fresh.

A fetch also has a total time limit (FETCH_DEADLINE): a slow or stalled feed
or image host can't hold the build until its CI time limit — it gives up and
falls back like any other feed problem.

Safety: the post link must be an instagram.com post/reel link and the image
must come from behold.pictures (also after redirects); each image must be a
real JPEG/PNG/WebP under 10 MB. Any problem — the feed unreachable, malformed,
or fewer than 3 usable posts — falls back to the hand-picked posts, and the
build report says why. If there are no posts at all, the section shows only
the "Follow @handle" link.

Writes data/instagram.json, which tools/build-home-media.py (the photo slots)
and tools/render.py (the section) read:

  {"source": "curated" | "behold", "posts": [{"slot": "instagram/1",
   "image": "src-img/…", "post_url": "https://www.instagram.com/p/…/", "alt": "…"}]}
"""
import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import content as content_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIN_POSTS = 3                 # fewer usable feed posts than this -> hand-picked posts
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_FEED_BYTES = 2 * 1024 * 1024
IG_HOSTS = {"instagram.com", "www.instagram.com"}
IMAGE_HOST = "behold.pictures"
SIZE_ORDER = ("large", "full", "medium", "small")   # large ≈ 1000 px: enough for a 960 px tile
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
UA = {"User-Agent": "Mozilla/5.0 (layers-site build)"}
REUSE_FOR = dt.timedelta(hours=12)      # a feed fetched this recently is reused, not fetched again
KEEP_ON_ERROR = dt.timedelta(days=3)    # the last good feed stands in this long when Behold can't be reached
FETCH_DEADLINE = 60                     # seconds for the whole fetch: the feed and every image
CACHE_NAME = "feed.json"                # in src-img/instagram/: what was fetched, when


class FeedError(Exception):
    """The feed can't be used; the message says why, in plain English."""


def data_file(root=ROOT):
    return pathlib.Path(root) / "data" / "instagram.json"


def download_dir(root=ROOT):
    return pathlib.Path(root) / "src-img" / "instagram"


def handle_of(content):
    return content["site"]["social"]["instagram_handle"].strip().lstrip("@")


def _host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _https_on(url, ok):
    return (isinstance(url, str) and url.startswith("https://") and ok(_host(url)))


def _behold_image(url):
    return _https_on(url, lambda h: h == IMAGE_HOST or h.endswith("." + IMAGE_HOST))


def _instagram_post(url):
    return (_https_on(url, lambda h: h in IG_HOSTS) and content_mod.INSTAGRAM_POST.fullmatch(url) is not None)


def fetch(url, limit, deadline=None):
    """GET url -> bytes (at most `limit`). Refuses a redirect to another kind
    of host: the final address must pass the same check as the first.
    deadline (time.monotonic()): read in pieces and give up once it passes —
    the socket timeout alone only limits each read, so a host trickling a
    byte at a time could otherwise take forever."""
    def left():
        return None if deadline is None else deadline - time.monotonic()
    if left() is not None and left() <= 0:
        raise FeedError("it took too long")
    req = urllib.request.Request(url, headers=UA)
    timeout = 20 if left() is None else max(1.0, min(20.0, left()))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = r.geturl()
        if _host(final) != _host(url) and not (_behold_image(url) and _behold_image(final)):
            raise FeedError(f"the address redirected to {_host(final) or 'another site'}")
        chunks, size = [], 0
        read = r.read1 if hasattr(r, "read1") else r.read     # read1: what has arrived, not a full block
        while size <= limit:
            chunk = read(min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if left() is not None and left() <= 0:
                raise FeedError("it took too long")
        body = b"".join(chunks)
    if len(body) > limit:
        raise FeedError("a file was larger than expected")
    return body


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
def curated_posts(content):
    """The hand-picked posts, in order, up to the chosen number."""
    ig = content["instagram"]
    out = []
    for p in ig["curated"]:
        image, link = content_mod.image_rel(p["image"]), p["post_url"].strip()
        if image and link:
            out.append({"image": image, "post_url": link, "alt": p["alt"].strip()})
    return _numbered(out[:ig["count"]])


def _numbered(posts):
    return [{"slot": f"instagram/{i + 1}", **p} for i, p in enumerate(posts)]


def _alt(post, handle):
    """altText, else the first line of the caption, else a plain description."""
    for text in (post.get("altText"), (post.get("prunedCaption") or post.get("caption") or "").strip().split("\n")[0]):
        if isinstance(text, str) and text.strip():
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 200:                       # keep it a description, not an essay
                text = text[:200].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"
            return text
    return f"Instagram post from @{handle}" if handle else "Instagram post"


def parse_feed(raw, handle):
    """Behold JSON -> [{"id", "post_url", "image_url", "alt"}] for every post
    that passes the link and image-host checks (others are skipped)."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise FeedError("the feed isn’t valid JSON") from None
    posts = data.get("posts") if isinstance(data, dict) else data
    if not isinstance(posts, list):
        raise FeedError("the feed has no list of posts")
    out = []
    for p in posts:
        if not isinstance(p, dict) or not _instagram_post(p.get("permalink")):
            continue
        sizes = p.get("sizes") if isinstance(p.get("sizes"), dict) else {}
        image = next((s.get("mediaUrl") for k in SIZE_ORDER for s in [sizes.get(k)]
                      if isinstance(s, dict) and _behold_image(s.get("mediaUrl"))), None)
        if not image:
            continue
        pid = re.sub(r"[^A-Za-z0-9_-]", "", str(p.get("id") or ""))[:40]
        pid = pid or hashlib.sha256(p["permalink"].encode()).hexdigest()[:16]
        out.append({"id": pid, "post_url": p["permalink"], "image_url": image, "alt": _alt(p, handle)})
    return out


def _save_image(body, dest_dir, pid):
    """Check the bytes are a real photo and store them; returns the repo path."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(body)) as im:
            fmt = im.format
            im.verify()
        with Image.open(io.BytesIO(body)) as im:
            w, h = im.size
    except Exception:
        raise FeedError("an image in the feed couldn’t be opened") from None
    if fmt not in FORMATS or min(w, h) < 200:
        raise FeedError("an image in the feed isn’t a usable photo")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{pid}.{FORMATS[fmt]}"
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(body)
    tmp.replace(dest)
    return dest


def feed_posts(content, root=ROOT, get=fetch, deadline=None):
    """The latest Behold posts, images downloaded. Raises FeedError.
    deadline: time.monotonic() by which the whole fetch must be done."""
    ig = content["instagram"]
    url = ig["behold_feed_url"].strip()
    if not content_mod.BEHOLD_FEED.fullmatch(url):
        raise FeedError("there’s no Behold feed link")
    deadline = time.monotonic() + FETCH_DEADLINE if deadline is None else deadline
    if get is fetch:
        get = lambda u, limit: fetch(u, limit, deadline)      # noqa: E731

    def in_time():
        if time.monotonic() > deadline:
            raise FeedError("it took too long")
    try:
        raw = get(url, MAX_FEED_BYTES)
    except FeedError:
        raise
    except Exception as e:                       # network: timeouts, DNS, HTTP errors
        raise FeedError(f"it couldn’t be reached ({type(e).__name__})") from None
    found = parse_feed(raw, handle_of(content))[:ig["count"]]
    if len(found) < min(MIN_POSTS, ig["count"]):
        raise FeedError(f"it had only {len(found)} usable post(s)")
    root = pathlib.Path(root)
    posts = []
    for p in found:
        in_time()
        try:
            body = get(p["image_url"], MAX_IMAGE_BYTES)
        except FeedError:
            raise
        except Exception as e:
            raise FeedError(f"a post’s image couldn’t be downloaded ({type(e).__name__})") from None
        dest = _save_image(body, download_dir(root), p["id"])
        posts.append({"image": str(dest.relative_to(root)).replace("\\", "/"), "post_url": p["post_url"],
                      "alt": p["alt"]})
    return _numbered(posts)


def _usable(doc, root):
    return (isinstance(doc, dict) and isinstance(doc.get("posts"), list)
            and all(isinstance(p, dict) and (pathlib.Path(root) / p.get("image", "")).is_file()
                    for p in doc["posts"]))


def cache_file(root=ROOT):
    return download_dir(root) / CACHE_NAME


def load_cache(content, root=ROOT):
    """The last fetched feed — {"fetched": datetime (UTC), "posts": [...]} —
    when it's for the same feed link and number of posts and every photo it
    downloaded is still here; else None."""
    ig = content["instagram"]
    try:
        c = json.loads(cache_file(root).read_text(encoding="utf-8"))
        fetched = dt.datetime.fromisoformat(c["fetched"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if fetched.tzinfo is None or c.get("feed") != ig["behold_feed_url"].strip() or c.get("count") != ig["count"]:
        return None
    if not (c.get("posts") and _usable(c, root)):
        return None
    return {"fetched": fetched, "posts": c["posts"]}


def save_cache(content, posts, now, root=ROOT):
    ig = content["instagram"]
    f = cache_file(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"fetched": now.isoformat(timespec="seconds"), "feed": ig["behold_feed_url"].strip(),
                             "count": ig["count"], "posts": posts}, indent=1, ensure_ascii=False) + "\n",
                 encoding="utf-8")


def _when(t):
    """'Tue 27 Oct, 6:07 AM' in Berkeley time, for the report."""
    import hours
    t = t.astimezone(hours.SHOP_TZ)
    return f"{t:%a} {t.day} {t:%b}, {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def resolve(content, root=ROOT, offline=False, get=fetch, refresh=False, now=None, info=None):
    """-> (doc, notes). doc is what data/instagram.json holds; notes are
    plain-English reasons the feed wasn't used (for the build report).
    refresh: fetch even if the last feed is recent (the daily build).
    info: a dict that gets "how" — fetched, reused, kept, curated, off."""
    root = pathlib.Path(root)
    info = {} if info is None else info
    ig = content["instagram"]
    if not ig["enabled"]:
        info["how"] = "off"
        return {"source": "off", "posts": []}, []
    curated = {"source": "curated", "posts": curated_posts(content)}
    info["how"] = "curated"
    if ig["mode"] != "auto" or not ig["behold_feed_url"].strip():
        return curated, []
    now = now or dt.datetime.now(dt.timezone.utc)
    cached = load_cache(content, root)
    if offline:     # no network: keep the last feed if its photos are still here
        if cached:
            info["how"] = "reused"
            return {"source": "behold", "posts": cached["posts"]}, []
        return curated, ["The Instagram feed wasn’t fetched (offline build), so the hand-picked posts are shown."]
    if cached and not refresh and now - cached["fetched"] < REUSE_FOR:
        info["how"] = f"reused (fetched {_when(cached['fetched'])})"
        return {"source": "behold", "posts": cached["posts"]}, []
    try:
        posts = feed_posts(content, root, get)
    except FeedError as e:
        if cached and now - cached["fetched"] < KEEP_ON_ERROR:
            info["how"] = "kept"
            return {"source": "behold", "posts": cached["posts"]}, [
                f"The Behold feed couldn’t be refreshed — {e} — so the posts fetched {_when(cached['fetched'])} "
                "are still shown. The site tries again on the next update."]
        return curated, [f"The Behold feed couldn’t be used today — {e} — so the hand-picked posts are shown. "
                         "The site tries again on the next update. If this keeps happening, check the feed in "
                         "Behold (and that the Instagram account is still connected there)."]
    save_cache(content, posts, now, root)
    keep = {pathlib.Path(p["image"]).name for p in posts} | {CACHE_NAME}
    for f in download_dir(root).glob("*"):       # photos of posts that left the feed
        if f.is_file() and f.name not in keep:
            f.unlink()
    info["how"] = "fetched"
    return {"source": "behold", "posts": posts}, []


def load_file(root=ROOT):
    try:
        return json.loads(data_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load(content, root=ROOT):
    """What the section shows: data/instagram.json as the last build step
    wrote it; without that file (a fresh checkout, tests), the hand-picked
    posts straight from the content — never the network."""
    doc = load_file(root)
    if isinstance(doc, dict) and isinstance(doc.get("posts"), list):
        return doc
    doc, _ = resolve(content, root, offline=True)
    return doc if doc["source"] != "behold" else {"source": "curated", "posts": curated_posts(content)}


def write(doc, root=ROOT):
    path = data_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def build(root=ROOT, offline=False, get=fetch, refresh=False, info=None):
    """The build step: resolve the posts and write data/instagram.json."""
    content = content_mod.load_all(root)
    doc, notes = resolve(content, root, offline=offline, get=get, refresh=refresh, info=info)
    write(doc, root)
    return doc, notes


if __name__ == "__main__":
    d, n = build(offline="--offline" in sys.argv, refresh="--refresh" in sys.argv)
    print(f"instagram: {len(d['posts'])} post(s) from {d['source']}")
    for line in n:
        print("  !", line)
