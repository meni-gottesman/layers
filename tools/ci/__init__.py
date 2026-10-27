"""
Helpers for the GitHub Actions workflows in .github/workflows/ (setup and
operations: docs/SETUP.md).

Each module here is both importable (the tests in tests/test_ci_*.py call the
pure functions) and runnable as a script from a workflow step:

  payload.py    checks a Pages CMS action request: main only, from Pages CMS,
                allow-listed values (CMS_SPEC §8.10)
  prefix.py     the GitHub Pages URL-prefix transform (/assets/… → /layers/assets/…)
  limits.py     the hosting limits a build must stay under (file count and size)
  report.py     opens / updates / closes the "Website update didn't publish" issue
  menu.py       commits the daily Square refresh only when the menu changed
  backup.py     makes, lists, prunes and restores the weekly backup releases
  undo.py       finds and reverts the manager's most recent content change
  keepalive.py  keeps the scheduled workflows from being switched off
  common.py     shared bits: step outputs, the run summary, git + gh calls

The workflows run most of these with the runner's own Python 3 and the
standard library only; the steps that also run tools/build.py use the
Python set up from requirements.txt (pinned by requirements.lock). The test
suite runs as plain `python -m pytest -q`: content-dependent tests read the
frozen seed content in tests/fixtures/seed, so the manager's edits never
fail it.
"""
