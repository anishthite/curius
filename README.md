# Curius

Small stdlib-first tools around public Curius data.

## Layout

- `scraper/` — public Curius crawler; writes local SQLite/progress files to ignored `data/`.
- `analysis/` — one-time graph/front-page generator plus generated analysis pages.
- `site/` — ongoing Hacker News-style static front page (`site/index.html`).

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

## Build pages

```sh
python3 analysis/build_follower_site.py
open site/index.html
open analysis/follower_graph.html
open analysis/follower_metrics.html
open analysis/follower_algorithms.html
open analysis/follower_next_questions.html
```

Check the generator:

```sh
python3 analysis/build_follower_site.py --self-test
```

## Tiny local QA experiment

Put `.md`, `.txt`, or `.rst` files in `analysis/index/`, then ask:

```sh
python3 analysis/curious_agent.py "what does the index say about X?"
python3 analysis/curious_agent.py --self-test
```

Skipped: pushing `data/*.sqlite` and screenshots. Add release assets later if someone needs the full crawl.
