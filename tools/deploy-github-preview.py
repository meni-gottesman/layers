#!/usr/bin/env python3
"""
Publishes the built site to the old hand-pushed GitHub Pages preview,
https://meni-gottesman.github.io/layers/ (repo meni-gottesman/layers, branch main,
holding built output only).

  python3 tools/build.py && python3 tools/deploy-github-preview.py "message"

Once this source repo is on GitHub with Pages set to "GitHub Actions"
(docs/SETUP.md), .github/workflows/build-deploy.yml publishes the preview on
every change and this script is retired. It refuses to push to a repository
that holds the site's source (tools/build.py, content/), so it can never
overwrite the real repo with built files.

GitHub serves a project site under /layers/, while the site uses root-absolute
URLs (/assets/…, /menu). This copies public/ to a staging folder and prefixes
every root-absolute URL with /layers — tools/ci/prefix.py, shared with the
Actions deploy — then commits and pushes.

The preview is static, so the two Pages Functions don't run there: the menu
shows the built menu (as it does without a Square token), and the catering form
reports that it's temporarily unavailable. Production is Cloudflare Pages.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ci import prefix  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
REPO = "https://github.com/meni-gottesman/layers.git"
PREFIX = "/layers"


def main():
    if not (PUBLIC / "index.html").exists():
        sys.exit("error: build first (python3 tools/build.py)")
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td) / "repo"
        subprocess.run(["git", "clone", "--depth", "1", REPO, str(repo)], check=True)
        if (repo / "tools" / "build.py").exists() or (repo / "content").is_dir():
            sys.exit(f"error: {REPO} holds the site's source, not a built preview. The preview is "
                     "published by GitHub Actions now (.github/workflows/build-deploy.yml); "
                     "nothing was pushed.")
        staged = pathlib.Path(td) / "site"
        left = prefix.prefix_tree(PUBLIC, staged, PREFIX)       # copy + .nojekyll + prefix
        if left:
            sys.exit("error: unprefixed URLs:\n  " + "\n  ".join(left[:20]))
        for item in repo.iterdir():                              # replace the whole tree
            if item.name != ".git":
                shutil.rmtree(item) if item.is_dir() else item.unlink()
        shutil.copytree(staged, repo, dirs_exist_ok=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        if subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"]).returncode == 0:
            print("nothing to deploy — preview is already current")
            return
        msg = sys.argv[1] if len(sys.argv) > 1 else "Update client preview build"
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True)
        subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:main"], check=True)
        print("pushed — https://meni-gottesman.github.io/layers/ (GitHub Pages rebuilds in about a minute)")


if __name__ == "__main__":
    main()
