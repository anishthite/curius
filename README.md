# Curius

Small stdlib-first tools around public Curius data.

## Layout

- `scraper/` — public Curius crawler; writes local SQLite/progress files to ignored `data/`.
- `analysis/` — generators plus the tiny local QA CLI.
- `apps/frontpage/` — Hacker News-style static app (`apps/frontpage/index.html`) plus `how-this-works.html`.
- `apps/analysis/` — follower graph analysis static app (`apps/analysis/index.html`).

## Scrape

```sh
python3 scraper/curius_scraper.py
python3 scraper/curius_scraper.py --person hardeep-gambhir
python3 scraper/curius_scraper.py --skip-social --all-people
```

Local outputs:

- `data/curius.sqlite`
- `data/curius_scrape_progress.html`

Quick check:

```sh
python3 scraper/curius_scraper.py --self-test
python3 scraper/curius_scraper.py --limit-users 3 --delay 0
```

## Link/highlight updater

Refresh stale saved links and highlights, then rebuild the frontpage HTML files:

```sh
python3 scraper/curius_link_highlight_updater.py --limit-users 200
open data/curius_link_highlight_updater.html
```

Keep it running locally:

```sh
python3 scraper/curius_link_highlight_updater.py --loop --sleep 600 --limit-users 200
```

Check it:

```sh
python3 scraper/curius_link_highlight_updater.py --self-test
python3 scraper/curius_link_highlight_updater.py --limit-users 1 --delay 0
```

## Build pages

```sh
python3 analysis/build_follower_site.py
open apps/frontpage/index.html
open apps/frontpage/how-this-works.html
open apps/analysis/index.html
open apps/analysis/metrics.html
open apps/analysis/algorithms.html
open apps/analysis/questions.html
```

Check the generator:

```sh
python3 analysis/build_follower_site.py --self-test
```

## Deploy

Create two Cloudflare Pages projects from this repo, or set `CLOUDFLARE_API_TOKEN` for direct deploys:

| Project | Build command | Output directory |
| --- | --- | --- |
| `curius-frontpage` | empty | `apps/frontpage` |
| `curius-analysis` | empty | `apps/analysis` |

`.github/workflows/update-curius.yml` runs on relevant `main` pushes, twice a day, and on demand. It restores the cached SQLite DB, refreshes stale links/highlights, rebuilds both apps, commits changed `apps/**/*.html`, and deploys directly when `CLOUDFLARE_API_TOKEN` is set. Without that secret, connect both Cloudflare Pages projects to this GitHub repo with the empty build commands and output directories above.

Repo secret for direct deploy:

| Secret | Use |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Cloudflare token with Pages edit access |

Optional repo variables:

| Variable | Default | Use |
| --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | detected locally | Cloudflare account for direct deploy |
| `CURIUS_FRONTPAGE_URL` | `https://curius.thite.site` | frontpage app URL for cross-links |
| `CURIUS_ANALYSIS_URL` | `https://curius-analysis.pages.dev` | analysis app URL for cross-links |
| `CURIUS_REFRESH_LIMIT` | `200` | stale users refreshed per run |
| `CURIUS_SOCIAL_LIMIT` | unset | cap users/follows crawl when social refresh runs |
| `CURIUS_REQUEST_DELAY` | `0.2` | seconds between Curius API requests |

## Tiny local QA experiment

Put `.md`, `.txt`, or `.rst` files in `analysis/index/`, then ask:

```sh
python3 analysis/curious_agent.py "what does the index say about X?"
python3 analysis/curious_agent.py --self-test
```

Skipped: pushing `data/*.sqlite` and screenshots. Add release assets later if someone needs the full crawl.
