"""House rules for .github/workflows/ that a linter doesn't know (CMS_SPEC
§6, §8.10, §10, §11): the fixed file names Pages CMS points at, pinned
action versions, no ${{ }} inside run: scripts, least privilege, and the
concurrency rules. Plain text checks — no YAML library needed."""
import re

import pytest

from conftest import ROOT

WF = ROOT / ".github" / "workflows"
FILES = sorted(WF.glob("*.yml"))

# CMS_SPEC §10 (+ the artifact actions from the same research)
PINNED = {
    "actions/checkout": "v7", "actions/setup-python": "v7", "actions/cache/restore": "v6",
    "actions/cache/save": "v6", "actions/configure-pages": "v6", "actions/upload-pages-artifact": "v5",
    "actions/deploy-pages": "v5", "actions/upload-artifact": "v7", "actions/download-artifact": "v8",
    # handed the Cloudflare token: pinned to a commit (v4.1.3), not a movable tag
    "cloudflare/wrangler-action": "953926a2e2182532811c01a25e53647d93bf07c0",
}


def run_scripts(text):
    """Every run: script (single-line or block), as (line number, text)."""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", ln)
        if not m:
            continue
        indent, rest = len(m.group(1)), m.group(2)
        if rest not in ("|", ">", "|-", ">-"):
            out.append((i + 1, rest))
            continue
        body = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            body.append(nxt)
        out.append((i + 1, "\n".join(body)))
    return out


def test_the_cms_workflow_names_exist():
    names = {f.name for f in FILES}
    assert {"build-deploy.yml", "menu-refresh.yml", "backup.yml", "restore.yml", "undo.yml"} <= names


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.name)
def test_actions_are_pinned(f):
    for action, version in re.findall(r"uses:\s*([\w./-]+)@(\S+)", f.read_text(encoding="utf-8")):
        assert PINNED.get(action) == version, f"{f.name}: {action}@{version}"


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.name)
def test_no_expressions_inside_run_scripts(f):
    for line, script in run_scripts(f.read_text(encoding="utf-8")):
        assert "${{" not in script, f"{f.name}:{line} — pass values through env: instead"


@pytest.mark.parametrize("f", FILES, ids=lambda f: f.name)
def test_least_privilege(f):
    text = f.read_text(encoding="utf-8")
    assert re.search(r"^permissions: \{\}$", text, re.M), "no default token permissions at the top"
    assert "write-all" not in text and "read-all" not in text
    # every job states its own permissions
    jobs = re.split(r"^  (?=[a-z][\w-]*:\s*$)", text.split("\njobs:\n", 1)[1], flags=re.M)
    for job in (j for j in jobs if j.strip()):
        assert "\n    permissions:" in job, f"{f.name}: job {job.split(':')[0]} has no permissions block"


def test_secrets_only_where_needed():
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        for name in re.findall(r"secrets\.([A-Z_]+)", text):
            assert name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"), f"{f.name}: {name}"
        assert "secrets.GITHUB_TOKEN" not in text      # github.token, scoped by the job's permissions


def test_build_and_deploy_concurrency():
    text = (WF / "build-deploy.yml").read_text(encoding="utf-8")
    groups = dict(re.findall(r"group: (\S+)\n\s+cancel-in-progress: (true|false)", text))
    assert groups == {"layers-site-build": "true", "layers-site-deploy-pages": "false",
                      "layers-site-deploy-cloudflare": "false", "layers-site-report": "false"}
    # deploys and the report wait for the build; Cloudflare only when it's set up
    assert "if: needs.build.outputs.cloudflare == 'true'" in text
    assert "include-hidden-files: true" in text.split("upload-pages-artifact@v5", 1)[1][:200]
    assert "pages deploy public" in text and "sparse-checkout: functions" in text
    assert "pages: write" in text and "id-token: write" in text and "issues: write" in text


def test_write_jobs_keep_no_credentials_in_git():
    """A job that can push checks out without credentials and hands the
    token only to the step that saves (GIT_PUSH_TOKEN): installing packages,
    syncing Square and decoding photos never run with it in git's config."""
    for name in ("menu-refresh.yml", "restore.yml", "undo.yml", "keep-alive.yml", "backup.yml", "build-deploy.yml"):
        text = (WF / name).read_text(encoding="utf-8")
        for block in text.split("uses: actions/checkout@")[1:]:
            assert "persist-credentials: false" in block.split("- name:", 1)[0], name
        if name in ("menu-refresh.yml", "restore.yml", "undo.yml", "keep-alive.yml"):
            assert text.count("GIT_PUSH_TOKEN: ${{ github.token }}") == 1, name


def test_installs_use_the_lock():
    for f in FILES:
        for line in f.read_text(encoding="utf-8").splitlines():
            if "pip install" in line:
                assert "-c requirements.lock" in line, f"{f.name}: {line.strip()}"


def test_content_writers_queue_apart():
    """Menu refresh, restore and undo each have their own queue: GitHub keeps
    one pending run per group, so a shared one let a third request silently
    drop a waiting restore."""
    groups = [re.search(r"group: (\S+)", (WF / n).read_text(encoding="utf-8")).group(1)
              for n in ("menu-refresh.yml", "restore.yml", "undo.yml")]
    assert len(set(groups)) == 3


def test_callers_grant_what_the_publish_needs():
    for name in ("menu-refresh.yml", "restore.yml", "undo.yml"):
        text = (WF / name).read_text(encoding="utf-8")
        publish = text.split("\n  publish:\n", 1)[1]
        assert "uses: ./.github/workflows/build-deploy.yml" in publish
        assert "secrets: inherit" in publish
        for perm in ("contents: read", "pages: write", "id-token: write", "issues: write"):
            assert perm in publish, f"{name}: {perm}"
        assert "if: needs." in publish and "outputs.changed == 'true'" in publish


def test_schedules_are_in_berkeley_time():
    for name in ("build-deploy.yml", "menu-refresh.yml", "backup.yml", "keep-alive.yml"):
        text = (WF / name).read_text(encoding="utf-8")
        assert "timezone: America/Los_Angeles" in text, name
    assert 'cron: "7 6 * * *"' in (WF / "build-deploy.yml").read_text(encoding="utf-8")       # ~06:00 daily
    assert re.search(r'cron: "\d+ \d+ \* \* 0"', (WF / "backup.yml").read_text(encoding="utf-8"))  # Sundays
