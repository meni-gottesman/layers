"""Backups and restores (tools/ci/backup.py): names, which backup a request
means, pruning (12 weekly + 6 "Back up now", counted apart), what goes in the
zip, and a restore that brings back content/, the photos in src-img/ and
data/ — never code, nor src-img/'s specs and manifests — from a sound zip only."""
import datetime as dt
import json
import zipfile

import pytest

from ci import backup
from test_ci_common import commit, gitenv, new_repo, sh, write  # noqa: F401  (gitenv: fixture)

TAGS = ["backup-2026-10-04-0423", "backup-2026-10-11-0423", "backup-2026-11-01-0423", "backup-2026-11-01-1530",
        "v1.0", "backup-latest", "backup-2026-13-01-0000"]


def test_names():
    assert backup.backup_name(dt.datetime(2026, 11, 1, 4, 23)) == "backup-2026-11-01-0423"
    assert backup.is_backup_tag("backup-2026-11-01-0423")
    for bad in ("backup-2026-11-01", "backup-2026-02-30-0423", "backup-2026-11-01-2500", "Backup-2026-11-01-0423",
                "backup-2026-11-01-0423x", "v1.0"):
        assert not backup.is_backup_tag(bad), bad
    assert backup.friendly_time("backup-2026-11-01-0423") == "Sunday 1 November 2026, 4:23 AM"
    assert backup.friendly_time("backup-2026-11-01-1530") == "Sunday 1 November 2026, 3:30 PM"
    assert backup.friendly_time("backup-2026-11-01-0005") == "Sunday 1 November 2026, 12:05 AM"


def test_resolve():
    assert backup.resolve("latest", TAGS) == "backup-2026-11-01-1530"
    assert backup.resolve("backup-2026-10-11-0423", TAGS) == "backup-2026-10-11-0423"
    assert backup.resolve("backup-2026-11-01", TAGS) == "backup-2026-11-01-1530"     # newest that day
    assert backup.resolve("backup-2026-10-12", TAGS) is None
    assert backup.resolve("backup-2026-10-11-0424", TAGS) is None
    assert backup.resolve("latest", ["v1.0"]) is None
    assert backup.resolve("v1.0", TAGS) is None                                       # never a non-backup


def test_prune_keeps_the_newest_twelve():
    tags = [f"backup-2026-{m:02d}-{d:02d}-0423" for m in (8, 9, 10) for d in (1, 8, 15, 22, 29)] + ["v1.0"]
    gone = backup.to_prune(tags)
    assert len(gone) == 3 and gone == ["backup-2026-08-01-0423", "backup-2026-08-08-0423", "backup-2026-08-15-0423"]
    assert "v1.0" not in gone
    assert backup.to_prune(tags[:12]) == []


def test_back_up_now_presses_never_push_out_the_weekly_history():
    """12 weekly backups, then a morning of 12 "Back up now" presses: the 12
    weekly ones all stay (and "latest" is the newest of all)."""
    weekly = [f"backup-2026-{m:02d}-{d:02d}-0423" for m, d in ((8, 2), (8, 9), (8, 16), (8, 23), (8, 30), (9, 6),
                                                              (9, 13), (9, 20), (9, 27), (10, 4), (10, 11), (10, 18))]
    manual = [f"backup-2026-10-21-10{n:02d}" for n in range(12)]
    gone = backup.to_prune(weekly + manual, weekly=set(weekly))
    assert gone == manual[:6] and not set(gone) & set(weekly)
    assert backup.resolve("latest", [t for t in weekly + manual if t not in gone]) == "backup-2026-10-21-1011"
    assert backup.to_prune(weekly + ["backup-2026-10-25-0423"], weekly=set(weekly) | {"backup-2026-10-25-0423"}) \
        == ["backup-2026-08-02-0423"]


def _info(name, mode=0o100644):
    i = zipfile.ZipInfo(name)
    i.external_attr = mode << 16
    return i


def test_safe_members():
    infos = [_info(n) for n in ("content/site.json", "src-img/uploads/a.jpg", "data/m.json", "public/index.html",
                                "templates/base.html", "BACKUP.json", "src-img/slot-specs.json",
                                "src-img/media-manifest.json", "src-img/uploads/.gitkeep", "src-img/menu/sq-x.PNG",
                                "content/")]
    infos[-1].external_attr = 0o040755 << 16
    ok, bad = backup.safe_members(infos)
    assert [i.filename for i in ok] == ["content/site.json", "src-img/uploads/a.jpg", "data/m.json",
                                        "src-img/menu/sq-x.PNG"] and bad == []
    for evil in ("../content/x", "content/../../etc/passwd", "/content/x", "content\\x", "C:/content/x",
                 "content//x"):
        assert backup.safe_members([_info(evil)])[1] == [evil], evil
    assert backup.safe_members([_info("content/link", 0o120777)])[1] == ["content/link"]   # symlink


# ---------------------------------------------------------------------------
# Make a zip and restore it, on a scratch repository
# ---------------------------------------------------------------------------
SITE = {"content/site.json": '{"name": "Layers"}', "content/specials/phi.json": '{"name": "Phi"}',
        "src-img/originals/a.jpg": "jpeg-a", "src-img/slot-specs.json": "{}", "data/menu-fallback.json": "{}",
        "src-img/media-manifest.json": '{"home/hero": "fp-a"}', "src-img/uploads/.gitkeep": "",
        "templates/base.html": "<html>", "public/index.html": "<h1>Layers</h1>", "tools/build.py": "# build\n",
        ".gitignore": "src-img/library/\nsrc-img/instagram/\n"}       # as in the real repo


@pytest.fixture
def site(gitenv):
    origin, work = new_repo(gitenv, SITE)
    write(work, {"src-img/library/raw.jpg": "not in git", "public/assets/img/x.webp": "built in CI"})
    return work


def test_zip_contents(site, gitenv, monkeypatch):
    monkeypatch.setattr(backup.common, "ROOT", site)
    write(site, {"src-img/slot-specs.json": '{"rebuilt": "by this run"}'})     # a build by-product on disk
    z = backup.make_zip(site, gitenv / "out", "backup-2026-11-01-0423", build_ok=False)
    assert z.name == "layers-backup-2026-11-01-0423.zip"
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        meta = json.loads(zf.read("BACKUP.json"))
        assert zf.getinfo("src-img/originals/a.jpg").compress_type == zipfile.ZIP_STORED     # photos aren't squeezed
        assert zf.read("src-img/slot-specs.json") == b"{}"           # the committed copy, not the working file
        assert zf.read("public/assets/img/x.webp") == b"built in CI"  # public/ as built
    assert names == {"BACKUP.json", "content/site.json", "content/specials/phi.json", "src-img/originals/a.jpg",
                     "src-img/slot-specs.json", "src-img/media-manifest.json", "src-img/uploads/.gitkeep",
                     "data/menu-fallback.json", "templates/base.html", "public/index.html",
                     "public/assets/img/x.webp"}          # no tools/, no untracked src-img/library/
    assert meta["name"] == "backup-2026-11-01-0423" and meta["build"].startswith("failed")
    assert meta["commit"] == sh(site, "rev-parse", "HEAD").strip()
    assert meta["files"] == {"content": 2, "src-img": 4, "data": 1, "templates": 1, "public": 2}


def test_restore_brings_back_content_photos_and_data_only(site, gitenv):
    z = backup.make_zip(site, gitenv / "out", "backup-2026-11-01-0423")
    write(site, {"content/site.json": '{"name": "Oops"}', "content/specials/phi.json": None,
                 "content/events/new.json": "{}", "src-img/uploads/new.jpg": "jpeg-new",
                 "src-img/originals/a.jpg": "jpeg-a-edited", "data/menu-fallback.json": '{"x": 1}',
                 "templates/base.html": "<html lang=en>", "tools/build.py": "# newer code\n",
                 "src-img/slot-specs.json": '{"retuned": 1}', "src-img/media-manifest.json": '{"home/hero": "fp-new"}'})
    commit(site, "later edits", {})
    r = backup.restore_into(z, site, "backup-2026-11-01-0423")
    assert r["written"] == 4        # 2 content + 1 photo + 1 data
    # today's developer files stay: with today's manifest the restored photo
    # no longer matches its fingerprint, so the build rebuilds it
    assert (site / "src-img/slot-specs.json").read_text() == '{"retuned": 1}'
    assert (site / "src-img/media-manifest.json").read_text() == '{"home/hero": "fp-new"}'
    assert (site / "src-img/uploads/.gitkeep").exists()
    for rel in ("content/site.json", "content/specials/phi.json", "src-img/originals/a.jpg", "data/menu-fallback.json"):
        assert (site / rel).read_text() == SITE[rel], rel
    assert not (site / "content/events/new.json").exists() and not (site / "src-img/uploads/new.jpg").exists()
    assert (site / "templates/base.html").read_text() == "<html lang=en>"        # never templates
    assert (site / "tools/build.py").read_text() == "# newer code\n"              # never code
    assert (site / "src-img/library/raw.jpg").exists()                            # files not in git are left alone
    status = sh(site, "status", "--porcelain").split("\n")
    assert all(ln[3:].startswith(("content/", "src-img/", "data/")) for ln in status if ln.strip())


def _evil_zip(path, name, extra):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("BACKUP.json", json.dumps({"name": name}))
        z.writestr("content/site.json", "{}")
        for n, data in extra.items():
            z.writestr(n, data)
    return path


@pytest.mark.parametrize("extra", [{"content/../tools/build.py": "pwned"}, {"/etc/x": "x"}, {"data\\..\\x": "x"}])
def test_unsafe_zips_are_refused_before_anything_changes(site, gitenv, extra):
    z = _evil_zip(gitenv / "evil.zip", "backup-2026-11-01-0423", extra)
    with pytest.raises(ValueError, match="unsafe"):
        backup.restore_into(z, site, "backup-2026-11-01-0423")
    assert sh(site, "status", "--porcelain", "--", "content", "src-img", "data") == ""


def test_wrong_or_empty_backups_are_refused(site, gitenv):
    z = backup.make_zip(site, gitenv / "out", "backup-2026-11-01-0423")
    with pytest.raises(ValueError, match="isn't the Layers backup"):
        backup.restore_into(z, site, "backup-2026-10-04-0423")
    with zipfile.ZipFile(gitenv / "empty.zip", "w") as zf:
        zf.writestr("BACKUP.json", json.dumps({"name": "backup-2026-11-01-0423"}))
    with pytest.raises(ValueError, match="no content"):
        backup.restore_into(gitenv / "empty.zip", site, "backup-2026-11-01-0423")
    assert (site / "content/site.json").exists()


def test_commit_restore(site, gitenv, monkeypatch):
    monkeypatch.setattr(backup.common, "ROOT", site)
    out = gitenv / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(gitenv / "summary.md"))
    z = backup.make_zip(site, gitenv / "zips", "backup-2026-11-01-0423")
    commit(site, "Update content/site.json (via Pages CMS)", {"content/site.json": '{"name": "Oops"}'})
    sh(site, "push", "-q", "origin", "HEAD:main")
    backup.main(["restore", "--zip", str(z)])
    backup.main(["commit", "--name", "backup-2026-11-01-0423"])
    assert "changed=true" in out.read_text()
    msg = sh(site, "log", "-1", "--format=%B")
    assert msg.startswith("Restore from backup backup-2026-11-01-0423\n")
    assert "Layers-Change: restore" in msg and "Requested-by" not in msg            # no names in public history
    assert sh(site, "show", "--name-only", "--format=", "HEAD").split() == ["content/site.json"]
    assert sh(gitenv / "origin.git", "rev-parse", "main") == sh(site, "rev-parse", "HEAD")
    backup.main(["commit", "--name", "backup-2026-11-01-0423"])           # again: nothing to restore
    assert out.read_text().strip().endswith("changed=false")
