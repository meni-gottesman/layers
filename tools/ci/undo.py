#!/usr/bin/env python3
"""
"Undo my last change": revert the manager's most recent change to the
site's content or photos.

What is the manager's: content/ and the PHOTOS under src-img/ (the image
types the CMS media library handles). The other files in src-img/ —
slot-specs.json (the tuned crops), existing-photos.json, PROVENANCE.json and
the photo manifests — are developer files the CMS can't edit: a commit that
touches them is code, so Undo never reverses the developer's crop tuning.

Which commit is "the last change" (choose(), a pure function, tested in
tests/test_ci_undo.py) — walking main from the newest commit back:

  * Undo commits are skipped, and so is each commit an undo already reverted
    (trailer "Layers-Undo-Of: <sha>"), so pressing Undo again goes one step
    further back instead of re-doing what was just undone.
  * The daily menu refresh ("Layers-Change: menu-refresh") is skipped: it's
    the website bot's change, not the manager's, and the next refresh would
    bring it back anyway.
  * Commits that don't touch content/ or a photo under src-img/ (code,
    tooling, crop specs, a backup heartbeat) are skipped.
  * The first commit left is the one undone — only if it changes nothing
    but content/, photos under src-img/ and data/, and isn't a merge.
    Otherwise Undo refuses and says why: a change that also touched the
    site's code is the developer's to undo. Restores ("Restore from backup
    …") can be undone.

  python3 tools/ci/undo.py prepare                  # choose + `git revert --no-commit`
  python3 tools/ci/undo.py commit --target SHA      # commit + push the revert

Between the two, the workflow checks the reverted content with
`python3 tools/build.py --check`, so an undo can't leave content that fails
to build.
"""
import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ci import common  # noqa: E402

# The photo types under src-img/ that are the manager's (the CMS media library
# takes jpg/jpeg/png/webp; HEIC files arrive by hand or from a restore).
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
LOOK_BACK = 400                                  # commits searched for the last change


def is_content(path):
    """content/…, or a photo under src-img/ — what counts as a content change."""
    return path.startswith("content/") or (path.startswith("src-img/") and path.lower().endswith(PHOTO_TYPES))


def is_allowed(path):
    """All an undoable commit may touch: content, photos, and data/ (the menu
    data a restore brings back)."""
    return is_content(path) or path.startswith("data/")
_TRAILER = re.compile(r"^(Layers-[A-Za-z-]+):\s*(\S.*?)\s*$", re.M)


def trailers(message):
    """{"Layers-Change": [...], "Layers-Undo-Of": [...]} from a commit message."""
    out = {}
    for k, v in _TRAILER.findall(message or ""):
        out.setdefault(k, []).append(v)
    return out


def choose(commits):
    """Pick the commit to undo.

    commits: newest first, each {"sha", "parents": [...], "message", "paths": [...]}
    (paths listed without rename detection, so a rename shows both names).
    Returns ("undo", commit) or ("refuse", markdown explaining why)."""
    undone = set()
    for c in commits:
        tr = trailers(c.get("message", ""))
        kinds = tr.get("Layers-Change", [])
        if "undo" in kinds or tr.get("Layers-Undo-Of"):
            undone.update(tr.get("Layers-Undo-Of", []))
            continue
        if c["sha"] in undone or "menu-refresh" in kinds:
            continue
        paths = c.get("paths", [])
        if not any(is_content(p) for p in paths):
            continue
        subject = (c.get("message") or "").splitlines()[0] if c.get("message") else c["sha"][:7]
        if len(c.get("parents", [])) != 1:
            return "refuse", ("### This change can't be undone automatically\n\n"
                              f"The most recent change (“{subject}”) "
                              + ("is the first one in the site's history." if not c.get("parents") else
                                 "combined several changes at once (a merge).")
                              + " Ask the developer. Nothing was changed.")
        outside = sorted(p for p in paths if not is_allowed(p))
        if outside:
            listed = ", ".join(f"`{p}`" for p in outside[:5]) + (" …" if len(outside) > 5 else "")
            return "refuse", ("### This change can't be undone from the CMS\n\n"
                              f"The most recent change to the content (“{subject}”) also changed the "
                              f"website's code ({listed}), so it's the developer's to undo. "
                              "Nothing was changed.")
        return "undo", c
    return "refuse", ("### Nothing to undo\n\nNo recent change to the site's content or photos was found. "
                      "Nothing was changed.")


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
def history(limit=LOOK_BACK, cwd=None):
    """Commits on the current branch, newest first, in choose()'s shape."""
    out = common.git("log", "--first-parent", "--no-renames", f"-n{limit}",
                     "--format=%x1e%H%x1f%P%x1f%B%x1f", "--name-only", cwd=cwd).stdout
    commits = []
    for rec in out.split("\x1e")[1:]:
        sha, parents, message, names = (rec.split("\x1f") + ["", "", "", ""])[:4]
        commits.append({"sha": sha.strip(), "parents": parents.split(),
                        "message": message.strip(), "paths": [n for n in names.split("\n") if n.strip()]})
    return commits


def cmd_prepare(args):
    verdict, c = choose(history(cwd=args.cwd))
    if verdict == "refuse":
        common.fail(c, title="Nothing undone")
    subject = c["message"].splitlines()[0] if c["message"] else c["sha"][:7]
    reverted = common.git("revert", "--no-commit", c["sha"], cwd=args.cwd, check=False)
    if reverted.returncode != 0:
        common.git("revert", "--abort", cwd=args.cwd, check=False)
        common.fail("### This change can't be undone automatically\n\n"
                    f"A later change edited the same file as “{subject}”, so undoing it would overwrite "
                    "newer work. Change it back by hand in Pages CMS, or ask the developer. "
                    "Nothing was changed.", title="Nothing undone")
    common.set_output("target", c["sha"])
    print(f"undoing {c['sha'][:7]} — {subject}")


def cmd_commit(args):
    target = args.target
    if not re.fullmatch(r"[0-9a-f]{40}", target):
        sys.exit(f"error: not a commit sha: {target!r}")
    subject = common.git("log", "-1", "--format=%s", target, cwd=args.cwd).stdout.strip()
    t = dt.datetime.fromtimestamp(int(common.git("log", "-1", "--format=%ct", target, cwd=args.cwd).stdout),
                                  common.SHOP_TZ)
    when = f"{t:%b} {t.day}, {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"
    msg = (f"Undo: {subject}\n\nThis reverts commit {target}.\n\n"
           f"Layers-Change: undo\nLayers-Undo-Of: {target}\n")
    try:
        # the revert only changed what the reverted commit changed (prepare
        # checked that is content, photos and data)
        sha = common.commit_and_push(["content", "src-img", "data"], msg, cwd=args.cwd)
    except common.PushConflict:
        common.fail("### Someone saved a change during the undo\n\nA change to the same file was saved in "
                    "Pages CMS while the undo was running, so nothing was undone. Try **Undo my last "
                    "change** again.", title="Nothing undone")
    if sha is None:
        common.summary(f"### Nothing to undo\n\n“{subject}” had already been reversed.")
        common.set_output("changed", "false")
        return
    common.summary(f"### Undone: {subject}\n\nThe change from {when} (Berkeley time) was reversed. The site "
                   "is being republished now. Pressing **Undo my last change** again undoes the change "
                   "before it.")
    common.set_output("changed", "true")
    common.set_output("sha", sha)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Undo the most recent content change.")
    ap.add_argument("--cwd", default=None, help="repository (default: this one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    p = sub.add_parser("commit")
    p.add_argument("--target", required=True)
    args = ap.parse_args(argv)
    {"prepare": cmd_prepare, "commit": cmd_commit}[args.cmd](args)


if __name__ == "__main__":
    common.guarded(main)
