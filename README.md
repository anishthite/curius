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

The sites are two [Cloudflare Worker static-assets deployments](https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/), not GitHub Actions or Cloudflare Pages projects. They preserve the current public URLs:

- `https://curius-links.thite.site` — Curius Front Page
- `https://curius-graph.thite.site` — follower-graph app

`wrangler.frontpage.jsonc` and `wrangler.analysis.jsonc` each attach a Worker to one hostname. Neither has an application handler or per-request computation: Cloudflare serves the staged static assets directly.

One-time migration:

1. In Cloudflare, remove `curius-links.thite.site` from the `curius-frontpage` Pages project and `curius-graph.thite.site` from the `curius-analysis` Pages project. A Worker custom domain cannot be created while the Pages CNAME exists.
2. Deploy both Workers with `npm run deploy:workers`.
3. Disconnect or delete the two old Pages projects so Git pushes no longer trigger Pages builds. Keep the GitHub repository itself connected: the replacement CI/CD integration is Cloudflare Workers Builds.
4. In the Cloudflare dashboard, connect this repository to both `curius-frontpage-worker` and `curius-analysis-worker` under **Settings → Builds → Connect**. Select `main` as the production branch. Each Worker uses the following settings:

   | Setting | Value |
   | --- | --- |
   | Root directory | `/` |
   | Build command | `npm run build:worker` |
   | Frontpage deploy command | `npx wrangler deploy --config wrangler.frontpage.jsonc` |
   | Graph deploy command | `npx wrangler deploy --config wrangler.analysis.jsonc` |

   Cloudflare will then build and deploy every push to `main`; enable non-production branch builds there when preview deployments are wanted. This uses Cloudflare's native build system, not GitHub Actions.

Preview either Worker before deploying:

```sh
npm run dev:frontpage
npm run dev:analysis
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

`npm run deploy:workers` remains useful for a direct local hotfix. The generator now defaults to the two public hostnames, so no deploy-time URL variables or GitHub secrets are needed. `dist/` is an ignored, reproducible staging directory created by `npm run build:worker`.

## Tiny local QA experiment

Put `.md`, `.txt`, or `.rst` files in `analysis/index/`, then ask:

```sh
python3 analysis/curious_agent.py "what does the index say about X?"
python3 analysis/curious_agent.py --self-test
```

Skipped: pushing `data/*.sqlite` and screenshots. Add release assets later if someone needs the full crawl.
