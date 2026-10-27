#!/usr/bin/env python3
"""
Checks a workflow request before anything acts on it — the guard every
workflow that Pages CMS can start runs first (CMS_SPEC §8.10).

Pages CMS starts a workflow with one input, `payload`: a JSON string with the
action, the branch open in the CMS, who clicked (name AND email address), and
the action's own fields under "inputs". Pages CMS doesn't check that request
against .pages.yml, so any CMS user could ask any workflow with a `payload`
input to run on any branch with any values. So:

  * the run must be on main (github.ref) — the workflow also checks this in
    YAML before checking anything out, so code from another branch never runs;
  * a payload must be a JSON object from Pages CMS, for the branch main;
  * only the values a workflow knows are read, each through an allow-list;
    everything else in the payload is ignored — including who clicked, which
    is never output, printed or written into a commit;
  * the payload is read from the event file GitHub writes for the run
    ($GITHUB_EVENT_PATH), never through ${{ }} in the workflow: not in a
    `run:` script (injection), and not in a step's `env:` either — GitHub
    prints a step's environment at the top of its log, and the logs of a
    public repository are public, so the manager's email address would be
    published with every button press.

Manual runs (Actions tab, or another workflow) have an empty payload and use
the workflow's plain inputs instead (INPUT_<NAME> in the environment).

  INPUT_BACKUP=… python3 tools/ci/payload.py restore

Writes step outputs (`source`, and per workflow e.g. `backup`), or
`refused=true` and stops with a friendly explanation on the run's summary
page.
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ci import common  # noqa: E402

MAX_PAYLOAD = 64 * 1024     # Pages CMS sends ~1 KB; anything huge isn't from it


class Refused(Exception):
    """The request can't be acted on; the message is Markdown for the run summary."""


# ---------------------------------------------------------------------------
# Allow-lists for the values a workflow reads
# ---------------------------------------------------------------------------
_BACKUP_RE = re.compile(r"(?:backup-)?(\d{4})-(\d{2})-(\d{2})(?:-(\d{2})(\d{2}))?")


def normalise_backup(value):
    """What the manager typed in "Restore a backup" → a selector backup.py
    understands: "latest", an exact name "backup-2026-11-01-0423", or a day
    "backup-2026-11-01" (the newest backup made that day). Accepts the name
    with or without "backup-", any case, stray spaces. Raises Refused."""
    v = str(value if value is not None else "").strip().lower()
    if v in ("", "latest", "newest", "last"):
        return "latest"
    m = _BACKUP_RE.fullmatch(v)
    ok = False
    if m:
        y, mo, d, hh, mm = m.groups()
        try:
            dt.date(int(y), int(mo), int(d))
            ok = hh is None or (int(hh) < 24 and int(mm) < 60)
        except ValueError:
            ok = False
    if not ok:
        raise Refused(
            "### That backup name wasn’t recognised\n\n"
            f"“{shown(value)}” isn’t a backup name. Type **latest** for the newest backup, or a name "
            "from the backups list such as **backup-2026-11-01-0423** (a date like **2026-11-01** "
            "picks the newest backup from that day). Nothing was changed.")
    return f"backup-{y}-{mo}-{d}" + (f"-{hh}{mm}" if hh else "")


# Each workflow: the payload "inputs" it reads, and how each is checked. A
# value missing from the payload falls back to the plain input of the same
# name (INPUT_<NAME> in the environment), then to the default.
WORKFLOWS = {
    "build-deploy": {},
    "menu-refresh": {},
    "backup": {},
    "restore": {"backup": (normalise_backup, "latest")},
    "undo": {},
}


def shown(value, limit=40):
    """An untrusted value made safe to quote in Markdown: printable, short,
    no Markdown/HTML specials."""
    s = re.sub(r"[^\w .@:/+-]", "", str(value), flags=re.UNICODE)[:limit]
    return s or "(blank)"


# ---------------------------------------------------------------------------
def check(workflow, raw_payload, ref, plain_inputs=None, repository=""):
    """Validate one request. Returns a dict of values to output:
    {"source": "pages-cms"|"manual", <workflow inputs>}.
    Raises Refused with a friendly Markdown explanation."""
    if workflow not in WORKFLOWS:
        raise ValueError(f"unknown workflow {workflow!r}")
    plain_inputs = plain_inputs or {}
    if ref != common.MAIN:
        raise Refused(
            "### This only runs on the main branch\n\n"
            "The website publishes from **main**. If you switched branches in Pages CMS, switch back to "
            "**main** (the branch menu at the top left) and try again. Nothing was changed.")

    out = {"source": "manual"}
    sent = {}
    raw = raw_payload or ""
    if raw.strip():
        if len(raw) > MAX_PAYLOAD:
            raise Refused("### This request wasn’t understood\n\nThe request was too large to be from "
                          "Pages CMS. Nothing was changed.")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise Refused("### This request wasn’t understood\n\nThe request from Pages CMS wasn’t valid. "
                          "Nothing was changed.") from None
        if not isinstance(payload, dict) or payload.get("source") != "pages-cms":
            raise Refused("### This request wasn’t understood\n\nOnly Pages CMS (or a run started by hand "
                          "with an empty payload) can start this. Nothing was changed.")
        rep = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
        cms_branch = rep.get("ref")
        if cms_branch is not None and cms_branch != "main":
            raise Refused(
                "### Switch Pages CMS back to the main branch\n\n"
                f"Pages CMS was on the branch “{shown(cms_branch)}”. The website only publishes from "
                "**main**: switch back to **main** with the branch menu at the top left, then try again. "
                "Nothing was changed.")
        if repository and rep.get("owner") and rep.get("repo"):
            if f"{rep['owner']}/{rep['repo']}".lower() != repository.lower():
                raise Refused("### This request wasn’t understood\n\nThe request was for a different "
                              "repository. Nothing was changed.")
        sent = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
        out["source"] = "pages-cms"

    for name, (validate, default) in WORKFLOWS[workflow].items():
        if name in sent:
            value = sent[name]
        elif plain_inputs.get(name) not in (None, ""):
            value = plain_inputs[name]
        else:
            value = default
        out[name] = validate(value)
    return out


def event_payload(path=None):
    """The `payload` input of the run, from the event file GitHub writes
    ($GITHUB_EVENT_PATH; "" for a push, a schedule, or a run without one).
    A workflow started by another workflow (workflow_call) sees its caller's
    event, so it checks the request that started the whole run."""
    path = path or os.environ.get("GITHUB_EVENT_PATH", "")
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            event = json.load(f)
    except (OSError, ValueError):
        return ""
    inputs = event.get("inputs") if isinstance(event, dict) else None
    value = inputs.get("payload") if isinstance(inputs, dict) else None
    return value if isinstance(value, str) else ""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in WORKFLOWS:
        sys.exit(f"usage: payload.py {{{'|'.join(WORKFLOWS)}}}")
    workflow = argv[0]
    plain = {name: os.environ.get(f"INPUT_{name.upper()}", "") for name in WORKFLOWS[workflow]}
    try:
        values = check(workflow, event_payload(), os.environ.get("GITHUB_REF", ""),
                       plain, os.environ.get("GITHUB_REPOSITORY", ""))
    except Refused as e:
        common.set_output("refused", "true")     # the publish report stays quiet about a refused request
        common.fail(str(e), title="Request refused")
    for k, v in values.items():
        common.set_output(k, v)
    print(f"request ok ({values['source']})")


if __name__ == "__main__":
    main()
