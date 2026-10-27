#!/usr/bin/env python3
"""
Saves what the daily menu refresh fetched from Square — only when the menu
the site shows actually changed.

tools/sync-menu-from-store.py rewrites the cached Square snapshot
(data/square-store-products.json) on every run, and that raw snapshot changes
most days on its own (stock badges, Square's indexing dates) without changing
anything on the site. So a refresh is committed only when one of these
changed:

  data/menu-fallback.json   the menu the site renders (names, prices, …)
  content/menu.json         items Square added, appended for the manager
  src-img/menu/             a new or changed Square product photo

and then together with the snapshot and the copy served at
/assets/data/menu-fallback.json. Otherwise the snapshot is put back and
nothing is committed.

  python3 tools/ci/menu.py commit
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ci import common  # noqa: E402

SIGNIFICANT = ("data/menu-fallback.json", "content/menu.json", "src-img/menu")
ALONGSIDE = ("data/square-store-products.json", "public/assets/data/menu-fallback.json")


def changed(paths, cwd=None):
    """Changed or new files under `paths` (git status, untracked included)."""
    out = common.git("status", "--porcelain", "--untracked-files=all", "--", *paths, cwd=cwd).stdout
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


def commit(cwd=None):
    sig = changed(SIGNIFICANT, cwd)
    if not sig:
        root = pathlib.Path(cwd) if cwd else common.ROOT
        present = [p for p in ALONGSIDE if (root / p).exists()]
        if present:      # put the day's raw snapshot back: it changes nothing on the site
            common.git("checkout", "--", *present, cwd=cwd, check=False)
        common.summary("### Menu unchanged\n\nSquare's menu matches the site; nothing to save.")
        common.set_output("changed", "false")
        return None
    listed = "\n".join(f"- {p}" for p in sig[:20])
    msg = ("Refresh menu from Square\n\n"
           f"The public Square store changed what the site's menu shows:\n{listed}\n\n"
           "Layers-Change: menu-refresh\n")
    try:
        sha = common.commit_and_push([*SIGNIFICANT, *ALONGSIDE], msg, cwd=cwd)
    except common.PushConflict:
        common.fail("### The menu refresh wasn't saved\n\nThe menu was edited in Pages CMS while Square was "
                    "being checked. Nothing was saved; the next refresh (tomorrow morning, or "
                    "**Refresh menu from Square**) will try again.", title="Menu not saved")
    common.summary("### Menu refreshed from Square\n\n" + listed + "\n\nThe site is being republished now.")
    common.set_output("changed", "true")
    common.set_output("sha", sha)
    return sha


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["commit"]:
        sys.exit("usage: menu.py commit")
    commit()


if __name__ == "__main__":
    common.guarded(main)
