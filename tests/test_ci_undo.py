"""'Undo my last change' (tools/ci/undo.py): which commit is the manager's
last change, and the real git revert on a scratch repository."""
import pytest

from ci import undo
from test_ci_common import commit, gitenv, new_repo, second_clone, sh  # noqa: F401  (gitenv: fixture)


def c(sha, paths, message="Update (via Pages CMS)", parents=("p",)):
    return {"sha": sha, "parents": list(parents), "message": message, "paths": list(paths)}


# ---------------------------------------------------------------------------
# choose(): pure
# ---------------------------------------------------------------------------
def test_newest_content_change():
    v, got = undo.choose([c("c3", ["content/specials/phi.json"]), c("c2", ["content/site.json"])])
    assert v == "undo" and got["sha"] == "c3"


def test_photo_uploads_count():
    v, got = undo.choose([c("c2", ["src-img/uploads/bowl.jpg"]), c("c1", ["content/site.json"])])
    assert got["sha"] == "c2"


def test_code_and_data_only_commits_are_skipped():
    v, got = undo.choose([c("d1", ["tools/render.py", "templates/base.html"]), c("d2", ["data/menu-fallback.json"]),
                          c("d3", ["docs/SETUP.md"]), c("c1", ["content/hours.json"])])
    assert got["sha"] == "c1"


def test_the_menu_refresh_and_heartbeats_are_not_the_managers():
    v, got = undo.choose([
        c("m1", ["content/menu.json", "data/menu-fallback.json", "src-img/menu/sq-new.jpg"],
          "Refresh menu from Square\n\nLayers-Change: menu-refresh"),
        c("h1", [], "Keep the scheduled website updates running\n\nLayers-Change: heartbeat"),
        c("c1", ["content/menu.json"], "Update content/menu.json (via Pages CMS)")])
    assert got["sha"] == "c1"


def test_pressing_undo_again_goes_further_back():
    history = [c("u1", ["content/events/run.json"], "Undo: Create run\n\nLayers-Change: undo\nLayers-Undo-Of: c3"),
               c("c3", ["content/events/run.json"]), c("c2", ["content/site.json"]), c("c1", ["content/hours.json"])]
    assert undo.choose(history)[1]["sha"] == "c2"
    history.insert(0, c("u2", ["content/site.json"], "Undo: x\n\nLayers-Change: undo\nLayers-Undo-Of: c2"))
    assert undo.choose(history)[1]["sha"] == "c1"


def test_a_new_change_after_an_undo_is_undone_first():
    history = [c("c4", ["content/site.json"]),
               c("u1", ["content/hours.json"], "Undo: y\n\nLayers-Change: undo\nLayers-Undo-Of: c3"),
               c("c3", ["content/hours.json"])]
    assert undo.choose(history)[1]["sha"] == "c4"


def test_restores_can_be_undone():
    v, got = undo.choose([c("r1", ["content/site.json", "src-img/uploads/a.jpg", "data/menu-fallback.json"],
                            "Restore from backup backup-2026-11-01-0423\n\nLayers-Change: restore")])
    assert v == "undo" and got["sha"] == "r1"


def test_developer_files_in_src_img_are_code():
    """Only photos under src-img/ are the manager's: the crop specs and photo
    manifests are the developer's, so a re-tune is never what Undo reverses."""
    v, got = undo.choose([c("t1", ["src-img/slot-specs.json"], "Re-tune the hero crop"),
                          c("m1", ["src-img/media-manifest.json", "public/assets/img/home/hero-1440.jpg"]),
                          c("c1", ["content/pages/home.json"], "Update content/pages/home.json (via Pages CMS)")])
    assert v == "undo" and got["sha"] == "c1"
    v, why = undo.choose([c("x1", ["src-img/uploads/new.jpg", "src-img/existing-photos.json"])])
    assert v == "refuse" and "`src-img/existing-photos.json`" in why
    assert undo.is_content("src-img/uploads/IMG_1.JPG") and not undo.is_content("src-img/PROVENANCE.json")
    assert not undo.is_content("src-img/uploads/.gitkeep")


def test_a_change_that_also_touched_code_is_refused():
    v, why = undo.choose([c("x1", ["content/site.json", "tools/render.py", "README.md"]), c("c1", ["content/a.json"])])
    assert v == "refuse" and "`tools/render.py`" in why and "`README.md`" in why and "developer" in why


def test_merges_and_the_first_commit_are_refused():
    assert undo.choose([c("m", ["content/a.json"], parents=("p1", "p2"))])[0] == "refuse"
    assert undo.choose([c("r", ["content/a.json"], parents=())])[0] == "refuse"


def test_nothing_to_undo():
    v, why = undo.choose([c("d1", ["tools/build.py"])])
    assert v == "refuse" and "Nothing to undo" in why
    assert undo.choose([])[0] == "refuse"


def test_trailers():
    assert undo.trailers("Undo: x\n\nThis reverts commit a.\n\nLayers-Change: undo\nLayers-Undo-Of: abc\n") == \
        {"Layers-Change": ["undo"], "Layers-Undo-Of": ["abc"]}


# ---------------------------------------------------------------------------
# On a real repository (a bare origin standing in for GitHub)
# ---------------------------------------------------------------------------
def run_undo(work, tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    undo.main(["--cwd", str(work), "prepare"])
    target = dict(ln.split("=", 1) for ln in out.read_text().splitlines())["target"]
    out.write_text("")
    undo.main(["--cwd", str(work), "commit", "--target", target])
    return target, dict(ln.split("=", 1) for ln in out.read_text().splitlines())


def test_undo_twice_on_a_real_repo(gitenv, monkeypatch):
    origin, work = new_repo(gitenv)
    c1 = commit(work, "Update content/site.json (via Pages CMS)", {"content/site.json": '{"name": "v2"}'})
    commit(work, "Create src-img/uploads/b.jpg (via Pages CMS)", {"src-img/uploads/b.jpg": "jpeg-b"})
    commit(work, "Update the renderer", {"tools/build.py": "# v2\n"})
    commit(work, "Refresh menu from Square\n\nLayers-Change: menu-refresh", {"data/menu.json": '{"m": 2}'})
    sh(work, "push", "-q", "origin", "HEAD:main")

    target, out = run_undo(work, gitenv, monkeypatch)                  # 1st: the photo upload
    assert out["changed"] == "true" and out["sha"] == sh(origin, "rev-parse", "main").strip()
    assert not (work / "src-img/uploads/b.jpg").exists()
    msg = sh(work, "log", "-1", "--format=%B")
    assert msg.startswith("Undo: Create src-img/uploads/b.jpg (via Pages CMS)")
    assert f"Layers-Undo-Of: {target}" in msg and "Requested-by" not in msg       # no names in public history
    assert (work / "tools/build.py").read_text() == "# v2\n"            # code untouched
    assert (work / "data/menu.json").read_text() == '{"m": 2}'         # the bot's menu refresh untouched

    target2, out = run_undo(work, gitenv, monkeypatch)                 # 2nd: one further back
    assert target2 == c1 and (work / "content/site.json").read_text() == '{"name": "Layers"}'
    assert "Undone: Update content/site.json" in (gitenv / "summary.md").read_text()


def test_undo_refuses_a_conflicting_revert(gitenv, monkeypatch):
    origin, work = new_repo(gitenv)
    commit(work, "Update content/site.json (via Pages CMS)", {"content/site.json": '{"name": "v2"}'})
    commit(work, "Dev tweak\n\nLayers-Change: menu-refresh", {"content/site.json": '{"name": "v3"}'})
    sh(work, "push", "-q", "origin", "HEAD:main")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(gitenv / "summary.md"))
    with pytest.raises(SystemExit):
        undo.main(["--cwd", str(work), "prepare"])
    assert "A later change edited the same file" in (gitenv / "summary.md").read_text()
    assert sh(work, "status", "--porcelain") == ""                     # revert aborted cleanly


def test_undo_racing_a_cms_save(gitenv, monkeypatch):
    origin, work = new_repo(gitenv)
    commit(work, "Create src-img/uploads/b.jpg (via Pages CMS)", {"src-img/uploads/b.jpg": "jpeg-b"})
    sh(work, "push", "-q", "origin", "HEAD:main")
    other = second_clone(gitenv, origin)                               # a CMS save lands mid-undo
    commit(other, "Update content/hours.json (via Pages CMS)", {"content/hours.json": "{}"})
    sh(other, "push", "-q", "origin", "HEAD:main")
    target, out = run_undo(work, gitenv, monkeypatch)
    assert out["changed"] == "true"
    assert sh(origin, "log", "--format=%s", "-2", "main").splitlines() == [
        "Undo: Create src-img/uploads/b.jpg (via Pages CMS)", "Update content/hours.json (via Pages CMS)"]


def test_history_parsing(gitenv):
    origin, work = new_repo(gitenv)
    commit(work, "Rename\n\nbody line", {"content/a.json": "{}", "content/site.json": None})
    h = undo.history(cwd=work)
    assert [x["message"].splitlines()[0] for x in h] == ["Rename", "First"]
    assert sorted(h[0]["paths"]) == ["content/a.json", "content/site.json"]
    assert len(h[0]["parents"]) == 1 and h[1]["parents"] == []
