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
open apps/analysis/about.html
```

Check the generator:

```sh
python3 analysis/build_follower_site.py --self-test
```

## Deploy

The site is a single [Cloudflare Worker static-assets deployment](https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/), not a GitHub Action or a Cloudflare Pages project. It serves:

- `/` — Curius Front Page
- `/analysis/` — follower-graph app

`wrangler.jsonc` attaches the Worker to `curius.thite.site`. It has no application handler and no per-request computation: Cloudflare serves the staged static assets directly.

One-time migration:

1. In Cloudflare, remove `curius.thite.site` from the existing Pages project. A Worker custom domain cannot be created while that Pages CNAME exists.
2. Disconnect or delete the two old Pages projects so Git pushes no longer trigger Pages builds. Keep the GitHub repository itself connected: the replacement CI/CD integration is Cloudflare Workers Builds.
3. Authenticate Wrangler locally with `npx wrangler@4 login`, then deploy with `npm run deploy:worker`. For CI-free non-interactive use, set `CLOUDFLARE_API_TOKEN` in the shell instead.
4. In the Cloudflare dashboard, open the `curius-site` Worker and go to **Settings → Builds → Connect**. Connect this repository, select `main` as the production branch, and use:

   | Setting | Value |
   | --- | --- |
   | Root directory | `/` |
   | Build command | `npm run build:worker` |
   | Deploy command | `npx wrangler deploy` |

   Cloudflare will then build and deploy every push to `main`; enable non-production branch builds there when preview deployments are wanted. This uses Cloudflare's native build system, not GitHub Actions.

Preview the exact Worker asset layout before deploying:

```sh
npm run dev:worker
```

Refresh data locally whenever a new snapshot is wanted. This intentionally replaces the former twice-daily GitHub Actions job; Cloudflare Workers cannot run the repository's Python crawler or retain its local SQLite file. Commit and push the newly generated `apps/` files after refreshing; Cloudflare Workers Builds will publish that pushed snapshot automatically.

```sh
# Run this only when a full social-graph refresh is needed.
python3 scraper/curius_scraper.py --delay 0.2

# Refresh the frontpage data from the local SQLite cache.
python3 scraper/curius_link_highlight_updater.py --limit-users 200 --delay 0.2

# Rebuild both sites with the Worker's same-origin links.
python3 analysis/build_follower_site.py

# Publish through Cloudflare's native CI/CD.
git add apps/frontpage apps/analysis
git commit -m "Update Curius static apps"
git push
```

`npm run deploy:worker` remains useful for a direct local hotfix. The generator now defaults to `/` and `/analysis`, so no deploy-time URL variables or GitHub secrets are needed. `dist/` is an ignored, reproducible staging directory created by `npm run build:worker`.

## Tiny local QA experiment

Put `.md`, `.txt`, or `.rst` files in `analysis/index/`, then ask:

```sh
python3 analysis/curious_agent.py "what does the index say about X?"
python3 analysis/curious_agent.py --self-test
```

Skipped: pushing `data/*.sqlite` and screenshots. Add release assets later if someone needs the full crawl.
