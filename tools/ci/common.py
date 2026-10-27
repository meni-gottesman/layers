"""
Shared helpers for the CI scripts in tools/ci/: GitHub Actions step outputs,
the run summary page, annotations, and the git / gh calls the workflows make.

Everything here works outside Actions too (the dry runs in docs/SETUP.md):
without $GITHUB_OUTPUT / $GITHUB_STEP_SUMMARY, outputs and summaries are
printed instead.
"""
import base64
import datetime as dt
import os
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SHOP_TZ = ZoneInfo("America/Los_Angeles")   # backups are named in Berkeley time
MAIN = "refs/heads/main"

# Commits the workflows make. The address is GitHub's own no-reply address for
# the Actions bot, so the commit shows the Actions avatar; the name says whose
# change it is in the CMS history ("Layers website bot").
BOT_NAME = "Layers website bot"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def shop_now():
    return dt.datetime.now(SHOP_TZ)


# ---------------------------------------------------------------------------
# GitHub Actions plumbing
# ---------------------------------------------------------------------------
def set_output(name, value):
    """A step output (`steps.<id>.outputs.<name>`). Values are single-line by
    construction: a newline could smuggle a second output in."""
    value = str(value)
    if "\n" in value or "\r" in value:
        raise ValueError(f"output {name} must be one line")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"[output] {name}={value}")


def summary(markdown):
    """Append Markdown to the run's summary page (what a person sees first
    when they open the run on GitHub)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown.rstrip() + "\n\n")
    else:
        print(markdown.rstrip() + "\n")


def _annotation_text(s):
    # Workflow-command escaping, so a message can't end the command early.
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(level, message, title=""):
    """::error / ::warning / ::notice — shown on the run page and in the
    workflow's list of problems."""
    t = f" title={_annotation_text(title).replace(',', '%2C').replace(':', '%3A')}" if title else ""
    print(f"::{level}{t}::{_annotation_text(message)}", flush=True)


def fail(markdown, title="Stopped"):
    """Stop the step with a friendly explanation on the summary page."""
    summary(markdown)
    first = next((ln.strip("# ").strip() for ln in markdown.splitlines() if ln.strip()), title)
    annotate("error", first, title=title)
    sys.exit(1)


def run_url():
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo, run_id = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else ""


def repo():
    r = os.environ.get("GITHUB_REPOSITORY", "")
    if not r:
        sys.exit("error: GITHUB_REPOSITORY is not set (owner/repo)")
    return r


# ---------------------------------------------------------------------------
# git and gh
# ---------------------------------------------------------------------------
def run(cmd, cwd=None, check=True, input=None):
    """Run a command, capture its output (text). Raises CalledProcessError
    with the output attached when check=True and it fails."""
    p = subprocess.run(cmd, cwd=cwd or ROOT, input=input, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, p.stdout, p.stderr)
    return p


def git(*args, cwd=None, check=True):
    return run(["git", *args], cwd=cwd, check=check)


def gh(*args, check=True, input=None):
    return run(["gh", *args], check=check, input=input)


def git_auth():
    """`-c http.<server>/.extraheader=…` for ONE git command that talks to
    GitHub (push, fetch), from $GIT_PUSH_TOKEN. The workflows check out with
    persist-credentials: false and set GIT_PUSH_TOKEN only on the step that
    saves, so the steps before it — installing packages, running the Square
    sync, decoding downloaded photos — never run with a write token in git's
    config. Without the variable (a laptop, a dry run) git uses its own
    credentials."""
    token = os.environ.get("GIT_PUSH_TOKEN", "")
    if not token:
        return []
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.{server}/.extraheader=AUTHORIZATION: basic {basic}"]


def guarded(main):
    """Run a script's main(). A git or gh command that fails becomes a short,
    readable failure on the run page — with the command's own message, for
    the developer — instead of a Python traceback."""
    try:
        return main()
    except subprocess.CalledProcessError as e:
        cmd = " ".join(str(x) for x in e.cmd[:3])
        detail = (e.stderr or e.stdout or "").strip().replace("```", "` ` `")[-1500:]
        fail("### A step couldn't finish\n\nA command the website's automation runs failed. This is for the "
             f"developer, not a content problem; the step stopped here.\n\n```\n$ {cmd} …\n{detail}\n```",
             title="Command failed")


class PushConflict(Exception):
    """Someone else changed the same files while this run was working."""


def commit_and_push(paths, message, cwd=None, branch="main", attempts=3):
    """Stage `paths`, commit as the website bot and push to `branch`.

    Returns the new commit's sha, or None when nothing changed. A push that
    loses a race with a Pages CMS save (non-fast-forward) is rebased onto the
    new tip and retried; if the rebase conflicts — the same file was edited in
    the meantime — PushConflict is raised and nothing is pushed."""
    cwd = cwd or ROOT
    git("add", "-A", "--", *paths, cwd=cwd)
    if git("diff", "--cached", "--quiet", cwd=cwd, check=False).returncode == 0:
        return None
    run(["git", "-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}", "commit", "-q", "-F", "-"],
        cwd=cwd, input=message)
    for attempt in range(attempts):
        if run(["git", *git_auth(), "push", "-q", "origin", f"HEAD:{branch}"], cwd=cwd, check=False).returncode == 0:
            return git("rev-parse", "HEAD", cwd=cwd).stdout.strip()
        run(["git", *git_auth(), "fetch", "-q", "origin", branch], cwd=cwd)
        rebased = run(["git", "-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}",
                       "rebase", "-q", f"origin/{branch}"], cwd=cwd, check=False)
        if rebased.returncode != 0:
            git("rebase", "--abort", cwd=cwd, check=False)
            raise PushConflict(rebased.stdout + rebased.stderr)
    raise PushConflict(f"the push to {branch} was rejected {attempts} times")
