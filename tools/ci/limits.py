#!/usr/bin/env python3
"""
The hosting limits a built site must stay under, checked in CI before
anything is uploaded (a host that rejects the upload halfway is worse than a
build that stops with a clear reason):

  Cloudflare Pages (Free)   at most 20,000 files; no file over 25 MiB
  GitHub Pages              the published site under 1 GB

  python3 tools/ci/limits.py public
"""
import pathlib
import sys

MAX_FILES = 20_000
MAX_FILE = 25 * 1024 * 1024
MAX_SITE = 1_000_000_000


def check(site):
    """Problems (plain-English strings) for the built site folder; [] = fine."""
    site = pathlib.Path(site)
    files = [f for f in site.rglob("*") if f.is_file()]
    problems = []
    if len(files) > MAX_FILES:
        problems.append(f"The site has {len(files):,} files; Cloudflare Pages accepts at most {MAX_FILES:,}.")
    for f in files:
        size = f.stat().st_size
        if size > MAX_FILE:
            problems.append(f"{f.relative_to(site)} is {size / 2**20:.1f} MB; Cloudflare Pages accepts files "
                            "up to 25 MB.")
    total = sum(f.stat().st_size for f in files)
    if total > MAX_SITE:
        problems.append(f"The site is {total / 1e9:.2f} GB; GitHub Pages publishes at most 1 GB.")
    return problems, len(files), total


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site = pathlib.Path(argv[0] if argv else "public")
    problems, n, total = check(site)
    print(f"{site}: {n:,} files, {total / 1e6:.0f} MB")
    if problems:
        print("::error title=Site too big to host::" + " ".join(problems).replace("\n", " "))
        sys.exit("\n".join(problems))


if __name__ == "__main__":
    main()
