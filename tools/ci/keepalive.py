#!/usr/bin/env python3
"""
Keeps the scheduled workflows running.

GitHub switches off scheduled workflows in a public repository after 60 days
with no activity in it. A café's content can go quiet for that long, and then
the daily build (announcement end dates, specials, holiday hours), the menu
refresh and the weekly backup would silently stop. Once a WEEK this:

  1. re-enables each scheduled workflow that GitHub switched off for
     inactivity (state "disabled_inactivity"; PUT /repos/{repo}/actions/
     workflows/{file}/enable — needs `actions: write`). A workflow someone
     switched off on purpose ("disabled_manually") is left off, with a note;
  2. if main has had no commit for 45 days, pushes an empty "heartbeat"
     commit as the website bot — a commit always counts as activity, and
     GitHub doesn't document whether re-enabling resets its clock. It
     changes no files, so Undo and the CMS history never see it.

Weekly, because the heartbeat must land before day 60 whatever the date of
the last commit: quiet for under 45 days at one run means at most 45 + 7 = 52
at the next. (A monthly run allowed up to 45 + 31 = 76 — by then GitHub has
switched off this workflow too, and nothing turns it back on.)
tests/test_ci_limits.py steps through the real schedule to prove the gap.

  python3 tools/ci/keepalive.py
"""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ci import common  # noqa: E402

SCHEDULED = ("build-deploy.yml", "menu-refresh.yml", "backup.yml", "keep-alive.yml")
HEARTBEAT_AFTER = dt.timedelta(days=45)


def needs_heartbeat(last_commit, now, after=HEARTBEAT_AFTER):
    """True when main has been quiet long enough to need a heartbeat commit."""
    return now - last_commit >= after


def main():
    repo = common.repo()
    for wf in SCHEDULED:
        r = common.gh("api", f"repos/{repo}/actions/workflows/{wf}", "--jq", ".state", check=False)
        state = (r.stdout or "").strip() if r.returncode == 0 else ""
        if state == "active":
            print(f"{wf}: active")
            continue
        if state == "disabled_manually":
            print(f"{wf}: switched off by hand — left off")
            common.annotate("notice", f"{wf} was switched off by hand, so it was left off. Switch it on in the "
                                      "Actions tab when it should run again.")
            continue
        r = common.gh("api", "-X", "PUT", f"repos/{repo}/actions/workflows/{wf}/enable", check=False)
        print(f"{wf} ({state or 'state unknown'}): " + ("enabled" if r.returncode == 0 else
                                                         f"not enabled ({(r.stderr or '').strip()[:200]})"))
        if r.returncode != 0:
            common.annotate("warning", f"Couldn't re-enable {wf}: {(r.stderr or '').strip()[:200]}")
    last = dt.datetime.fromisoformat(common.git("log", "-1", "--format=%cI").stdout.strip())
    now = dt.datetime.now(dt.timezone.utc)
    if not needs_heartbeat(last, now):
        print(f"last commit {last:%Y-%m-%d}: no heartbeat needed")
        return
    common.run(["git", "-c", f"user.name={common.BOT_NAME}", "-c", f"user.email={common.BOT_EMAIL}",
                "commit", "-q", "--allow-empty", "-F", "-"],
               input="Keep the scheduled website updates running\n\nNo files changed: GitHub pauses "
                     "scheduled workflows after 60 quiet days.\n\nLayers-Change: heartbeat\n")
    if common.run(["git", *common.git_auth(), "push", "-q", "origin", "HEAD:main"], check=False).returncode != 0:
        print("main moved while this ran — that is activity too; no heartbeat needed")
        return
    common.summary("### Heartbeat\n\nmain had been quiet for 45+ days, so an empty commit was pushed to keep "
                   "the daily build, menu refresh and backups scheduled.")


if __name__ == "__main__":
    common.guarded(main)
