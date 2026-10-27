"""The Instagram section's posts (tools/instagram.py, CMS_SPEC §2.6 + §9):
hand-picked posts, the Behold feed fetched at build time, and every way the
feed can fail falling back to the hand-picked posts. No network: the feed and
its images come from a stub."""
import datetime as dt
import io
import json

import pytest
from PIL import Image

import content as C
import instagram
from conftest import edit

FEED = "https://feeds.behold.so/AbC123xyz"


def jpeg(w=1080, h=1350, color=(200, 120, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


def post(n, **kw):
    p = {"id": f"1789{n}", "permalink": f"https://www.instagram.com/p/Post{n}x/", "mediaType": "IMAGE",
         "caption": f"Caption {n}\nsecond line #hashtag", "prunedCaption": f"Caption {n}\nsecond line",
         "sizes": {"small": {"mediaUrl": f"https://behold.pictures/a/b/{n}/small.jpg", "width": 300, "height": 375},
                   "large": {"mediaUrl": f"https://behold.pictures/a/b/{n}/large.jpg", "width": 1000, "height": 1250}}}
    p.update(kw)
    return p


class Stub:
    """A fake network: the feed JSON and an image for every behold.pictures URL."""

    def __init__(self, posts, fail=None):
        self.posts, self.fail, self.calls = posts, fail, []

    def __call__(self, url, limit):
        self.calls.append(url)
        if self.fail:
            raise self.fail
        if url.startswith("https://feeds.behold.so/"):
            return json.dumps({"username": "layerssuperfoodbar", "posts": self.posts}).encode()
        return jpeg()


def auto(repo, count=4):
    edit(repo, "instagram.json", lambda d: d.update(mode="auto", behold_feed_url=FEED, count=count))
    return C.load_all(repo)


def test_curated_posts_are_numbered_slots(repo):
    doc, notes = instagram.resolve(C.load_all(repo), repo, get=Stub([]))
    assert doc["source"] == "curated" and notes == []
    assert [p["slot"] for p in doc["posts"]] == ["instagram/1", "instagram/2", "instagram/3", "instagram/4"]
    assert doc["posts"][0] == {"slot": "instagram/1", "image": "src-img/albums/04-the-regulars/04.jpg",
                               "post_url": "https://www.instagram.com/p/DeFwOJmj8zc/",
                               "alt": "A woman in white headphones crouches at the Layers door beside a smiling "
                                      "tricolor dog"}


def test_curated_mode_never_touches_the_network(repo):
    stub = Stub([post(1)])
    edit(repo, "instagram.json", lambda d: d.update(behold_feed_url=FEED))     # a feed link, but mode curated
    instagram.resolve(C.load_all(repo), repo, get=stub)
    assert stub.calls == []


def test_count_limits_the_posts(repo):
    edit(repo, "instagram.json", lambda d: d.update(count=2))
    doc, _ = instagram.resolve(C.load_all(repo), repo)
    assert len(doc["posts"]) == 2


def test_feed_posts_are_downloaded_and_used(repo):
    stub = Stub([post(n) for n in range(1, 7)])
    doc, notes = instagram.resolve(auto(repo), repo, get=stub)
    assert doc["source"] == "behold" and notes == [] and len(doc["posts"]) == 4
    first = doc["posts"][0]
    assert first["post_url"] == "https://www.instagram.com/p/Post1x/" and first["alt"] == "Caption 1"
    assert first["image"] == "src-img/instagram/17891.jpg" and (repo / first["image"]).is_file()
    assert stub.calls[0] == FEED and stub.calls[1] == "https://behold.pictures/a/b/1/large.jpg"   # the large size
    assert len(stub.calls) == 1 + 4                                             # one feed request


def test_alt_text_prefers_the_posts_alt_text(repo):
    stub = Stub([post(1, altText="Two cups of Phi Velvet on the counter"), post(2, prunedCaption="", caption=""),
                 post(3)])
    doc, _ = instagram.resolve(auto(repo, count=3), repo, get=stub)
    assert [p["alt"] for p in doc["posts"]] == ["Two cups of Phi Velvet on the counter",
                                                "Instagram post from @layerssuperfoodbar", "Caption 3"]


def test_posts_from_other_hosts_are_skipped(repo):
    bad_link = post(1, permalink="https://evil.example/p/x/")
    bad_image = post(2, sizes={"large": {"mediaUrl": "https://evil.example/large.jpg"}})
    http_image = post(3, sizes={"large": {"mediaUrl": "http://behold.pictures/a/large.jpg"}})
    fake_host = post(4, sizes={"large": {"mediaUrl": "https://behold.pictures.evil.example/large.jpg"}})
    good = [post(n) for n in range(5, 8)]
    stub = Stub([bad_link, bad_image, http_image, fake_host] + good)
    doc, _ = instagram.resolve(auto(repo), repo, get=stub)
    assert doc["source"] == "behold"
    assert [p["post_url"] for p in doc["posts"]] == [f"https://www.instagram.com/p/Post{n}x/" for n in range(5, 8)]
    assert not any("evil" in u for u in stub.calls)


@pytest.mark.parametrize("posts, fail, why", [
    ([post(1), post(2)], None, "only 2 usable post"),
    ([], OSError("timed out"), "couldn’t be reached"),
    ("not json", None, "isn’t valid JSON"),
])
def test_feed_problems_fall_back_to_the_hand_picked_posts(repo, posts, fail, why):
    stub = Stub(posts, fail)
    if posts == "not json":
        stub = lambda url, limit: b"<html>oops</html>"          # noqa: E731
    doc, notes = instagram.resolve(auto(repo), repo, get=stub)
    assert doc["source"] == "curated" and len(doc["posts"]) == 4
    assert len(notes) == 1 and why in notes[0] and "hand-picked posts are shown" in notes[0]


def test_a_broken_image_falls_back(repo):
    class Broken(Stub):
        def __call__(self, url, limit):
            return b"not an image" if "behold.pictures" in url else super().__call__(url, limit)
    doc, notes = instagram.resolve(auto(repo), repo, get=Broken([post(n) for n in range(1, 5)]))
    assert doc["source"] == "curated" and "couldn’t be opened" in notes[0]


def test_offline_keeps_the_last_feed_or_uses_the_hand_picked_posts(repo):
    content = auto(repo)
    doc, _ = instagram.resolve(content, repo, get=Stub([post(n) for n in range(1, 5)]))
    instagram.write(doc, repo)
    again, notes = instagram.resolve(content, repo, offline=True)
    assert again == doc and notes == []
    (repo / doc["posts"][0]["image"]).unlink()                   # a photo went missing
    again, notes = instagram.resolve(content, repo, offline=True)
    assert again["source"] == "curated" and "offline" in notes[0]


def test_feed_photos_that_left_the_feed_are_tidied(repo):
    content = auto(repo, count=3)
    instagram.resolve(content, repo, get=Stub([post(n) for n in range(1, 4)]))
    instagram.resolve(content, repo, get=Stub([post(n) for n in range(4, 7)]), refresh=True)
    assert sorted(f.name for f in (repo / "src-img" / "instagram").iterdir()) == ["17894.jpg", "17895.jpg",
                                                                                  "17896.jpg", "feed.json"]


# ---------------------------------------------------------------------------
# How often Behold is asked (its free plan counts every feed request)
# ---------------------------------------------------------------------------
T0 = dt.datetime(2026, 10, 27, 13, 0, tzinfo=dt.timezone.utc)      # 6 AM in Berkeley


def feed_requests(stub):
    return sum(1 for u in stub.calls if u.startswith("https://feeds.behold.so/"))


def test_a_recent_feed_is_reused_without_asking_behold(repo):
    content = auto(repo)
    first = Stub([post(n) for n in range(1, 7)])
    doc, _ = instagram.resolve(content, repo, get=first, now=T0)
    assert feed_requests(first) == 1
    for hours_later in (1, 6, 11.9):                 # a busy day of CMS saves
        again = Stub([post(n) for n in range(7, 13)])
        info = {}
        same, notes = instagram.resolve(content, repo, get=again, now=T0 + dt.timedelta(hours=hours_later), info=info)
        assert same == doc and notes == [] and again.calls == [] and info["how"].startswith("reused")


def test_an_older_feed_is_fetched_again(repo):
    content = auto(repo)
    instagram.resolve(content, repo, get=Stub([post(n) for n in range(1, 7)]), now=T0)
    later = Stub([post(n) for n in range(7, 13)])
    doc, _ = instagram.resolve(content, repo, get=later, now=T0 + dt.timedelta(hours=12, minutes=1))
    assert feed_requests(later) == 1 and doc["posts"][0]["post_url"].endswith("/Post7x/")
    cache = json.loads((repo / "src-img" / "instagram" / "feed.json").read_text())
    assert cache["fetched"] == (T0 + dt.timedelta(hours=12, minutes=1)).isoformat(timespec="seconds")


def test_the_daily_build_always_fetches(repo):
    content = auto(repo)
    instagram.resolve(content, repo, get=Stub([post(n) for n in range(1, 7)]), now=T0)
    daily = Stub([post(n) for n in range(7, 13)])
    instagram.resolve(content, repo, get=daily, now=T0 + dt.timedelta(hours=1), refresh=True)
    assert feed_requests(daily) == 1


def test_a_day_of_saves_costs_at_most_a_few_requests(repo):
    """The daily 6 AM build, then a save every 30 minutes until midnight: no
    more than 3 feed requests that day (budget: 1,200 a month)."""
    content = auto(repo)
    stub = Stub([post(n) for n in range(1, 7)])
    instagram.resolve(content, repo, get=stub, now=T0, refresh=True)
    for k in range(1, 37):
        instagram.resolve(content, repo, get=stub, now=T0 + dt.timedelta(minutes=30 * k))
    assert feed_requests(stub) <= 3


def test_a_changed_feed_link_or_count_is_fetched_fresh(repo):
    content = auto(repo)
    instagram.resolve(content, repo, get=Stub([post(n) for n in range(1, 7)]), now=T0)
    stub = Stub([post(n) for n in range(1, 7)])
    instagram.resolve(auto(repo, count=6), repo, get=stub, now=T0 + dt.timedelta(minutes=5))
    assert feed_requests(stub) == 1


def test_behold_down_keeps_the_last_feed_for_three_days(repo):
    content = auto(repo)
    doc, _ = instagram.resolve(content, repo, get=Stub([post(n) for n in range(1, 7)]), now=T0)
    down = Stub([], OSError("timed out"))
    kept, notes = instagram.resolve(content, repo, get=down, now=T0 + dt.timedelta(days=2), refresh=True)
    assert kept == doc and "couldn’t be refreshed" in notes[0] and "still shown" in notes[0]
    old, notes = instagram.resolve(content, repo, get=down, now=T0 + dt.timedelta(days=3, hours=1), refresh=True)
    assert old["source"] == "curated" and "hand-picked posts are shown" in notes[0]


def test_a_stalled_host_gives_up_by_the_deadline(repo):
    """A host that sends a byte at a time can't hold the build: the whole
    fetch has one deadline, then the hand-picked posts are shown."""
    import time

    class Slow(Stub):
        def __call__(self, url, limit):
            self.calls.append(url)
            if url.startswith("https://feeds.behold.so/"):
                return json.dumps({"posts": self.posts}).encode()
            time.sleep(0.02)
            return jpeg()
    content = auto(repo)
    stub = Slow([post(n) for n in range(1, 7)])
    with pytest.raises(instagram.FeedError, match="too long"):
        instagram.feed_posts(content, repo, get=stub, deadline=time.monotonic() + 0.05)
    assert len(stub.calls) < 5


def test_fetch_reads_in_pieces_until_the_deadline(monkeypatch):
    """The real fetch: a response that trickles in stops at the deadline,
    not at the end of the file."""
    import time

    class Trickle:
        def __init__(self):
            self.n = 0

        def geturl(self):
            return "https://feeds.behold.so/AbC123xyz"

        def read1(self, size):
            self.n += 1
            time.sleep(0.01)
            return b"x"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    t = Trickle()
    monkeypatch.setattr(instagram.urllib.request, "urlopen", lambda req, timeout: t)
    with pytest.raises(instagram.FeedError, match="too long"):
        instagram.fetch(FEED, 1000, deadline=time.monotonic() + 0.1)
    assert t.n < 50


def test_switched_off_means_no_posts(repo):
    edit(repo, "instagram.json", lambda d: d.update(enabled=False))
    doc, _ = instagram.resolve(C.load_all(repo), repo)
    assert doc == {"source": "off", "posts": []}


def test_load_without_a_built_file_uses_the_content(repo):
    f = repo / "data" / "instagram.json"
    if f.exists():
        f.unlink()
    assert instagram.load(auto(repo), repo)["source"] == "curated"
