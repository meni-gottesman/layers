# Layers website — setup and operations

For Meni (developer and owner of the setup). The marketing manager's guide is
`docs/HANDBOOK.md`; the build spec is `docs/dev/CMS_SPEC.md`.

Commands below use `meni-gottesman/layers` as the repository. If you use
another name, change it everywhere, and note that the GitHub Pages preview
URL follows the name (`https://meni-gottesman.github.io/<name>/`).

## How it fits together

```
Pages CMS (manager edits) ──commit──▶ main ──▶ "Publish website" (build-deploy.yml)
                                                 1 check content (plain-English report)
                                                 2 build the site, run the tests
                                                 3 publish the same build to:
                                                     GitHub Pages  — the preview, under /layers/
                                                     Cloudflare Pages — the live site (once set up)
                                                 4 open / update / close the
                                                   "Website update didn't publish" issue
```

A failed check or build never touches either site. The live site keeps the
last good version until the problem is fixed.

| Workflow file | Name in GitHub | Runs | Pages CMS button |
|---|---|---|---|
| `build-deploy.yml` | Publish website | every push to main that changes the site; daily 6:07 (Berkeley time); called by the three below | **Publish now** |
| `menu-refresh.yml` | Refresh menu from Square | daily 5:37 | **Refresh menu from Square** |
| `backup.yml` | Back up the website | Sundays 4:23 | **Back up now** |
| `restore.yml` | Restore a backup | on request | **Restore a backup** (field: backup name) |
| `undo.yml` | Undo the last content change | on request | **Undo my last change** |
| `keep-alive.yml` | Keep scheduled updates running | Mondays 3:41 | none |

The helpers the workflows run are in `tools/ci/`. Each one is a short Python
script with tests in `tests/test_ci_*.py`.

---

## 1. Put the repository on GitHub

`meni-gottesman/layers` exists today. It is the old preview: built files only,
pushed by hand with `tools/deploy-github-preview.py`, and its Pages setting is
"Deploy from a branch". To reuse the `/layers/` URL, move the old repo aside
first. Renaming keeps its history.

```bash
# 1. move the old preview repo out of the way (its Pages URL moves with it)
gh repo rename layers-preview-old --repo meni-gottesman/layers --yes

# 2. check nothing private is tracked (the contract, the proposal and PDFs are gitignored)
git ls-files | grep -iE 'contract|proposal|agreement|\.pdf|\.env' || echo "clean"

# 3. create the new repo from this folder and push main
gh repo create meni-gottesman/layers --public --source . --remote origin --push
```

**The repo must be public** for GitHub Pages on GitHub Free. GitHub Pro (free
with the Student Developer Pack) can publish Pages from a private repo, but
the site itself is still public. In a public repo, everything tracked is
public: content, photos, and the backup releases (§6). The catering inbox,
API keys and tokens never go in the repo. They live only as Cloudflare or
GitHub secrets.

### Switch GitHub Pages to "GitHub Actions"

```bash
# new repo, no Pages site yet:
gh api -X POST repos/meni-gottesman/layers/pages -f build_type=workflow
# a repo that already has a Pages site ("Deploy from a branch"):
gh api -X PUT  repos/meni-gottesman/layers/pages -f build_type=workflow

gh api repos/meni-gottesman/layers/pages --jq .build_type      # → workflow
```

In the browser: Settings → Pages → Build and deployment → Source → **GitHub
Actions**. Until this is set, the "Publish to GitHub Pages" job skips itself
and leaves a warning on each run. It doesn't fail.

The deploy job uses the `github-pages` environment. GitHub creates it with
the Pages setting. Check Settings → Environments → github-pages →
Deployment branches: it should be limited to `main`.

### Repository settings the workflows rely on

- **Actions → General → Actions permissions:** allow GitHub's own actions and
  `cloudflare/wrangler-action`, or allow all. The workflows use
  `actions/checkout@v7`, `setup-python@v7`, `cache@v6`, `upload-artifact@v7`,
  `download-artifact@v8`, `configure-pages@v6`, `upload-pages-artifact@v5`,
  `deploy-pages@v5` and `cloudflare/wrangler-action` — the last pinned to a
  full commit (v4.1.3), because it's handed the Cloudflare token. To upgrade
  it, look up the new release's commit (`git ls-remote
  https://github.com/cloudflare/wrangler-action 'refs/tags/v4*'`) and change
  the hash in `build-deploy.yml` and `tests/test_ci_workflows.py`.
- **Exact package versions.** CI installs `requirements.txt` constrained by
  `requirements.lock`, so a library's new release can't stop publishing
  overnight. Upgrade on purpose: the command is at the top of the lock file.
- **The repo must stay public** (GitHub Pages on the Free plan). The jobs
  that push check out without stored credentials and fetch file contents
  anonymously; only the step that saves gets the token.
- **Workflow logs are public too.** Nothing in them prints what Pages CMS
  sends (it includes the manager's email address — `tools/ci/payload.py`
  reads it from the run's event file), and no commit carries her name.
- **Workflow permissions:** "Read repository contents" as the default is
  fine. Each job states exactly what it needs.
- **Don't require pull requests on `main`.** Pages CMS saves, the menu
  refresh, restore and undo all commit straight to main. A rule that requires
  PRs would reject every one of them. Blocking force-pushes and branch
  deletion is fine.
- **Issues must be switched on.** That's where "Website update didn't publish"
  appears. Watch the repo (Watch → All activity, or Custom → Issues) so the
  issue emails you. Only an issue the Actions bot opened is updated or
  closed by it; anyone else's issue with the same title is left alone.
- **The manager doesn't see the issue** (she has no GitHub account, and Pages
  CMS shows no status for a normal save). When it opens for a content
  problem, forward her the issue text — it's written for her — or fix it
  yourself. A code or setup problem is yours.

`tools/deploy-github-preview.py` is retired once Actions publishes the
preview. It refuses to push to a repo that holds the site's source.

### First run

Actions tab → **Publish website** → Run workflow (branch `main`, leave
"payload" empty). Or:

```bash
gh workflow run build-deploy.yml --ref main && gh run watch
```

The run summary shows the build report. The preview appears at
https://meni-gottesman.github.io/layers/.

---

## 2. Pages CMS

1. **Install the GitHub App on this repo only.** Go to
   https://github.com/apps/pages-cms → Install → *Only select repositories* →
   `layers`. It asks for:
   - Repository: Administration (read & write), Actions (read & write),
     Contents (read & write), Checks (read), Commit statuses (read), Metadata
     (read)
   - Account: Email addresses (read)

   Actions access is what lets the CMS buttons start workflows.
2. Sign in at https://app.pagescms.org with GitHub and open
   `meni-gottesman/layers` on branch **main**. The editor comes from
   `.pages.yml`.
3. **Invite the manager.** In Pages CMS, open the repo → **Collaborators** (in
   the sidebar) → invite her email address. She doesn't need a GitHub account. The invite
   link **expires after 24 hours** and each emailed sign-in code after 5
   minutes, so re-invite her if she misses the window. Collaborators can edit
   content and photos and press the buttons. They can't change `.pages.yml`
   or invite anyone.

Things to know:

- **Buttons:** a button press shows "running → succeeded / failed" in the
  CMS. Collaborators can't open GitHub's run pages. When a run fails, the
  reason is on the run's summary page (for you) and, for publishing, in the
  issue. **"Cancelled" is normal** for "Publish now", Undo or Restore when
  another save came in right after: the newer run publishes both changes.
  Menu refresh, restore and undo each have their own queue, so one can never
  drop another that is waiting.
- **Branches:** collaborators can create and switch branches, and edits on
  another branch never publish. Every workflow refuses to run unless it's on
  main and the CMS is on main, and says why.
- **Photo uploads over about 3.3 MB fail** on the hosted CMS (error 413). The
  site's `/photo-prep` page shrinks a photo in the browser before upload.
- **Security:** Pages CMS doesn't check which workflow a button starts.
  Anyone signed in to the CMS could start any workflow that has a `payload`
  input, on any branch, with any values (CMS_SPEC §8.10). So only the five
  safe workflows take `payload`, and each one:
  - refuses anything but main before checking anything out;
  - reads the payload in Python from the run's event file — never through
    `${{ }}` in a script (injection), and never through a step's `env:`
    either (GitHub prints a step's environment in its public log);
  - checks every value against an allow-list (`tools/ci/payload.py`);
  - runs with the smallest permissions it needs.

  `keep-alive.yml` has no payload, so the CMS can't start it.

---

## 3. Instagram, through Behold

The homepage Instagram grid uses hand-picked posts until a Behold feed is
connected. After that it shows the latest posts automatically.

1. Layers' Instagram must be a **Business or Creator** account. Switching is
   free: in the Instagram app, Settings → Account type and tools → Switch to
   professional account.
2. Create a free account at https://behold.so and add an Instagram source.
   You don't need Layers' Instagram password: copy Behold's **authorization
   link** and send it to the manager. She opens it, logs in to Instagram, and
   grants **all** the permissions it asks for, including the ones marked
   optional.
3. In Behold, create a feed of type **JSON** and copy its link,
   `https://feeds.behold.so/<id>`.
4. In Pages CMS: **Instagram** → *Posts to show* → **Automatic** → paste the
   link into *Behold feed link* → Save. The build after that save fetches
   the feed.

How it behaves:

- Visitors' browsers never call Behold. The build fetches the feed and
  rebuilds the photos like any other photo on the site.
- Behold's free plan counts every feed request, with a cap of 1,200 a month.
  The daily 6 AM build always fetches the feed; any other build (a save,
  Publish now, Undo …) reuses the last feed and its photos while they're
  under 12 hours old (`src-img/instagram/`, kept in the Actions cache
  `layers-instagram-v1-…`). A busy day of saves costs one or two extra
  requests — about 30–90 a month. If a fetch fails, the last good feed stays
  up for 3 days, then the hand-picked posts; the build report says why. A
  fetch gives up after 60 seconds, so a slow Behold can't hold up a publish.
- If Layers' Instagram password or privacy setting changes, open the same
  authorization link again.

---

## 4. Cloudflare Pages: the live site

Production runs on Cloudflare Pages, which serves the site at the root and
runs the two Functions: `/api/menu` (live Square data) and `/api/catering`
(the inquiry form). Create everything in **Layers' own Cloudflare account**,
then add yourself under Members.

1. **Create the project as Direct Upload.** It can never be switched to Git
   integration later, and doesn't need to be: Actions builds once and uploads
   that build.
   - Dashboard: Workers & Pages → Create → Pages → **Upload assets**. Name it
     (e.g. `layers-superfood-bar`) and create it. You can skip the first
     upload.
   - Or from a terminal: `npx wrangler pages project create layers-superfood-bar --production-branch=main`
2. **Set the Functions' settings** in the Pages project → Settings →
   Variables and Secrets (Production). Store each as a **Secret** where
   noted. They live only in Cloudflare, never in GitHub or the repo.

   | Name | Type | What |
   |---|---|---|
   | `CATERING_TO` | Secret | the inbox catering inquiries go to |
   | `CATERING_FROM` | Text | the verified sender address at the email provider |
   | `RESEND_API_KEY` | Secret | the email provider's key |
   | `TURNSTILE_SECRET` | Secret | recommended: blocks bots on the form |
   | `SQUARE_ACCESS_TOKEN` | Secret | optional: live sold-out labels (§5) |
   | `RATE_LIMIT` | KV binding | optional: per-visitor throttling of the form |
   | `MENU_TTL` | Text | optional: seconds the live menu is cached (default 300) |

3. **API token for GitHub Actions.** My Profile → API Tokens → Create Token →
   *Create Custom Token*:
   - Permissions: **Account · Cloudflare Pages · Edit**
   - Account Resources: Include → Layers' account
   - Leave IP filtering off, because GitHub's runners change address.
4. **Account ID:** shown on the Workers & Pages overview (right-hand column),
   and in the dashboard URL.
5. **Hand all three to GitHub.** Give all three or none: half a setup stops
   the build with an error, so the live site never silently falls behind.

   ```bash
   gh secret set CLOUDFLARE_API_TOKEN   --repo meni-gottesman/layers   # paste when asked
   gh secret set CLOUDFLARE_ACCOUNT_ID  --repo meni-gottesman/layers
   gh variable set CF_PAGES_PROJECT --body layers-superfood-bar --repo meni-gottesman/layers
   ```

6. **Publish now** (or `gh workflow run build-deploy.yml --ref main`). The
   *Publish to Cloudflare Pages* job uploads `public/` and `functions/`. Check
   `https://<project>.pages.dev`.
7. **Custom domain:** Pages project → Custom domains → Set up a domain →
   `layerssuperfoodbar.com`, then add `www.layerssuperfoodbar.com` the same
   way.
   - The apex domain needs the domain's DNS on Cloudflare (add it as a zone
     and switch the nameservers).
   - `www` can be a CNAME at any DNS host.
   - Canonical links and the sitemap already use
     `https://layerssuperfoodbar.com`.

**Rollback:** Pages project → Deployments → ⋯ next to a good production
deployment → *Rollback to this deployment*. This is instant and is the right
fix for a bad deploy. For a content mistake, use Undo or Restore (§6).

---

## 5. Cloudflare Web Analytics and the Square token

**Web Analytics** is free and cookie-free. Use one of the two options, not
both, or visits are counted twice.

- **Through the CMS (works anywhere):** Cloudflare dashboard → Web Analytics →
  Add a site → hostname `layerssuperfoodbar.com`. Copy the token from the
  snippet it shows (the 32-character value after `"token":`). Paste it in
  Pages CMS → **Business details** → *Analytics* → *Cloudflare Web Analytics
  token*. The token is public by design, not a secret.
  - The beacon only loads on `layerssuperfoodbar.com` and
    `www.layerssuperfoodbar.com` (`PRODUCTION_HOSTS` in `tools/render.py`):
    the GitHub Pages preview, the `*.pages.dev` address and localhost don't
    count. If the live domain changes, change `SITE_URL` there.
- **Pages' own switch:** Pages project → Metrics → Web Analytics → Enable.
  This adds the beacon on the next deployment, on Cloudflare only. Cloudflare
  doesn't document whether the switch works for Direct Upload projects. If it
  does and you use it, leave the CMS token empty.

**Square token, for live sold-out labels.** Without it, the menu shows the
built menu (names, prices and photos from the daily refresh). With it,
`/api/menu` reads Square's catalog, and the page marks sold-out items and
adds brand-new ones.

1. https://developer.squareup.com → sign in with Layers' Square account →
   Applications → **+** → name it "Layers website".
2. Switch the app to **Production** → Credentials → copy the *Production
   access token*. It acts with the full access of Layers' Square account.
   Keep it only as the Cloudflare secret `SQUARE_ACCESS_TOKEN` (§4 step 2).
   Never put it in GitHub, the repo or a chat.
3. Publish (or just wait). Functions read it at request time.

The daily menu refresh doesn't need the token. It reads Layers' public
Square Online store.

---

## 6. Backups, restore and undo

### Backups

`backup.yml` runs every Sunday and on **Back up now**. It makes a GitHub
Release named `backup-YYYY-MM-DD-HHMM` (Berkeley time; titled "Weekly backup
…" or "Backup … (Back up now)") holding one zip,
`layers-backup-YYYY-MM-DD-HHMM.zip`, with:

- `content/`, `src-img/` (the photos in git, not `src-img/library/`), `data/`
  and `templates/`, exactly as committed on main;
- `public/`, the site as built that day, for reference;
- `BACKUP.json`, which records when the backup was made, from which commit,
  and whether that day's build passed.

The **newest 12 weekly** backups are kept, and separately the **newest 6
made with "Back up now"**; older ones are deleted with their tags. A morning
of button presses can never push the weekly history out. The backup's build
runs `--offline`, so it never spends a Behold request.
Today's zip is about 310 MB, almost all photos. Each release file must stay
under 2 GB. **Releases in a public repo are public:** anyone can download a
backup. That's acceptable because everything in it is already public in the
repo. Keep anything private out of `content/`, `src-img/` and `data/`.

List them: `gh release list --repo meni-gottesman/layers`, or the repo's
**Releases** page, which the manager can see without an account.

### Restore

**Restore a backup** (or `gh workflow run restore.yml --ref main -f backup=latest`)
accepts:

- `latest`, for the newest backup;
- a full name such as `backup-2026-11-01-0423`, with or without `backup-`;
- a date such as `2026-11-01`, for the newest backup from that day.

Anything else is refused before anything happens. A name that matches no
backup is refused with a list of the newest backups.

What a restore does:

- It brings back **only `content/`, the photos in `src-img/` and `data/`**:
  each becomes exactly what the backup holds. It never restores code,
  templates, the built site, or `src-img/`'s developer files
  (`slot-specs.json`, `existing-photos.json`, `PROVENANCE.json`, the photo
  manifests) — today's manifests stay, so every restored photo is rebuilt
  rather than mistaken for the newer photo that was built under its name.
- It checks the restored content with the build's validation **before**
  committing. If the backup doesn't pass today's checks, nothing is
  committed.
- It commits "Restore from backup <name>" as *Layers website bot* (no names:
  the history is public), then publishes.

### Undo my last change

`undo.yml` reverts the most recent commit that changed `content/` or a photo
in `src-img/`, then publishes. `src-img/`'s other files (crop specs, photo
manifests, the exempt-photo list) are code: a commit that only re-tunes a
crop is skipped, never undone.

- **Repeated presses go further back.** Each undo records the commit it
  reverted (`Layers-Undo-Of:` in the message), so pressing Undo again undoes
  the change before it. It doesn't redo the first one.
- **The daily menu refresh is skipped.** It's the bot's change, not the
  manager's. Code-only commits are skipped too.
- **A restore can be undone.**
- **Refused, with the reason on the run page:**
  - a change that also touched anything but `content/`, photos in `src-img/`
    and `data/` (the developer's to undo);
  - a merge commit;
  - a change that a later edit to the same file overlaps;
  - a revert whose content wouldn't pass the build's checks.

The rules are in `tools/ci/undo.py`, with tests in `tests/test_ci_undo.py`.

### When a publish fails

- **One issue, "Website update didn't publish".** It opens with the
  plain-English build report as its body. The next failure updates it, and a
  comment is added only when the problem changed, so a failing daily build
  doesn't email you every morning. The next good publish closes it with a
  comment.
- **Content problems** read like "Opening hours › Saturday → Opens: '9am'
  isn't a time …". The manager fixes them in the CMS and saves again.
- **Code or setup problems** say so: tests, a missing secret, a failed
  upload to Cloudflare. The run's summary page has the details.
- **Superseded runs are cancelled quietly.** A burst of saves cancels the
  older builds, and one publish carries all the changes. A run cancelled
  with no newer run behind it ran out of time — that opens the issue.
- **A refused request** (Publish now pressed while the CMS was on another
  branch) doesn't open the issue: the refusal is on the run's page.
- **Preview-only failures don't open the issue.** If only the GitHub Pages
  preview failed while the live site published, the red run tells you
  instead.

### Tests in CI check code, not content

CI runs plain `python -m pytest -q`. Every test that needs content reads the
frozen seed in `tests/fixtures/seed/` — never `content/` — so new hours, an
uploaded photo, a special switched off, an event, the announcement bar or a
photo deleted from the media library can't fail a test and hold up an update
(a deleted seed photo is read back from git history; that's why the build
job checks out full history with `filter: blob:none`). The build's validation
is what judges content. When your own change makes a seed assertion wrong,
update the fixture on purpose (`tests/conftest.py` explains how).

A separate developer-only step, `tools/cms_normalize.py --check`, tells you
when a content file isn't in the CMS's exact format (a hand edit); it never
stops a publish.

---

## 7. Keeping the schedules alive

GitHub switches off scheduled workflows in a public repo after **60 days**
with no activity — including `keep-alive.yml` itself, after which nothing
turns them back on. A quiet winter would silently stop the daily build, the
menu refresh and the backups. `keep-alive.yml` runs **every Monday** and:

- re-enables any of the four scheduled workflows GitHub switched off for
  inactivity (one you switched off by hand stays off, with a note);
- if main has had **no commit for 45 days**, pushes an empty "heartbeat"
  commit. It changes no files, so Undo and the CMS history ignore it.
  Weekly runs put the heartbeat at day 52 at the latest
  (`tests/test_ci_limits.py` steps through the real schedule).

If a schedule was disabled anyway, re-enable it:

```bash
gh workflow enable build-deploy.yml --repo meni-gottesman/layers
```

---

## 8. Running things locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # CI adds -c requirements.lock
.venv/bin/python tools/build.py            # the same build CI runs
.venv/bin/python tools/build.py --check    # content checks only
.venv/bin/python -m pytest -q              # all tests (the CI helpers: tests/test_ci_*.py)
```

**The GitHub Pages preview, exactly as Actions makes it:**

```bash
python3 tools/ci/prefix.py public /tmp/layers-preview/layers --prefix /layers
python3 -m http.server 8971 --bind 127.0.0.1 --directory /tmp/layers-preview
# → http://127.0.0.1:8971/layers/
```

**Lint the workflows** (it must report nothing):

```bash
brew install actionlint && actionlint
```

**The CI helpers by hand.** Outside Actions they print their outputs instead
of writing them. Run `undo.py` and `backup.py restore` only in a scratch
clone, because they change the working tree.

```bash
GITHUB_REF=refs/heads/main INPUT_BACKUP=2026-11-01 python3 tools/ci/payload.py restore
python3 tools/ci/backup.py make --out /tmp/layers-backup            # a backup zip, no upload
python3 tools/ci/limits.py public                                   # hosting limits
```

**Start workflows from the terminal:**

```bash
gh workflow run build-deploy.yml --ref main
gh workflow run menu-refresh.yml --ref main
gh workflow run backup.yml       --ref main
gh workflow run restore.yml      --ref main -f backup=latest
gh workflow run undo.yml         --ref main
gh run list --limit 5 && gh run watch
```

**The photo cache.** Photos built from CMS uploads aren't committed, so
Actions keeps them in a cache (`layers-photos-v1-…`): the built photo folders
plus `src-img/media-manifest.json` and `album-manifest.json`. A stale cache
can only cost time: any photo whose fingerprint doesn't match is rebuilt. To
start fresh, run `gh cache delete --all --repo meni-gottesman/layers`, or
change `v1` to `v2` in the two workflows that use it. Unused caches expire
after 7 days. (A restore never brings back old photo manifests, so even a
reset cache can't make the build publish the wrong photo.) The Instagram
feed has its own small cache, `layers-instagram-v1-…`; deleting it just means
the next build fetches the feed again.
