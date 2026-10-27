"""The daily menu refresh saves only real menu changes (tools/ci/menu.py):
Square's raw snapshot changes most days without changing the site."""
from ci import menu
from test_ci_common import gitenv, new_repo, sh, write  # noqa: F401  (gitenv: fixture)

FILES = {"data/menu-fallback.json": '{"price": "9.75"}', "data/square-store-products.json": '{"stock": 1}',
         "public/assets/data/menu-fallback.json": '{"price": "9.75"}', "content/menu.json": '{"items": []}',
         "src-img/menu/sq-a.jpg": "jpeg"}


def run(work, tmp, monkeypatch):
    out = tmp / "out.txt"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp / "summary.md"))
    menu.commit(cwd=work)
    return dict(ln.split("=", 1) for ln in out.read_text().splitlines())


def test_snapshot_only_changes_are_not_saved(gitenv, monkeypatch):
    origin, work = new_repo(gitenv, FILES)
    before = sh(origin, "rev-parse", "main")
    write(work, {"data/square-store-products.json": '{"stock": 0}'})
    assert run(work, gitenv, monkeypatch) == {"changed": "false"}
    assert sh(origin, "rev-parse", "main") == before
    assert sh(work, "status", "--porcelain") == ""                    # the snapshot was put back


def test_a_price_change_or_new_photo_is_saved(gitenv, monkeypatch):
    origin, work = new_repo(gitenv, FILES)
    write(work, {"data/menu-fallback.json": '{"price": "10.25"}', "public/assets/data/menu-fallback.json":
                 '{"price": "10.25"}', "data/square-store-products.json": '{"stock": 0}',
                 "src-img/menu/sq-new.jpg": "jpeg-new"})
    out = run(work, gitenv, monkeypatch)
    assert out["changed"] == "true" and out["sha"] == sh(origin, "rev-parse", "main").strip()
    msg = sh(work, "log", "-1", "--format=%B")
    assert msg.startswith("Refresh menu from Square") and "Layers-Change: menu-refresh" in msg
    assert sorted(sh(work, "show", "--name-only", "--format=", "HEAD").split()) == [
        "data/menu-fallback.json", "data/square-store-products.json", "public/assets/data/menu-fallback.json",
        "src-img/menu/sq-new.jpg"]
