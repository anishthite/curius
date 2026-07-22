#!/usr/bin/env python3
"""Refresh Curius saved links and highlights, then rebuild the front page."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from curius_scraper import CuriusScraper, DEFAULT_DB, REPO_ROOT, as_bool, utc_now

DEFAULT_PROGRESS = REPO_ROOT / "data/curius_link_highlight_updater.html"
DEFAULT_LOCK = REPO_ROOT / "data/curius_link_highlight_updater.lock"
DEFAULT_SITE_OUT = REPO_ROOT / "apps/frontpage/index.html"


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clear_stale()
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit(f"Updater already running; lock exists: {self.path}")
        os.write(self.fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *_: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _clear_stale(self) -> None:
        try:
            pid = int(self.path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return
        try:
            os.kill(pid, 0)
        except OSError:
            self.path.unlink(missing_ok=True)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def stale_people(scraper: CuriusScraper, refresh_hours: float, limit: int | None) -> list[sqlite3.Row]:
    if scraper.count("users") == 0:
        scraper.known_people()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=refresh_hours)
    # ponytail: after global activity ingest, prior activity is the cheap proxy for deeper per-user refreshes.
    rows = scraper.conn.execute(
        """
        WITH activity AS (
            SELECT user_id, max(activity_at) AS latest_activity
            FROM (
                SELECT user_id, max(saved_at) AS activity_at FROM saved_links GROUP BY user_id
                UNION ALL
                SELECT user_id, max(created_at) AS activity_at FROM highlights GROUP BY user_id
            )
            GROUP BY user_id
        )
        SELECT u.user_id, u.user_link, ps.completed_at, ps.updated_at, ps.error,
               activity.latest_activity
        FROM users u
        LEFT JOIN person_scrapes ps ON ps.user_id = u.user_id
        LEFT JOIN activity ON activity.user_id = u.user_id
        WHERE u.user_id IS NOT NULL
        ORDER BY ps.user_id IS NOT NULL,
                 activity.latest_activity IS NULL,
                 activity.latest_activity DESC,
                 coalesce(ps.completed_at, ps.updated_at), u.user_id
        """
    ).fetchall()
    def last_checked(row: sqlite3.Row) -> datetime | None:
        if row["completed_at"]:
            return parse_time(row["completed_at"])
        return parse_time(row["updated_at"]) if row["error"] else None
    picked = [row for row in rows if (last_checked(row) or datetime.min.replace(tzinfo=timezone.utc)) <= cutoff]
    return picked[:limit] if limit is not None else picked


def rebuild_frontpage(db_path: Path, site_out: Path) -> None:
    sys.path.insert(0, str(REPO_ROOT / "analysis"))
    from build_follower_site import load_frontpage, render_frontpage_html  # noqa: PLC0415

    site_out.parent.mkdir(parents=True, exist_ok=True)
    site_out.write_text(render_frontpage_html(load_frontpage(db_path)), encoding="utf-8")


def ingest_link_activity(scraper: CuriusScraper, activity: list[dict[str, Any]]) -> tuple[int, int]:
    users = links = 0
    with scraper.conn:
        for row in activity:
            user = row.get("user") or {}
            user_id = user.get("id")
            if user_id is None:
                continue
            scraper.upsert_user(user)
            users += 1
            for link in row.get("links") or []:
                link_id = link.get("id")
                if link_id is None:
                    continue
                scraper.upsert_link(link)
                scraper.conn.execute(
                    """
                    INSERT OR REPLACE INTO saved_links(
                        user_id, link_id, saved_at, modified_at, favorite, to_read, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        link_id,
                        link.get("createdDate"),
                        link.get("modifiedDate"),
                        as_bool(link.get("favorite")),
                        as_bool(link.get("toRead")),
                        utc_now(),
                    ),
                )
                links += 1
    return users, links


def scrape_link_activity(scraper: CuriusScraper) -> tuple[int, int]:
    scraper.status.update({"phase": "global link activity", "target_person": "", "saved_links": 0})
    scraper.write_progress()
    activity = scraper.request_json("/links/activity")
    if not isinstance(activity, list):
        raise RuntimeError("/links/activity did not return a list")
    users, links = ingest_link_activity(scraper, activity)
    scraper.status.update({"saved_links": links, "people_total": users, "people_done": users})
    scraper.write_progress()
    return users, links


def update_cycle(scraper: CuriusScraper, args: argparse.Namespace, cycle: int) -> int:
    scraper.status.update(
        {
            "state": "running",
            "phase": "pick stale users",
            "mode": "links/highlights updater",
            "refresh_hours": args.refresh_hours,
            "frontpage": str(args.site_out),
            "cycle": cycle,
            "next_sleep": "",
        }
    )
    scraper.write_progress()
    try:
        scrape_link_activity(scraper)
        rebuild_frontpage(args.db, args.site_out)
    except Exception as exc:  # ponytail: fall back to per-user refresh if the public activity feed flakes.
        scraper.record_error(str(exc), "links/activity")
    people = stale_people(scraper, args.refresh_hours, args.limit_users)
    scraper.status.update({"phase": "links/highlights", "people_total": len(people), "people_done": 0})
    scraper.write_progress()

    for idx, person in enumerate(people, 1):
        user_id = int(person["user_id"])
        user_link = str(person["user_link"] or user_id)
        scraper.status.update(
            {
                "current_user": user_link,
                "target_person": user_link,
                "people_done": idx - 1,
                "saved_links": 0,
                "highlight_pages": 0,
                "highlights": 0,
            }
        )
        scraper.write_progress()
        try:
            saved_count = scraper.scrape_saved_links(user_id, user_link)
            highlight_count, highlight_pages = scraper.scrape_highlights(user_id, user_link, args.max_highlight_pages)
            if args.max_highlight_pages is None:
                with scraper.conn:
                    scraper.mark_person_scraped(user_id, user_link, saved_count, highlight_count, highlight_pages)
            rebuild_frontpage(args.db, args.site_out)
        except Exception as exc:  # ponytail: keep the 24/7 loop moving; inspect errors in progress HTML.
            scraper.record_error(str(exc), user_link)
            with scraper.conn:
                scraper.mark_person_scraped(user_id, user_link, 0, 0, 0, str(exc)[:1000])
        scraper.status.update({"people_done": idx})
        scraper.write_progress()

    rebuild_frontpage(args.db, args.site_out)
    scraper.status.update({"state": "done", "phase": "cycle complete", "people_done": len(people)})
    scraper.write_progress()
    return len(people)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--progress-html", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--site-out", type=Path, default=DEFAULT_SITE_OUT)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--refresh-hours", type=float, default=6, help="refresh users older than this many hours")
    parser.add_argument("--limit-users", type=int, help="max stale users per cycle")
    parser.add_argument("--max-highlight-pages", type=int, help="testing cap; writes partial highlights and does not mark users fresh")
    parser.add_argument("--loop", action="store_true", help="keep updating forever")
    parser.add_argument("--sleep", type=float, default=600, help="seconds between loop cycles")
    parser.add_argument("--delay", type=float, default=0.2, help="seconds to sleep after each successful request")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "curius.sqlite"
        progress = Path(tmp) / "progress.html"
        site = Path(tmp) / "index.html"
        scraper = CuriusScraper(db, progress, 0, 5, "Curius link/highlight updater")
        with scraper.conn:
            scraper.upsert_user({"id": 1, "firstName": "Ada", "lastName": "L", "userLink": "ada"})
            scraper.upsert_user({"id": 2, "firstName": "Grace", "lastName": "H", "userLink": "grace"})
            scraper.upsert_user({"id": 3, "firstName": "Alan", "lastName": "T", "userLink": "alan"})
            scraper.upsert_user({"id": 4, "firstName": "Katherine", "lastName": "J", "userLink": "katherine"})
            scraper.upsert_link({"id": 9, "link": "https://example.com", "title": "Example"})
            scraper.upsert_link({"id": 10, "link": "https://example.net", "title": "Newer Example"})
            scraper.conn.execute("INSERT OR REPLACE INTO saved_links VALUES (?, ?, ?, ?, ?, ?, ?)", (1, 9, "2000-01-02T00:00:00+00:00", None, 0, 0, utc_now()))
            scraper.conn.execute("INSERT OR REPLACE INTO saved_links VALUES (?, ?, ?, ?, ?, ?, ?)", (4, 10, "2000-01-03T00:00:00+00:00", None, 0, 0, utc_now()))
            scraper.conn.execute(
                """
                INSERT OR REPLACE INTO highlights(
                    highlight_id, user_id, link_id, highlight_text, raw_highlight,
                    left_context, right_context, position, verified, created_at,
                    comment_json, mentions_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (101, 1, 9, "Small updates are easier to trust.", None, "", "", None, 1, "2000-01-02T00:00:00+00:00", None, None, utc_now()),
            )
            scraper.conn.execute(
                """
                INSERT OR REPLACE INTO person_scrapes(
                    user_id, user_link, saved_links_count, highlights_count,
                    highlight_pages, completed_at, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (1, "ada", 1, 1, 1, "2000-01-01T00:00:00+00:00", None, utc_now()),
            )
            scraper.conn.execute(
                """
                INSERT OR REPLACE INTO person_scrapes(
                    user_id, user_link, saved_links_count, highlights_count,
                    highlight_pages, completed_at, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (3, "alan", 0, 0, 0, "2999-01-01T00:00:00+00:00", None, utc_now()),
            )
            scraper.conn.execute(
                """
                INSERT OR REPLACE INTO person_scrapes(
                    user_id, user_link, saved_links_count, highlights_count,
                    highlight_pages, completed_at, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (4, "katherine", 1, 0, 0, "2000-01-01T00:00:00+00:00", None, utc_now()),
            )
        assert [int(row["user_id"]) for row in stale_people(scraper, 24, None)] == [2, 4, 1]
        assert stale_people(scraper, 24, 0) == []
        users, links = ingest_link_activity(scraper, [{
            "user": {"id": 5, "firstName": "Dorothy", "lastName": "V", "userLink": "dorothy"},
            "links": [{"id": 11, "link": "https://example.org", "title": "Global Example", "createdDate": "2000-01-04T00:00:00+00:00"}],
        }])
        assert (users, links) == (1, 1)
        assert scraper.count("links") == 3
        assert scraper.count("saved_links") == 3
        scraper.write_progress()
        assert "Curius link/highlight updater" in progress.read_text(encoding="utf-8")
        scraper.close()
        rebuild_frontpage(db, site)
        assert "frontpage-data" in site.read_text(encoding="utf-8")
        with FileLock(Path(tmp) / "test.lock"):
            assert (Path(tmp) / "test.lock").exists()
    print("self-test ok")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        self_test()
        return 0

    with FileLock(args.lock):
        scraper = CuriusScraper(args.db, args.progress_html, args.delay, args.timeout, "Curius link/highlight updater")
        try:
            cycle = 1
            while True:
                update_cycle(scraper, args, cycle)
                if not args.loop:
                    return 0
                scraper.status.update({"state": "sleeping", "phase": "waiting", "next_sleep": f"{args.sleep:g}s"})
                scraper.write_progress()
                time.sleep(args.sleep)
                cycle += 1
        except KeyboardInterrupt:
            scraper.status.update({"state": "interrupted", "phase": "stopped"})
            scraper.write_progress()
            return 130
        except Exception as exc:
            scraper.status.update({"state": "failed"})
            scraper.record_error(str(exc), "fatal")
            scraper.write_progress()
            raise
        finally:
            scraper.close()


if __name__ == "__main__":
    raise SystemExit(main())
