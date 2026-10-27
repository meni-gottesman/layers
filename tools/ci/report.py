#!/usr/bin/env python3
"""
Tells people how a publish went, through ONE GitHub issue titled
"Website update didn't publish".

  * The build failed → the issue is opened (or, if one is already open,
    updated) with build-report.md — the plain-English list of what to fix —
    as its body. A comment is added only when the problem changed, so a
    failing daily build doesn't send the same email every morning.
  * The site built but the production upload failed → the same issue, with a
    short note that this is a setup problem for the developer.
  * Everything published → an open issue is closed with a comment.
  * A run that was cancelled because a newer change superseded it → nothing
    (the newer run reports). A run cancelled with NO newer run behind it hit
    its time limit — that is a problem, and opens the issue.
  * A request the build refused before building (Pages CMS open on another
    branch, a request that isn't from Pages CMS) → nothing: the refusal is on
    the run's page, and it isn't a problem with the site.

Only an issue the Actions bot opened is ever updated or closed — anyone can
open an issue with the same title in a public repository.

Production is Cloudflare Pages when it's set up, otherwise the GitHub Pages
preview. A preview failure while production published is left to the red
run (GitHub emails the developer) — the manager's update did go live.

  BUILD=success PAGES=success PAGES_PUBLISHED=true CLOUDFLARE=skipped \
      python3 tools/ci/report.py --report-dir build-report/

decide() is pure and tested in tests/test_ci_report.py.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ci import common  # noqa: E402

TITLE = "Website update didn't publish"
MAX_BODY = 60000            # GitHub's limit is 65,536 characters
BOT_LOGIN = "github-actions[bot]"
# The workflows whose runs publish (and share the build's concurrency group):
# a newer run of one of them is what cancels a build in progress.
PUBLISHING = (".github/workflows/build-deploy.yml", ".github/workflows/menu-refresh.yml",
              ".github/workflows/restore.yml", ".github/workflows/undo.yml")

CODE_PROBLEM = (
    "# Website update didn’t publish\n\n"
    "The live site has **not** changed. This time the problem is in the website’s code or setup, not your "
    "content — the developer has been told and will fix it. Your changes are saved and will go live with "
    "the next successful update.")


TIMED_OUT = (
    "# Website update didn’t publish\n\n"
    "The live site has **not** changed. The update ran out of time before it finished (a service it needs, "
    "such as the Instagram feed or the host, may have been very slow). This isn’t a problem with your content — "
    "the developer has been told. Your changes are saved and will go live with the next successful update.")


def _same_title(t):
    return (t or "").replace("’", "'").strip().lower() == TITLE.lower()


def upload_problem(target):
    host = {"cloudflare": "Cloudflare Pages (the live site)",
            "pages": "GitHub Pages (the site)"}[target]
    return (
        "# Website update didn’t publish\n\n"
        f"Your changes checked out and the site was built, but uploading it to {host} failed, so the live "
        "site has **not** changed. This is a setup or service problem, not your content — the developer "
        "has been told. Your changes are saved and will go live with the next successful update.\n\n"
        "<details><summary>For the developer</summary>\n\n"
        + ("Check the `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` secrets and the `CF_PAGES_PROJECT` "
           "variable (docs/SETUP.md), and Cloudflare's status page."
           if target == "cloudflare" else
           "Check Settings → Pages (Source: GitHub Actions) and the github-pages environment's branch rules "
           "(docs/SETUP.md).")
        + "\n\n</details>")


def decide(build, pages, pages_published, cloudflare, report=None, refused=False, superseded=True):
    """What to do with the issue after a run.

    build / pages / cloudflare: the jobs' results (success, failure,
    cancelled, skipped). pages_published: "true" when the Pages job really
    uploaded (it skips itself while Pages isn't switched to Actions).
    report: build-report.json as a dict, or None when the build never got to
    write one. refused: the request check turned the run down before building.
    superseded: for a cancelled run, whether a newer publishing run exists
    (False = the run hit its time limit). Returns (action, text):
    ("open", issue body), ("close", comment) or ("none", why)."""
    if refused:
        return "none", "The request was refused before anything was built (see the run's summary)."
    if "cancelled" in (build, pages, cloudflare):
        if superseded:
            return "none", "A newer change superseded this run; it will report instead."
        return "open", TIMED_OUT
    if build == "skipped":
        return "none", "Nothing was built."
    if build != "success":
        if report and report.get("status") == "failed" and report.get("_md"):
            return "open", report["_md"]
        return "open", CODE_PROBLEM
    production = "cloudflare" if cloudflare != "skipped" else "pages"
    result = cloudflare if production == "cloudflare" else pages
    if result != "success":
        return "open", upload_problem(production)
    if production == "pages" and pages_published != "true":
        return "none", ("The site built, but nothing is set up to publish it yet: GitHub Pages isn't "
                        "switched to GitHub Actions and Cloudflare isn't configured (docs/SETUP.md).")
    return "close", "This is fixed: the latest update published successfully."


def with_footer(body, url, sha):
    foot = "\n\n---\n<sub>" + " · ".join(x for x in (
        f"[Run details]({url})" if url else "", f"commit {sha[:7]}" if sha else "",
        "This issue updates itself and closes when the site publishes again.") if x) + "</sub>"
    if len(body) + len(foot) > MAX_BODY:
        body = body[:MAX_BODY - len(foot) - 40] + "\n\n…(cut short — see the run details)"
    return body + foot


# ---------------------------------------------------------------------------
# gh
# ---------------------------------------------------------------------------
def _api(method, path, data=None):
    args = ["api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
    if data is None:
        return json.loads(common.gh(*args).stdout or "null")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
    try:
        return json.loads(common.gh(*args, "--input", f.name).stdout or "null")
    finally:
        os.unlink(f.name)


def open_issue():
    """The open "Website update didn't publish" issue the Actions bot opened,
    or None. Matching the title alone would let anyone's issue with that
    title be rewritten or closed by the bot."""
    out = common.gh("api", "--paginate", f"repos/{common.repo()}/issues?state=open&per_page=100",
                    "--jq", '.[] | select(.pull_request == null) | {number, title, body, user: .user.login}').stdout
    for line in out.splitlines():
        if line.strip():
            item = json.loads(line)
            if _same_title(item["title"]) and item.get("user") == BOT_LOGIN:
                return item
    return None


def newer_run_exists(run_id=None):
    """True when a publishing run newer than this one exists (it superseded
    this one); False when none does (this one ran out of time). Run ids only
    grow. When the API can't say, assume superseded — the old, quiet answer."""
    run_id = int(run_id or os.environ.get("GITHUB_RUN_ID") or 0)
    if not run_id:
        return True
    r = common.gh("api", f"repos/{common.repo()}/actions/runs?per_page=30", "--jq",
                  ".workflow_runs[] | [.id, .path] | @tsv", check=False)
    if r.returncode != 0:
        return True
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) > run_id and parts[1] in PUBLISHING:
            return True
    return False


def apply(action, text, url="", sha=""):
    repo = common.repo()
    issue = open_issue() if action != "none" else None
    if action == "open":
        body = with_footer(text, url, sha)
        if issue is None:
            made = _api("POST", f"repos/{repo}/issues", {"title": TITLE, "body": body})
            return f"opened issue #{made['number']}"
        old = (issue.get("body") or "").split("\n\n---\n<sub>")[0]
        _api("PATCH", f"repos/{repo}/issues/{issue['number']}", {"body": body})
        if old.strip() != text.strip():      # a new problem: say so (this notifies people)
            _api("POST", f"repos/{repo}/issues/{issue['number']}/comments",
                 {"body": "The problem changed — the description above is the latest report."
                          + (f" ([run]({url}))" if url else "")})
            return f"updated issue #{issue['number']} (new problem)"
        return f"updated issue #{issue['number']} (same problem)"
    if action == "close" and issue is not None:
        _api("POST", f"repos/{repo}/issues/{issue['number']}/comments",
             {"body": text + (f" ([run]({url}))" if url else "")})
        _api("PATCH", f"repos/{repo}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
        return f"closed issue #{issue['number']}"
    return "no issue change"


def load_report(directory):
    d = pathlib.Path(directory) if directory else None
    if not d or not (d / "build-report.json").is_file():
        return None
    try:
        rep = json.loads((d / "build-report.json").read_text(encoding="utf-8"))
        md = d / "build-report.md"
        rep["_md"] = md.read_text(encoding="utf-8") if md.is_file() else ""
        return rep
    except ValueError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Open, update or close the publish-problem issue.")
    ap.add_argument("--report-dir", default="", help="folder holding build-report.json/.md")
    args = ap.parse_args(argv)
    env = os.environ
    results = (env.get("BUILD", ""), env.get("PAGES", ""), env.get("CLOUDFLARE", ""))
    superseded = newer_run_exists() if "cancelled" in results else True
    action, text = decide(env.get("BUILD", ""), env.get("PAGES", ""), env.get("PAGES_PUBLISHED", ""),
                          env.get("CLOUDFLARE", ""), load_report(args.report_dir),
                          refused=env.get("REFUSED", "") == "true", superseded=superseded)
    print(f"decision: {action}")
    if action == "none":
        common.summary(f"### Publish report\n\n{text}")
        return
    try:
        done = apply(action, text, common.run_url(), env.get("BUILT_SHA", ""))
    except subprocess.CalledProcessError as e:        # Issues switched off, API hiccup: don't hide the build result
        common.annotate("warning", f"Couldn't update the publish-problem issue: {(e.stderr or '').strip()[:300]}")
        return
    common.summary(f"### Publish report\n\n{done}.")
    print(done)


if __name__ == "__main__":
    common.guarded(main)
