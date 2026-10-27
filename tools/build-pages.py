#!/usr/bin/env python3
"""
Renders the pages only, from the photos, menu and albums already built.

  python3 tools/build-pages.py

The full build is python3 tools/build.py (validate content → menu → photos →
albums → pages → sitemap/robots). This shortcut is for template work: it
validates content/, renders every page from templates/ (Jinja2) and writes
public/. The renderer itself is tools/render.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import render  # noqa: E402

if __name__ == "__main__":
    render.main()
