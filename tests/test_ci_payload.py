"""The request guard for workflows Pages CMS can start (tools/ci/payload.py,
CMS_SPEC §8.10): main only, Pages CMS payloads only, allow-listed values."""
import json
import re

import pytest

from ci import payload
from conftest import ROOT

MAIN = "refs/heads/main"


def cms(inputs=None, ref="main", **extra):
    """A payload shaped like the one Pages CMS 2.1.8 sends
    (app/api/[owner]/[repo]/[branch]/actions/route.ts)."""
    p = {"source": "pages-cms", "action": {"name": "restore", "label": "Restore a backup", "cancelable": True},
         "repository": {"owner": "meni-gottesman", "repo": "layers", "ref": ref, "workflowRef": ref,
                        "sha": "0" * 40},
         "triggeredAt": "2026-10-27T15:00:00.000Z",
         "triggeredBy": {"userId": "u1", "name": "Sam Rivera", "email": "sam@example.com",
                         "githubUsername": None, "image": None},
         "context": {"type": "repo", "name": None, "path": None, "data": {}},
         "inputs": inputs or {}}
    p.update(extra)
    return json.dumps(p)


def test_manual_run_uses_plain_inputs():
    assert payload.check("build-deploy", "", MAIN) == {"source": "manual"}
    assert payload.check("restore", "", MAIN)["backup"] == "latest"
    assert payload.check("restore", "", MAIN, {"backup": "backup-2026-11-01-0423"})["backup"] == \
        "backup-2026-11-01-0423"


def test_pages_cms_request():
    out = payload.check("restore", cms({"backup": " Backup-2026-11-01-0423 "}), MAIN, {"backup": "latest"},
                        "meni-gottesman/layers")
    assert out == {"source": "pages-cms", "backup": "backup-2026-11-01-0423"}
    # the CMS value wins over the plain input's default; a missing one falls back to it
    assert payload.check("restore", cms({}), MAIN, {"backup": "latest"})["backup"] == "latest"
    # values the workflow doesn't read are ignored, never output
    out = payload.check("undo", cms({"evil": "$(rm -rf /)", "backup": "x"}), MAIN)
    assert set(out) == {"source"}


@pytest.mark.parametrize("ref", ["refs/heads/draft", "refs/heads/main-2", "refs/tags/v1", "", "refs/pull/1/merge"])
def test_only_main(ref):
    with pytest.raises(payload.Refused, match="main branch"):
        payload.check("undo", "", ref)
    with pytest.raises(payload.Refused, match="main branch"):
        payload.check("build-deploy", cms(), ref)


def test_cms_open_on_another_branch_is_refused():
    with pytest.raises(payload.Refused) as e:
        payload.check("build-deploy", cms(ref="summer-menu"), MAIN)
    assert "summer-menu" in str(e.value) and "Switch Pages CMS back" in str(e.value)
    with pytest.raises(payload.Refused) as e:      # a hostile branch name is defanged before it's shown
        payload.check("build-deploy", cms(ref="x`<img src=x onerror=alert(1)>`\n## hi"), MAIN)
    assert "<" not in str(e.value) and "`x" not in str(e.value) and "\n## hi" not in str(e.value)


@pytest.mark.parametrize("raw", [
    "not json", "[]", '"pages-cms"', "{}", '{"source": "github"}', json.dumps({"inputs": {"backup": "latest"}}),
    "{" + " " * (70 * 1024) + "}",
])
def test_payloads_not_from_pages_cms_are_refused(raw):
    with pytest.raises(payload.Refused):
        payload.check("restore", raw, MAIN)


def test_other_repository_is_refused():
    with pytest.raises(payload.Refused, match="different repository"):
        payload.check("backup", cms(), MAIN, repository="someone/else")
    payload.check("backup", cms(), MAIN, repository="Meni-Gottesman/Layers")      # case doesn't matter


@pytest.mark.parametrize("value,expected", [
    ("latest", "latest"), ("", "latest"), (None, "latest"), ("  LATEST ", "latest"), ("newest", "latest"),
    ("backup-2026-11-01-0423", "backup-2026-11-01-0423"), ("2026-11-01-0423", "backup-2026-11-01-0423"),
    ("2026-11-01", "backup-2026-11-01"), ("Backup-2026-11-01", "backup-2026-11-01"),
])
def test_backup_names_allowed(value, expected):
    assert payload.normalise_backup(value) == expected


@pytest.mark.parametrize("value", [
    "latest; rm -rf /", "$(id)", "`id`", "../../etc/passwd", "backup-2026-11-01-0423 --clobber",
    "backup-2026-13-01-0000", "backup-2026-02-30-1200", "backup-2026-11-01-2460", "backup-2026-11-01-2400",
    "backup-26-11-01", "v1.0", "backup-2026-11-01-0423\nbackup=latest", 20261101, ["latest"], {"a": 1}, True,
])
def test_backup_names_refused(value):
    with pytest.raises(payload.Refused, match="wasn’t recognised"):
        payload.normalise_backup(value)


def test_who_clicked_is_never_output():
    """Pages CMS sends the manager's name and email; in a public repository
    the run's outputs, log and commits are public, so neither leaves check()."""
    out = payload.check("restore", cms({"backup": "latest"}), MAIN)
    assert "Sam" not in json.dumps(out) and "@" not in json.dumps(out)


def event(tmp_path, raw_payload):
    """A workflow_dispatch event file, as GitHub writes it for the run."""
    f = tmp_path / "event.json"
    f.write_text(json.dumps({"inputs": {"payload": raw_payload, "backup": "latest"}, "ref": "refs/heads/main"}))
    return f


def test_cli_reads_the_event_file_and_prints_nothing_personal(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setenv("GITHUB_REF", MAIN)
    monkeypatch.delenv("PAYLOAD", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event(tmp_path, cms({"backup": "2026-11-01"}))))
    monkeypatch.setenv("INPUT_BACKUP", "latest")
    payload.main(["restore"])
    assert out.read_text().splitlines() == ["source=pages-cms", "backup=backup-2026-11-01"]
    printed = capsys.readouterr().out
    assert "sam@example.com" not in printed and "Sam Rivera" not in printed
    monkeypatch.setenv("GITHUB_REF", "refs/heads/other")
    with pytest.raises(SystemExit) as e:
        payload.main(["restore"])
    assert e.value.code == 1
    assert "only runs on the main branch" in (tmp_path / "summary").read_text()
    assert "::error" in capsys.readouterr().out
    assert out.read_text().splitlines()[-1] == "refused=true"          # the publish report stays quiet


def test_event_file_shapes(tmp_path):
    assert payload.event_payload(str(event(tmp_path, '{"source": "pages-cms"}'))) == '{"source": "pages-cms"}'
    push = tmp_path / "push.json"
    push.write_text(json.dumps({"ref": "refs/heads/main", "commits": []}))          # a push or a schedule
    assert payload.event_payload(str(push)) == ""
    assert payload.event_payload(str(tmp_path / "missing.json")) == ""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"inputs": {"payload": {"not": "a string"}}}))
    assert payload.event_payload(str(bad)) == ""


def test_every_payload_workflow_is_guarded():
    """Each workflow Pages CMS can start (a `payload` input) is known here,
    refuses other branches before checking anything out, and never touches
    the payload in YAML: not in a run: script (injection) and not in a step's
    env: either (GitHub prints a step's environment in its public log, and
    the payload holds the manager's email). payload.py reads the event file."""
    wf_dir = ROOT / ".github" / "workflows"
    with_payload = set()
    for f in sorted(wf_dir.glob("*.yml")):
        text = f.read_text(encoding="utf-8")
        if re.search(r"^\s{6}payload:\s*$", text, re.M):
            with_payload.add(f.stem)
            assert "if: github.ref != 'refs/heads/main'" in text, f.name
            first_checkout = text.index("uses: actions/checkout@")
            assert text.index("if: github.ref != 'refs/heads/main'") < first_checkout, f.name
            assert "inputs.payload" not in text and "event.inputs" not in text, f.name
            assert f"python3 tools/ci/payload.py {f.stem}" in text, f.name
    assert with_payload == set(payload.WORKFLOWS)
