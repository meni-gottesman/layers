"""Python version compatibility: the build supports Python 3.11 and newer
(CMS_SPEC §0, requirements.txt), but CI runs 3.12 and laptops run newer, and
both accept f-string syntax that 3.11 rejects (PEP 701). These checks catch
that before it reaches someone running 3.11."""
import glob
import io
import os
import pathlib
import shutil
import subprocess
import tokenize

import pytest

from conftest import ROOT

SOURCES = sorted(glob.glob(str(ROOT / "tools" / "**" / "*.py"), recursive=True)
                 + glob.glob(str(ROOT / "tests" / "*.py")))


def _quote(tok):
    """The quote characters a string / f-string token opens with ('"', "'''" …)."""
    s = tok.lstrip("rRbBuUfF")
    return s[:3] if s[:3] in ('"""', "'''") else s[:1]


def pep701_problems(src):
    """f-string expressions that only parse on Python 3.12+: a backslash, a
    reused quote character or a comment inside the {…} part. On 3.12+ the
    tokenizer exposes f-string internals (FSTRING_START …); older tokenizers
    don't, and there the file simply has to compile (the imports prove it)."""
    start = getattr(tokenize, "FSTRING_START", None)
    if start is None:
        return []
    middle, end = tokenize.FSTRING_MIDDLE, tokenize.FSTRING_END
    out, stack = [], []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if stack and tok.type not in (middle, end):
            where = f"line {tok.start[0]}"
            if tok.type == tokenize.STRING and "\\" in tok.string:
                out.append(f"{where}: backslash inside an f-string expression")
            if tok.type in (tokenize.STRING, start) and _quote(tok.string)[0] == stack[-1][0]:
                out.append(f"{where}: f-string expression reuses the enclosing quote")
            if tok.type == tokenize.COMMENT:
                out.append(f"{where}: comment inside an f-string expression")
        if tok.type == start:
            stack.append(_quote(tok.string))
        elif tok.type == end:
            stack.pop()
    return out


def test_no_python_312_only_fstrings():
    problems = []
    for path in SOURCES:
        problems += [f"{os.path.relpath(path, ROOT)} {p}" for p in
                     pep701_problems(pathlib.Path(path).read_text(encoding="utf-8"))]
    assert not problems, "\n".join(problems)


def test_the_lint_catches_what_python_311_rejects():
    if getattr(tokenize, "FSTRING_START", None) is None:
        pytest.skip("this interpreter's tokenizer doesn't expose f-string internals")
    assert pep701_problems("x = f\"{', '.join(re.sub(r'\\s+', ' ', n) for n in m)}\"\n")
    assert pep701_problems('x = f"{"a"}"\n')
    assert not pep701_problems("x = f\"{a!r:>{w}} and {', '.join(b)}\"\n")


def _python311():
    """A Python 3.11 interpreter, if this machine has one (PYTHON311, PATH, uv)."""
    cands = [os.environ.get("PYTHON311"), shutil.which("python3.11")]
    cands += sorted(glob.glob(os.path.expanduser("~/.local/share/uv/python/cpython-3.11*/bin/python3.11")))
    return next((c for c in cands if c and os.path.isfile(c)), None)


def test_every_source_compiles_on_python_311():
    py = _python311()
    if py is None:
        pytest.skip("no Python 3.11 on this machine (set PYTHON311 to check)")
    # compile() in memory: py_compile would leave __pycache__ files behind
    code = "import sys\nfor f in sys.argv[1:]:\n    compile(open(f, encoding='utf-8').read(), f, 'exec')\n"
    r = subprocess.run([py, "-c", code, *SOURCES], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
