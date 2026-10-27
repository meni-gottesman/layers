"""Hosting limits (tools/ci/limits.py) and the schedule keep-alive
(tools/ci/keepalive.py)."""
import datetime as dt

from ci import keepalive, limits
from conftest import ROOT


def test_the_real_site_fits():
    problems, n, total = limits.check(ROOT / "public")
    assert problems == [] and n > 100 and total > 0


def test_limits_are_reported(tmp_path, monkeypatch):
    (tmp_path / "big.mp4").write_bytes(b"")
    with open(tmp_path / "big.mp4", "r+b") as f:
        f.truncate(26 * 1024 * 1024)                     # sparse: 26 MiB on paper, nothing on disk
    for i in range(3):
        (tmp_path / f"{i}.html").write_text("x")
    monkeypatch.setattr(limits, "MAX_FILES", 2)
    problems, n, _ = limits.check(tmp_path)
    assert n == 4
    assert any("big.mp4 is 26.0 MB" in p for p in problems) and any("at most 2" in p for p in problems)


def test_heartbeat_only_after_a_quiet_spell():
    now = dt.datetime(2026, 12, 1, tzinfo=dt.timezone.utc)
    assert not keepalive.needs_heartbeat(now - dt.timedelta(days=44), now)
    assert keepalive.needs_heartbeat(now - dt.timedelta(days=45), now)
    assert set(keepalive.SCHEDULED) == {"build-deploy.yml", "menu-refresh.yml", "backup.yml", "keep-alive.yml"}
    for wf in keepalive.SCHEDULED:
        assert "schedule:" in (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")


def _keepalive_runs(start, end):
    """Every run of keep-alive.yml's real schedule ("M H * * D", Berkeley
    time) between two datetimes, in UTC."""
    import re
    from zoneinfo import ZoneInfo
    text = (ROOT / ".github" / "workflows" / "keep-alive.yml").read_text(encoding="utf-8")
    minute, hour, dom, month, dow = re.search(r'cron: "([^"]+)"', text).group(1).split()
    assert (dom, month) == ("*", "*") and "timezone: America/Los_Angeles" in text, "update this simulation"
    la = ZoneInfo("America/Los_Angeles")
    day = start.astimezone(la).date()
    while day <= end.astimezone(la).date():
        if dow == "*" or (day.isoweekday() % 7) == int(dow):
            t = dt.datetime(day.year, day.month, day.day, int(hour), int(minute), tzinfo=la)
            if start <= t <= end:
                yield t.astimezone(dt.timezone.utc)
        day += dt.timedelta(days=1)


def test_the_heartbeat_always_lands_before_github_switches_schedules_off():
    """GitHub switches off scheduled workflows after 60 days without activity
    — keep-alive.yml included, after which nothing turns them back on. For a
    last commit at any time of 2027 (every 6 hours), the first run that
    pushes a heartbeat must come before day 60. A monthly schedule failed
    this for about half of all dates (up to 76 days)."""
    worst = dt.timedelta(0)
    last = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    while last.year == 2027:
        first = next(t for t in _keepalive_runs(last, last + dt.timedelta(days=120))
                     if keepalive.needs_heartbeat(last, t))
        worst = max(worst, first - last)
        last += dt.timedelta(hours=6)
    assert worst < dt.timedelta(days=60), worst
    assert worst <= keepalive.HEARTBEAT_AFTER + dt.timedelta(days=7, hours=2)
