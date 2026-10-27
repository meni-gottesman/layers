"""
Shared test setup. Tests import the build modules straight from tools/.

The tests check the site's CODE, never the manager's content: every test
that needs content reads a frozen copy of the seed content (the site as it
was handed over, Oct 27 2026) in tests/fixtures/seed/ —

  content/      the content files, exactly as they were
  data/         the menu data, album and Instagram data the build made from them
  src-img/*.json  the photo specs, the exempt-photo list and the photo manifests
  photos.json   the seed photos those files use, by git blob id

— never content/ itself. So anything the manager does in the CMS (new
opening hours, an uploaded photo on the homepage, a special switched off,
an event, the announcement bar, deleting an old photo from the media
library) can't fail a test and stop the site from publishing; the build's
own checks are what judge her content.

Two ways in:

  seed_root()   a read-only site root made from the fixture, built once per
                test session in a temporary folder: content/data/specs copied
                from the fixture, templates/ and tools/ linked to the real
                code, and each seed photo linked from src-img/ — or, when the
                file there was deleted or replaced since, restored from git
                history (git cat-file, by its blob id), so it is always the
                seed's photo. Use it for anything that only reads.
  repo          (fixture) a throwaway copy of that site for one test, to edit.

When a developer change makes a seed assertion wrong (a new field, a re-tuned
crop), update the fixture on purpose: copy the changed file into
tests/fixtures/seed/ (and, for a new seed photo, add its blob id to
photos.json: `git ls-tree HEAD <path>`).

  pip install -r requirements.txt
  pytest -q
"""
import atexit
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

FIXTURE = ROOT / "tests" / "fixtures" / "seed"
TODAY = dt.date(2026, 10, 27)     # a fixed "today" so date windows are deterministic

PHOTO_DIRS = ("originals", "albums", "menu")
DATA_FILES = ("menu-fallback.json", "square-store-products.json", "albums.json", "instagram.json")
SPEC_FILES = ("slot-specs.json", "media-manifest.json", "album-manifest.json", "existing-photos.json")


def load_tool(path, name):
    """Import a hyphenated tools/ script from a given repo copy."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def blob_id(path):
    """The git blob id of a file's bytes (what `git hash-object` prints)."""
    data = pathlib.Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def seed_photos():
    """{repo path: git blob id} of every seed photo (tests/fixtures/seed/photos.json)."""
    return json.loads((FIXTURE / "photos.json").read_text())["photos"]


def _photo_from_git(blob, dest):
    """Write a seed photo out of git history. In CI the checkout is a partial
    clone (blob:none), so git fetches the one photo on demand."""
    with open(dest, "wb") as out:
        r = subprocess.run(["git", "cat-file", "blob", blob], cwd=ROOT, stdout=out, stderr=subprocess.PIPE)
    if r.returncode != 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"The seed photo {dest.name} ({blob}) isn't in src-img/ any more and couldn't be read "
                           f"from git history: {r.stderr.decode(errors='replace').strip()}")


_SEED = None


def seed_root():
    """The read-only seed site (see the module docstring), made on first use."""
    global _SEED
    if _SEED is not None:
        return _SEED
    base = pathlib.Path(tempfile.mkdtemp(prefix="layers-seed-"))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    r = base / "seed"
    shutil.copytree(FIXTURE / "content", r / "content")
    (r / "data").mkdir(parents=True)
    for f in DATA_FILES:
        shutil.copy(FIXTURE / "data" / f, r / "data" / f)
    (r / "src-img" / "uploads").mkdir(parents=True)
    for f in SPEC_FILES:
        shutil.copy(FIXTURE / "src-img" / f, r / "src-img" / f)
    for name in ("templates", "tools", ".pages.yml"):
        (r / name).symlink_to(ROOT / name)
    for rel, blob in seed_photos().items():
        dest = r / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        real = ROOT / rel
        if real.is_file() and blob_id(real) == blob:
            dest.symlink_to(real)
        else:
            _photo_from_git(blob, dest)
    _SEED = r
    return r


def seed_content(rel):
    """A seed content file, parsed: seed_content("hours.json")."""
    return json.loads((FIXTURE / "content" / rel).read_text())


@pytest.fixture
def repo(tmp_path):
    """A scratch copy of the seed site to edit: its content, data and photo
    specs copied, tools and templates copied from the real code, photo
    folders linked to the seed's photos (so validation sees real images)."""
    seed = seed_root()
    r = tmp_path / "repo"
    shutil.copytree(seed / "content", r / "content")
    for d in ("templates", "tools"):
        shutil.copytree(ROOT / d, r / d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(seed / "data", r / "data")
    (r / "src-img").mkdir()
    for f in SPEC_FILES:
        shutil.copy(seed / "src-img" / f, r / "src-img" / f)
    for d in PHOTO_DIRS:
        (r / "src-img" / d).symlink_to(seed / "src-img" / d)
    (r / "src-img" / "uploads").mkdir()
    (r / "public" / "assets" / "data").mkdir(parents=True)
    return r


def edit(repo, rel, fn):
    """Load content/<rel>, let fn change it in place, save it back."""
    p = repo / "content" / rel
    data = json.loads(p.read_text())
    fn(data)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return p
