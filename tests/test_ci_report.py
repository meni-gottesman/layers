"""The "Website update didn't publish" issue (tools/ci/report.py): when it's
opened, updated, closed or left alone, and what it says."""
import json

import pytest

from ci import report

FAILED = {"status": "failed", "_md": "# Website update didn’t publish\n\n## What needs fixing\n\n- **Opening hours** › "
                                     "Saturday → Opens: “9am” isn’t a time."}
PASSED = {"status": "passed", "_md": "# Website update: published ✓\n"}


def test_content_problem_posts_the_build_report():
    assert report.decide("failure", "skipped", "", "skipped", FAILED) == ("open", FAILED["_md"])


@pytest.mark.parametrize("rep", [None, PASSED, {"status": "failed", "_md": ""}])
def test_other_build_failures_say_its_not_their_content(rep):
    # no report (setup failed early), or the report passed but the tests failed afterwards
    action, body = report.decide("failure", "skipped", "", "skipped", rep)
    assert action == "open" and "not your" in body and "has **not** changed" in body


def test_success_closes():
    assert report.decide("success", "success", "true", "skipped", PASSED)[0] == "close"
    assert report.decide("success", "success", "true", "success", PASSED)[0] == "close"
    # the preview failing while the live site published: the update did go live
    assert report.decide("success", "failure", "false", "success", PASSED)[0] == "close"


def test_production_upload_failure_opens():
    action, body = report.decide("success", "success", "true", "failure", PASSED)
    assert action == "open" and "Cloudflare" in body and "not your content" in body
    action, body = report.decide("success", "failure", "false", "skipped", PASSED)
    assert action == "open" and "GitHub Pages" in body


@pytest.mark.parametrize("results", [("cancelled", "skipped", "skipped"), ("success", "cancelled", "skipped"),
                                     ("success", "success", "cancelled"), ("skipped", "skipped", "skipped")])
def test_superseded_or_skipped_runs_leave_the_issue_alone(results):
    b, p, c = results
    assert report.decide(b, p, "", c, FAILED)[0] == "none"


def test_a_refused_request_is_not_a_problem():
    """Publish now pressed with the CMS on another branch: the request check
    refuses before building. That's on the run's page, not an issue."""
    assert report.decide("failure", "skipped", "", "skipped", None, refused=True)[0] == "none"


def test_a_run_that_ran_out_of_time_opens_the_issue():
    """A timed-out job is reported as cancelled, like a superseded one: when
    no newer run exists it ran out of time, and that must be said."""
    action, body = report.decide("cancelled", "skipped", "", "skipped", None, superseded=False)
    assert action == "open" and "ran out of time" in body and "isn’t a problem with your content" in body
    assert report.decide("cancelled", "skipped", "", "skipped", None, superseded=True)[0] == "none"


def test_newer_run_exists(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "meni-gottesman/layers")

    class R:
        returncode, stdout = 0, ""

    def runs(*rows):
        r = R()
        r.stdout = "\n".join(f"{i}\t{path}" for i, path in rows)
        return lambda *a, **k: r
    monkeypatch.setattr(report.common, "gh", runs((105, ".github/workflows/build-deploy.yml"),
                                                  (100, ".github/workflows/build-deploy.yml")))
    assert report.newer_run_exists(100)                        # a newer publish superseded run 100
    monkeypatch.setattr(report.common, "gh", runs((105, ".github/workflows/backup.yml"),
                                                  (100, ".github/workflows/build-deploy.yml")))
    assert not report.newer_run_exists(100)                    # only a backup since: it timed out
    monkeypatch.setattr(report.common, "gh", runs((104, ".github/workflows/restore.yml")))
    assert report.newer_run_exists(100)                        # a restore's publish shares the queue


def test_nothing_set_up_yet_is_not_the_managers_problem():
    action, why = report.decide("success", "success", "false", "skipped", PASSED)
    assert action == "none" and "SETUP" in why


def test_footer_and_size_limit():
    body = report.with_footer("x" * 70000, "https://github.com/o/r/actions/runs/1", "abcdef1234")
    assert len(body) <= report.MAX_BODY and "cut short" in body and "[Run details]" in body and "abcdef1" in body


def test_title_match_ignores_apostrophe_style():
    assert report._same_title("Website update didn’t publish") and report._same_title("website update didn't publish ")
    assert not report._same_title("Website update published")


class FakeGitHub:
    """Stands in for `gh api`: issues in memory, calls recorded."""

    def __init__(self, issues=()):
        self.issues = {i["number"]: dict({"user": report.BOT_LOGIN}, **i, state="open") for i in issues}
        self.comments = []

    def __call__(self, *args, check=True, input=None):
        args = list(args)
        method = args[args.index("-X") + 1] if "-X" in args else "GET"
        path = next(a for a in args if a.startswith("repos/"))
        data = None
        if "--input" in args:
            with open(args[args.index("--input") + 1]) as f:
                data = json.load(f)

        class R:
            stdout = ""
        if method == "GET":
            R.stdout = "\n".join(json.dumps({"number": n, "title": i["title"], "body": i["body"], "user": i["user"]})
                                 for n, i in self.issues.items() if i["state"] == "open")
        elif path.endswith("/comments"):
            self.comments.append(data["body"])
            R.stdout = "{}"
        elif method == "POST":
            n = max(self.issues, default=0) + 1
            self.issues[n] = dict(data, number=n, state="open", user=report.BOT_LOGIN)
            R.stdout = json.dumps({"number": n})
        else:
            self.issues[int(path.rsplit("/", 1)[1])].update(data)
            R.stdout = "{}"
        return R


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "meni-gottesman/layers")
    gh = FakeGitHub([{"number": 7, "title": "Something else", "body": ""},
                     {"number": 6, "title": "Website update didn't publish", "body": "spoof", "user": "someone"}])
    monkeypatch.setattr(report.common, "gh", gh)
    return gh


def test_issue_lifecycle(fake):
    assert report.apply("open", FAILED["_md"], "https://run/1", "abc1234") == "opened issue #8"
    assert fake.issues[8]["title"] == report.TITLE and fake.issues[8]["body"].startswith(FAILED["_md"])
    # the same problem again (tomorrow's scheduled build): body refreshed, no new comment
    assert report.apply("open", FAILED["_md"], "https://run/2") == "updated issue #8 (same problem)"
    assert fake.comments == [] and "https://run/2" in fake.issues[8]["body"]
    # a different problem: one comment, so people hear about it
    assert report.apply("open", report.CODE_PROBLEM, "https://run/3") == "updated issue #8 (new problem)"
    assert len(fake.comments) == 1
    assert report.apply("close", "This is fixed.", "https://run/4") == "closed issue #8"
    assert fake.issues[8]["state"] == "closed" and fake.issues[7]["state"] == "open"
    # someone else's issue with the same title is never touched
    assert fake.issues[6]["state"] == "open" and fake.issues[6]["body"] == "spoof"
    assert report.apply("close", "This is fixed.") == "no issue change"      # nothing open: nothing to do
