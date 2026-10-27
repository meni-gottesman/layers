#!/usr/bin/env python3
"""
Weekly backups as GitHub Releases, and restoring one.

A backup is a release tagged backup-YYYY-MM-DD-HHMM (Berkeley time) holding one
zip, layers-backup-YYYY-MM-DD-HHMM.zip, with:

  content/    every content file                       } exactly as committed on
  src-img/    the photos and photo specs in git         } main (git archive): not
  data/       the menu data                             } src-img/library/, not the
  templates/  the page templates (reference only)       } Instagram downloads
  public/     the site as built that day, including photos built from CMS
              uploads (reference only)
  BACKUP.json what this is: name, time, commit, whether the build passed

The source folders come from the commit rather than the working folder, so a
build's by-products (photo manifests, data/albums.json) never end up in a
backup — and restoring one changes only what really differed.

Kept: the newest 12 weekly (scheduled) backups, and separately the newest 6
made with "Back up now" — so pressing the button a dozen times can never push
the weekly history out. A release's title says which kind it is ("Weekly
backup …" / "Backup …"). In a public repository the releases are public too —
nothing private belongs in content/, src-img/ or data/.

Restoring brings back content/, the PHOTOS in src-img/ and data/ — never
code, templates, the built site, or the developer files in src-img/
(slot-specs.json, existing-photos.json, PROVENANCE.json, the photo
manifests): those stay as they are now. Keeping today's photo manifests
matters: they describe the photos built for today's files, so a restored
photo no longer matches its fingerprint and is rebuilt — with the backup's
manifests, the build would believe the newer photos' files were current and
publish them for the restored content. Each restored folder is made exactly as
it was in the backup, then committed as "Restore from backup <name>".

  python3 tools/ci/backup.py make --out DIR            # zip → DIR, prints the name
  python3 tools/ci/backup.py publish --zip FILE        # create the release, prune to 12
  python3 tools/ci/backup.py fetch --select latest --dir DIR   # resolve + download + check
  python3 tools/ci/backup.py restore --zip FILE        # unpack into the working tree
  python3 tools/ci/backup.py commit --name NAME        # commit + push the restore

The pure parts (names, choosing, pruning, which zip entries are safe) are
tested in tests/test_ci_backup.py.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ci import common, payload  # noqa: E402

KEEP = 12                  # weekly backups kept
KEEP_MANUAL = 6            # "Back up now" backups kept, separately
WEEKLY_TITLE = "Weekly backup"
TAG_RE = re.compile(r"backup-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})")
ZIP_PREFIX = "layers-backup-"
FROM_GIT = ("content", "src-img", "data", "templates")     # committed bytes
BUILT = ("public",)                                         # as built in this run
RESTORED = ("content", "src-img", "data")
PHOTOS_ONLY = ("src-img",)             # from src-img/ a restore takes (and replaces) only photos in git
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
STORED = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".heic", ".mp4", ".mov", ".zip", ".woff2"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
MAX_UNPACKED = 4 * 1024 ** 3          # refuse anything that would unpack past 4 GB


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------
def backup_name(when):
    """backup-2026-11-01-0423 for a (Berkeley-time) datetime."""
    return f"backup-{when:%Y-%m-%d-%H%M}"


def is_backup_tag(tag):
    m = TAG_RE.fullmatch(str(tag))
    if not m:
        return False
    y, mo, d, hh, mm = (int(x) for x in m.groups())
    try:
        dt.date(y, mo, d)
    except ValueError:
        return False
    return hh < 24 and mm < 60


def friendly_time(tag):
    """'backup-2026-11-01-0423' → 'Sunday 1 November 2026, 4:23 AM'."""
    y, mo, d, hh, mm = (int(x) for x in TAG_RE.fullmatch(tag).groups())
    t = dt.datetime(y, mo, d, hh, mm)
    return f"{t:%A} {t.day} {t:%B %Y}, {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def resolve(selector, tags):
    """Pick the backup a selector means among existing release tags:
    "latest" → the newest; "backup-YYYY-MM-DD-HHMM" → that one;
    "backup-YYYY-MM-DD" → the newest from that day. None when there's no match.
    Names sort chronologically, so the newest is the largest."""
    backups = sorted(t for t in tags if is_backup_tag(t))
    if selector == "latest":
        return backups[-1] if backups else None
    if is_backup_tag(selector):
        return selector if selector in backups else None
    day = [t for t in backups if t.startswith(f"{selector}-")]
    return day[-1] if day else None


def to_prune(tags, weekly=None, keep=KEEP, keep_manual=KEEP_MANUAL):
    """The backup tags to delete (oldest first): weekly backups beyond the
    newest `keep`, and "Back up now" backups beyond the newest `keep_manual`,
    counted separately. weekly: the set of tags that are weekly backups (by
    their release title); None = treat every backup as weekly. Releases that
    aren't backups are never touched."""
    backups = sorted(t for t in tags if is_backup_tag(t))
    weekly = set(backups) if weekly is None else set(weekly)
    out = []
    for kind, n in (([t for t in backups if t in weekly], keep), ([t for t in backups if t not in weekly], keep_manual)):
        out += kind[:-n] if len(kind) > n else []
    return sorted(out)


# ---------------------------------------------------------------------------
# Making the zip
# ---------------------------------------------------------------------------
def _stored(rel):
    return zipfile.ZIP_STORED if pathlib.PurePosixPath(rel).suffix.lower() in STORED else zipfile.ZIP_DEFLATED


def _committed_files(root, commit):
    """(path, bytes, mtime) for every file of FROM_GIT in `commit`, streamed
    from `git archive` (tracked files only, exactly as committed)."""
    present = set(common.git("ls-tree", "--name-only", commit, cwd=root).stdout.split())
    tops = [t for t in FROM_GIT if t in present]
    if not tops:
        return
    proc = subprocess.Popen(["git", "archive", "--format=tar", commit, "--", *tops], cwd=root,
                            stdout=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
        for m in tar:
            if m.isfile():
                yield m.name, tar.extractfile(m).read(), m.mtime
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, ["git", "archive", commit])


def _built_files(root):
    for top in BUILT:
        base = pathlib.Path(root) / top
        if base.is_dir():
            for f in sorted(base.rglob("*")):
                if f.is_file() and not f.is_symlink() and f.name not in SKIP_NAMES:
                    yield f.relative_to(root).as_posix(), f


def make_zip(root, out_dir, name, commit="HEAD", build_ok=True):
    """Write <out_dir>/layers-backup-….zip and return its path."""
    root, out_dir = pathlib.Path(root), pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"{ZIP_PREFIX}{name[len('backup-'):]}.zip"
    sha = common.git("rev-parse", commit or "HEAD", cwd=root).stdout.strip()
    counts = dict.fromkeys(FROM_GIT + BUILT, 0)
    with zipfile.ZipFile(zpath, "w") as z:
        for rel, data, mtime in _committed_files(root, sha):
            info = zipfile.ZipInfo(rel, dt.datetime.fromtimestamp(max(mtime, 315532800)).timetuple()[:6])
            info.external_attr = 0o100644 << 16
            z.writestr(info, data, compress_type=_stored(rel))
            counts[rel.split("/", 1)[0]] += 1
        for rel, f in _built_files(root):
            z.write(f, rel, compress_type=_stored(rel))
            counts[rel.split("/", 1)[0]] += 1
        meta = {
            "name": name,
            "made": common.shop_now().isoformat(timespec="seconds"),
            "commit": sha,
            "build": "passed" if build_ok else "failed — public/ is the last committed copy",
            "files": counts,
            "restore": "Restoring brings back content/, src-img/ and data/ only.",
        }
        z.writestr("BACKUP.json", json.dumps(meta, indent=1) + "\n", compress_type=zipfile.ZIP_DEFLATED)
    return zpath


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------
def _restored(name):
    """content/…, data/…, and photos under src-img/ — never src-img/'s
    developer files (specs, manifests) or anything else."""
    top = name.split("/", 1)[0]
    if top in PHOTOS_ONLY:
        return name.lower().endswith(PHOTO_TYPES)
    return top in RESTORED


def safe_members(infos, allowed=RESTORED):
    """The zip entries a restore may write: regular files under the allowed
    top folders (and from src-img/ only photos), with no absolute paths, no
    '..', no backslashes, no symlinks. Returns (members, rejected names).
    Everything else (public/, templates/, src-img/*.json, BACKUP.json) is
    simply not restored."""
    ok, bad = [], []
    for info in infos:
        name = info.filename
        if info.is_dir():
            continue
        parts = name.split("/")
        mode = (info.external_attr >> 16) & 0o170000
        if (name.startswith("/") or "\\" in name or ".." in parts or "" in parts or ":" in parts[0]
                or mode == 0o120000):
            bad.append(name)
            continue
        if parts[0] in allowed and len(parts) > 1 and _restored(name):
            ok.append(info)
    return ok, bad


def read_meta(zpath):
    with zipfile.ZipFile(zpath) as z:
        try:
            return json.loads(z.read("BACKUP.json"))
        except (KeyError, ValueError):
            return None


def restore_into(zpath, root, name):
    """Make content/, src-img/ (files in git) and data/ exactly as in the
    backup. Returns {"written": n, "removed": n}. Raises ValueError for a zip
    that isn't a sound Layers backup — before anything is touched."""
    root = pathlib.Path(root)
    meta = read_meta(zpath)
    if not meta or meta.get("name") != name:
        raise ValueError(f"{pathlib.Path(zpath).name} isn't the Layers backup {name}")
    with zipfile.ZipFile(zpath) as z:
        infos = z.infolist()
        members, bad = safe_members(infos)
        if bad:
            raise ValueError("unsafe paths in the backup: " + ", ".join(bad[:5]))
        if sum(i.file_size for i in members) > MAX_UNPACKED:
            raise ValueError("the backup would unpack to more than 4 GB")
        if not any(i.filename.startswith("content/") for i in members):
            raise ValueError("the backup has no content/ folder")
        removed = 0
        for top in RESTORED:                          # clear what's there now…
            if top in PHOTOS_ONLY:
                out = common.git("ls-files", "-z", "--", top, cwd=root).stdout
                for rel in (p for p in out.split("\0") if p and _restored(p)):
                    (root / rel).unlink(missing_ok=True)
                    removed += 1
            elif (root / top).is_dir():
                removed += sum(1 for f in (root / top).rglob("*") if f.is_file())
                shutil.rmtree(root / top)
        for info in members:                          # …and write the backup's copy
            dest = root / info.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    return {"written": len(members), "removed": removed}


# ---------------------------------------------------------------------------
# gh: releases
# ---------------------------------------------------------------------------
def releases(drafts=True):
    """[(tag, title)] of every release in the repo (backups and anything
    else). Drafts — a backup whose upload broke off — count for pruning, so
    they get cleaned up, but are never offered for a restore."""
    args = ["release", "list", "--repo", common.repo(), "--limit", "1000", "--json", "tagName,name",
            "--jq", ".[] | [.tagName, .name] | @tsv"]
    out = common.gh(*args, *([] if drafts else ["--exclude-drafts"])).stdout
    rows = [ln.split("\t", 1) for ln in out.splitlines() if ln.strip()]
    return [(r[0], r[1] if len(r) > 1 else "") for r in rows]


def release_tags(drafts=True):
    return [t for t, _ in releases(drafts)]


def cmd_make(args):
    name = backup_name(common.shop_now())   # the same name form for both kinds: what the manager types
    zpath = make_zip(common.ROOT, args.out, name, "HEAD", build_ok=args.build == "passed")
    size = zpath.stat().st_size
    if size >= 2 * 1024 ** 3:
        common.fail(f"### The backup is too big\n\n{zpath.name} is {size / 1e9:.1f} GB; GitHub release "
                    "files must be under 2 GB. This is for the developer.", title="Backup too big")
    common.set_output("name", name)
    common.set_output("zip", str(zpath))
    print(f"{zpath.name}: {size / 1e6:.0f} MB")


def cmd_publish(args):
    zpath = pathlib.Path(args.zip)
    name = read_meta(zpath)["name"]
    weekly_run = args.kind == "weekly"
    listed = releases()
    tags = [t for t, _ in listed]
    if name in tags:        # two backups in the same minute: the first one stands
        common.summary(f"### A backup was just made\n\n**{name}** already exists, so no second copy "
                       "was made.")
        return
    when = friendly_time(name)
    notes = (f"Backup of the website's content, photos and menu data, {when} (Berkeley time).\n\n"
             f"To bring it back: in Pages CMS, **Restore a backup** → `{name}` (or `latest` for the "
             "newest). Restoring brings back content, photos and menu data only, then republishes.\n\n"
             "The zip also holds that day's templates and built site, for reference.")
    title = f"{WEEKLY_TITLE} {when}" if weekly_run else f"Backup {when} (Back up now)"
    common.gh("release", "create", name, str(zpath), "--repo", common.repo(),
              "--title", title, "--notes", notes, "--latest=false",
              "--target", read_meta(zpath)["commit"] or "main")
    weekly = {t for t, title_ in listed if title_.startswith(WEEKLY_TITLE)} | ({name} if weekly_run else set())
    pruned = to_prune(tags + [name], weekly)
    for tag in pruned:
        common.gh("release", "delete", tag, "--repo", common.repo(), "--cleanup-tag", "--yes")
    common.summary(f"### Backup made: {name}\n\n{when} (Berkeley time). "
                   + (f"Removed the oldest: {', '.join(pruned)}. " if pruned else "")
                   + f"Keeping the newest {KEEP} weekly backups and {KEEP_MANUAL} made with “Back up now”.")


def cmd_fetch(args):
    try:
        select = payload.normalise_backup(args.select)     # the same allow-list as the request check
    except payload.Refused as e:
        common.fail(str(e), title="Backup not found")
    tags = release_tags(drafts=False)
    tag = resolve(select, tags)
    if not tag:
        have = sorted(t for t in tags if is_backup_tag(t))
        listed = ", ".join(have[-5:]) if have else "none yet"
        common.fail("### No backup with that name\n\n"
                    + ("There are no backups yet." if select == "latest" else
                       f"There's no backup matching **{select}**.")
                    + f" The newest backups: {listed}. Nothing was changed.", title="Backup not found")
    out = pathlib.Path(args.dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    common.gh("release", "download", tag, "--repo", common.repo(), "--pattern", f"{ZIP_PREFIX}*.zip",
              "--dir", str(out))
    zips = sorted(out.glob(f"{ZIP_PREFIX}*.zip"))
    if len(zips) != 1 or (read_meta(zips[0]) or {}).get("name") != tag:
        common.fail(f"### That backup can't be used\n\nThe release **{tag}** doesn't hold a Layers backup "
                    "zip. Nothing was changed.", title="Backup unusable")
    common.set_output("name", tag)
    common.set_output("zip", str(zips[0]))
    print(f"{tag}: {zips[0].name}")


def cmd_restore(args):
    zpath = pathlib.Path(args.zip)
    name = (read_meta(zpath) or {}).get("name", "")
    try:
        r = restore_into(zpath, common.ROOT, name)
    except ValueError as e:
        common.fail(f"### That backup can't be used\n\n{e}. Nothing was changed.", title="Backup unusable")
    print(f"restored {name}: {r['written']} file(s) written, {r['removed']} removed first")


def cmd_commit(args):
    name = args.name
    if not is_backup_tag(name):
        sys.exit(f"error: not a backup name: {name!r}")
    msg = (f"Restore from backup {name}\n\n"
           f"content/, the photos in src-img/ and data/ as they were in {name} ({friendly_time(name)}, "
           "Berkeley time).\n\nLayers-Change: restore\n")
    try:
        sha = common.commit_and_push(list(RESTORED), msg)
    except common.PushConflict:
        common.fail("### Someone saved a change during the restore\n\nA change was saved in Pages CMS while "
                    "the backup was being restored, to the same files. Nothing was restored. Run "
                    "**Restore a backup** again.", title="Restore not saved")
    if sha is None:
        common.summary(f"### Nothing to restore\n\nThe site's content already matches **{name}**.")
        common.set_output("changed", "false")
        return
    common.summary(f"### Restored {name}\n\nContent, photos and menu data are back to {friendly_time(name)} "
                   "(Berkeley time). The site is being republished now.")
    common.set_output("changed", "true")
    common.set_output("sha", sha)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make")
    p.add_argument("--out", required=True)
    p.add_argument("--build", choices=("passed", "failed"), default="passed")
    p = sub.add_parser("publish")
    p.add_argument("--zip", required=True)
    p.add_argument("--kind", choices=("weekly", "manual"), default="manual",
                   help="weekly = the scheduled backup (kept 12), manual = Back up now (kept 6)")
    p = sub.add_parser("fetch")
    p.add_argument("--select", required=True)
    p.add_argument("--dir", required=True)
    p = sub.add_parser("restore")
    p.add_argument("--zip", required=True)
    p = sub.add_parser("commit")
    p.add_argument("--name", required=True)
    args = ap.parse_args(argv)
    {"make": cmd_make, "publish": cmd_publish, "fetch": cmd_fetch, "restore": cmd_restore,
     "commit": cmd_commit}[args.cmd](args)


if __name__ == "__main__":
    common.guarded(main)
