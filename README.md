# Letterboxd Free-to-Watch Checker

Pulls one or more public Letterboxd lists, checks which of the following
services carry each film at **no extra cost** right now (subscription-included,
free, or ad-supported — rent/buy is ignored), and writes the result to a
static HTML page per list, plus a landing page linking to all of them:

Netflix · Prime Video · Disney+ · Hulu · Peacock · Apple TV+ · HBO/Max ·
Paramount+ · a free ad-supported catch-all (Pluto TV, Tubi, etc. — named
specifically per film, not just the umbrella)

Re-run it any time to pick up new additions/removals from each list and
refreshed streaming availability.

**Live at https://owieguy.github.io/letterboxd/** — a GitHub Actions
workflow (`.github/workflows/update.yml`) re-runs the script and redeploys
weekly, the same pattern used by [Fantasy Thing](#hosting-on-github-pages-auto-updating-weekly).
A GitLab Pages setup also exists in `.gitlab-ci.yml` (see
[Hosting on GitLab Pages](#hosting-on-gitlab-pages-auto-updating-weekly))
if you'd rather move hosting there later — GitHub is what's live today.

## One-time setup

1. Install dependencies (Python 3.10+):
   ```
   pip install -r requirements.txt
   ```
2. Get a free TMDB API key: sign up at https://www.themoviedb.org, then
   go to **Settings → API → Request an API Key** (choose "Developer", fill
   the short form — no payment info needed).
3. Copy `.env.example` to `.env` and fill in your key:
   ```
   cp .env.example .env
   ```
   `.env` already lists 3 lists (`LIST_URLS`, comma-separated) and defaults
   to the `US` region (Peacock/Hulu/HBO/Paramount+ availability is mainly a
   US concept). Edit `LIST_URLS` / `COUNTRY` there to add, remove, or swap
   lists — paste a `boxd.it` short link or a full `letterboxd.com/.../list/...`
   URL, either works.

## Usage

```
python main.py
```

This processes every list in `LIST_URLS`, writing each to its own page
(auto-named from the list's title, e.g. `output/watch-with-ash.html`), plus
a hub page at **`output/index.html`** linking to all of them — open that one
first.

Useful flags:
```
python main.py --refresh                 # bypass the cache, re-check every film's availability
python main.py --list-url <url>          # process just this one list instead of everything in .env
python main.py --list-url <url> --output somewhere.html   # ...and write it to an exact path
python main.py --country GB              # check a different region
```

## Hosting on GitHub Pages (auto-updating weekly)

This is how the live site above is actually hosted. `.github/workflows/update.yml`
installs dependencies, runs `python main.py --output-dir docs`, and commits
`docs/` back to `main` if anything changed — GitHub Pages serves whatever's
in `docs/` on the default branch. It runs every Tuesday at 08:00 UTC and can
also be triggered manually from the Actions tab.

### One-time GitHub setup

1. Push this repo to a **public** GitHub repo (public repos get free Pages).
2. **Settings → Secrets and variables → Actions** → add a repository secret
   `TMDB_API_KEY` with your TMDB key. `LIST_URLS` / `COUNTRY` don't need
   secrets — the script's built-in defaults match this repo's
   `.env.example` lists.
3. **Settings → Pages** → Source: "Deploy from a branch" → Branch `main`,
   folder `/docs` → Save.
4. Trigger the workflow once manually (Actions tab → "Update letterboxd
   streaming checker site" → "Run workflow") to populate `docs/` for the
   first time, or just run `python main.py --output-dir docs` locally and
   push `docs/` yourself.

**DST caveat:** GitHub Actions cron is always UTC and doesn't shift for
daylight saving — see the comment in the workflow file.

## Hosting on GitLab Pages (auto-updating weekly)

`.gitlab-ci.yml` defines a `pages` job that installs dependencies, runs
`python main.py --output-dir public` (GitLab Pages serves whatever a job
named `pages` publishes as the `public/` artifact — no need to commit
generated HTML back into the repo, unlike a GitHub Pages setup), and deploys
the result. It runs on every push to the default branch, on demand, and on
a weekly schedule.

### One-time GitLab setup

1. Push this repo to a GitLab project (any visibility — private Pages sites
   just require the viewer to be logged into GitLab).
2. In the project: **Settings → CI/CD → Variables** → add `TMDB_API_KEY`
   (your TMDB key), marked **Masked** (and **Protected** only if you'll
   always run pipelines from a protected branch). `LIST_URLS` / `COUNTRY`
   don't need variables — the script's built-in defaults match this repo's
   `.env.example` lists; add them as variables too if you want to override
   without editing code.
3. **Build → Pipeline schedules** → New schedule → set the interval (e.g.
   `0 8 * * 2` for every Tuesday at 08:00 UTC — use
   https://crontab.guru to compute a different time) → Save, then "Run
   pipeline schedule now" once to trigger the first build.
4. **Deploy → Pages** in the project sidebar shows the live URL once the
   first `pages` job succeeds — typically
   `https://<you>.gitlab.io/<project>/`.

**DST caveat:** like GitHub Actions, GitLab's scheduler cron is always UTC
and doesn't shift for daylight saving.

Every scheduled run also pushes the resolved-film/availability cache
(`cache/`) and pip's download cache into GitLab's CI cache (not into git),
so re-runs stay fast and don't needlessly re-hit Letterboxd/TMDB for films
already resolved.

Running with `--list-url` for a one-off list still auto-names its page and
adds it to the landing page (it's remembered across runs); only pairing
`--list-url` with `--output` writes to that exact path and skips the landing
page, for a fully standalone one-off file.

## How it works

- **The list**: Letterboxd has no public API, so the list page (and, for
  each film, its Letterboxd page) is parsed directly from public HTML —
  no login, no private data.
- **TMDB id per film**: resolved from the "TMDB" link on each film's
  Letterboxd page (reliable — no fuzzy title matching needed in the
  common case). Falls back to a TMDB title/year search only if that link
  is missing.
- **Streaming availability**: fetched from TMDB's `/movie/{id}/watch/providers`
  endpoint, which is sourced from JustWatch. A film counts as "free" on a
  service if it appears under JustWatch's `flatrate` (subscription),
  `free`, or `ads` categories — `rent`/`buy` listings are ignored since
  those cost extra.
- **Caching**: `cache/data.json` stores each film's resolved TMDB id
  (kept indefinitely), its last-checked availability (refreshed after 24h
  by default, or immediately with `--refresh`), and a small registry of
  every list the script has ever generated a page for — shared across all
  lists, so a film that appears in more than one list is only looked up
  once, and re-runs are fast and don't hammer either site.
- **Output**: one self-contained HTML page per list — poster grid, a badge
  per service, and a client-side search/filter/sort (no server required) —
  plus `output/index.html` linking to all of them.
- **Badge links**: clicking a green ("available") badge opens that
  service's own search page for the film. TMDB's free API doesn't expose a
  per-title deep link per provider, only one aggregate JustWatch link per
  film, so these are best-effort constructed search URLs (`letterboxd_streaming/providers.py`,
  `SERVICE_SEARCH_URL_TEMPLATES`) — usually the title is the first/only
  result, but it's a search page, not a guaranteed exact-match link, and a
  service can change its search URL pattern without notice. The "Free
  (ads)" badge routes to whichever specific free platform actually matched
  (Tubi, Pluto TV, etc.), not a generic search. The film **title** always
  links to its Letterboxd page.

## Notes / limitations

- A handful of very obscure titles may have no TMDB entry — these are
  shown with no badges and counted as "unresolved" in the console output.
- Streaming availability data comes from JustWatch via TMDB and can lag
  reality slightly or vary by exact plan/region; treat it as "very likely
  right," not gospel.
- Per TMDB's terms, availability data must be attributed to JustWatch —
  that credit is included in the generated page's footer; please keep it
  if you modify the template.
- Badge links are best-effort search URLs (see above) — occasionally one
  may land on a search-results page instead of the exact title, or a
  service may have changed its URL pattern.
