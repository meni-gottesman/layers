"""Shared CI plumbing (tools/ci/common.py): step outputs, and the bot commit
that survives a race with a Pages CMS save. The git helpers here (a bare
"GitHub" origin plus a working clone, isolated from the developer's own git
config) are reused by the other test_ci_* files."""
import pathlib
import subprocess

import pytest

from ci import common


# ---------------------------------------------------------------------------
# Helpers shared with test_ci_backup.py, test_ci_undo.py, test_ci_menu.py
# ---------------------------------------------------------------------------
@pytest.fixture
def gitenv(tmp_path, monkeypatch):
    """Git with a throwaway identity and no global/system config (no commit
    signing, no hooks from the developer's machine), and no Actions files."""
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = Test Dev\n\temail = dev@example.com\n[init]\n\tdefaultBranch = main\n"
                   "[commit]\n\tgpgsign = false\n[advice]\n\tdetachedHead = false\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME",
              "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def sh(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def write(repo, files):
    """files: {relative path: text, or None to delete}."""
    for rel, text in files.items():
        p = pathlib.Path(repo) / rel
        if text is None:
            p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)


def commit(repo, message, files):
    write(repo, files)
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", message)
    return sh(repo, "rev-parse", "HEAD").strip()


def new_repo(root, files=None):
    """A bare origin ("GitHub") and a working clone with one commit on main."""
    root = pathlib.Path(root)
    origin, work = root / "origin.git", root / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    commit(work, "First", files or {"content/site.json": '{"name": "Layers"}', "tools/build.py": "# build\n",
                                    "src-img/originals/a.jpg": "jpeg-a", "data/menu.json": "{}"})
    sh(work, "push", "-q", "origin", "HEAD:main")
    return origin, work


def second_clone(root, origin):
    """Someone else's clone (Pages CMS saving at the same time)."""
    other = pathlib.Path(root) / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True, capture_output=True)
    return other


# ---------------------------------------------------------------------------
def test_set_output(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    common.set_output("changed", True)
    common.set_output("name", "backup-2026-11-01-0423")
    assert out.read_text() == "changed=True\nname=backup-2026-11-01-0423\n"
    with pytest.raises(ValueError):
        common.set_output("x", "a\nchanged=false")       # can't smuggle a second output in


def test_annotations_are_escaped(capsys):
    common.annotate("error", "line one\nline two 100%", title="a: b, c")
    assert capsys.readouterr().out == "::error title=a%3A b%2C c::line one%0Aline two 100%25\n"


def test_fail_writes_the_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "s"))
    with pytest.raises(SystemExit) as e:
        common.fail("### Nothing to undo\n\nDetails.")
    assert e.value.code == 1 and "### Nothing to undo" in (tmp_path / "s").read_text()


def test_commit_and_push_as_the_bot(gitenv):
    origin, work = new_repo(gitenv)
    write(work, {"content/site.json": '{"name": "Layers Superfood Bar"}', "tools/build.py": "# changed\n"})
    sha = common.commit_and_push(["content"], "Restore from backup x\n\nLayers-Change: restore\n", cwd=work)
    assert sha == sh(origin, "rev-parse", "main").strip()
    assert sh(work, "log", "-1", "--format=%an <%ae>|%s") == \
        f"{common.BOT_NAME} <{common.BOT_EMAIL}>|Restore from backup x\n"
    assert sh(work, "show", "--name-only", "--format=", "HEAD").split() == ["content/site.json"]   # only the paths given
    assert common.commit_and_push(["content"], "again", cwd=work) is None                         # nothing changed


def test_push_race_with_another_save_is_rebased(gitenv):
    origin, work = new_repo(gitenv)
    other = second_clone(gitenv, origin)
    commit(other, "Update content/hours.json (via Pages CMS)", {"content/hours.json": "{}"})
    sh(other, "push", "-q", "origin", "HEAD:main")
    write(work, {"data/menu.json": '{"new": 1}'})
    sha = common.commit_and_push(["data"], "Refresh menu from Square", cwd=work)
    log = sh(origin, "log", "--format=%s", "main").splitlines()
    assert log[:2] == ["Refresh menu from Square", "Update content/hours.json (via Pages CMS)"]
    assert sha == sh(origin, "rev-parse", "main").strip()


def test_push_race_on_the_same_file_stops(gitenv):
    origin, work = new_repo(gitenv)
    other = second_clone(gitenv, origin)
    commit(other, "Update content/site.json (via Pages CMS)", {"content/site.json": '{"name": "CMS"}'})
    sh(other, "push", "-q", "origin", "HEAD:main")
    before = sh(origin, "rev-parse", "main")
    write(work, {"content/site.json": '{"name": "Bot"}'})
    with pytest.raises(common.PushConflict):
        common.commit_and_push(["content"], "Restore from backup x", cwd=work)
    assert sh(origin, "rev-parse", "main") == before                                  # nothing pushed
    assert not (pathlib.Path(work) / ".git" / "rebase-merge").exists()               # rebase cleaned up
