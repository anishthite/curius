#!/usr/bin/env python3
"""Scrape public Curius users, follows, links, and highlights into SQLite."""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://curius.app/api"
DEFAULT_DB = REPO_ROOT / "data/curius.sqlite"
DEFAULT_PROGRESS = REPO_ROOT / "data/curius_scrape_progress.html"
USER_AGENT = "curius/0.1 (+local public-data scrape)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def as_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def sqlite_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return as_json(value)
    return value


def clean_metadata(value: Any) -> str | None:
    if not isinstance(value, dict):
        return as_json(value)
    # ponytail: skip full page text; keep link identity/metadata small. Add a documents table if needed.
    return as_json({k: v for k, v in value.items() if k != "full_text"})


class CuriusScraper:
    def __init__(self, db_path: Path, progress_path: Path, delay: float, timeout: int, progress_title: str = "Curius scrape progress") -> None:
        self.db_path = db_path
        self.progress_path = progress_path
        self.progress_title = progress_title
        self.delay = delay
        self.timeout = timeout
        self.started_at = utc_now()
        self.status: dict[str, Any] = {
            "state": "starting",
            "phase": "init",
            "started_at": self.started_at,
            "updated_at": self.started_at,
            "requests": 0,
            "users_total": 0,
            "users_done": 0,
            "people_total": 0,
            "people_done": 0,
            "current_user": "",
            "target_person": "",
            "saved_links": 0,
            "highlight_pages": 0,
            "highlights": 0,
            "last_url": "",
            "last_error": "",
            "mode": "",
            "refresh_hours": "",
            "frontpage": "",
            "cycle": "",
            "next_sleep": "",
            "errors": [],
        }
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.init_db()
        self.write_progress()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                user_link TEXT UNIQUE,
                first_name TEXT,
                last_name TEXT,
                school TEXT,
                github TEXT,
                twitter TEXT,
                website TEXT,
                created_at TEXT,
                modified_at TEXT,
                last_online TEXT,
                views INTEGER,
                num_followers INTEGER,
                raw_json TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS follows (
                follower_user_id INTEGER NOT NULL,
                followed_user_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (follower_user_id, followed_user_id)
            );
            CREATE TABLE IF NOT EXISTS links (
                link_id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                snippet TEXT,
                created_by INTEGER,
                created_at TEXT,
                modified_at TEXT,
                last_crawled TEXT,
                read_count INTEGER,
                metadata_json TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_links (
                user_id INTEGER NOT NULL,
                link_id INTEGER NOT NULL,
                saved_at TEXT,
                modified_at TEXT,
                favorite INTEGER,
                to_read INTEGER,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, link_id)
            );
            CREATE TABLE IF NOT EXISTS highlights (
                highlight_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                link_id INTEGER NOT NULL,
                highlight_text TEXT,
                raw_highlight TEXT,
                left_context TEXT,
                right_context TEXT,
                position INTEGER,
                verified INTEGER,
                created_at TEXT,
                comment_json TEXT,
                mentions_json TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scrape_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                phase TEXT,
                target TEXT,
                url TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS person_scrapes (
                user_id INTEGER PRIMARY KEY,
                user_link TEXT,
                saved_links_count INTEGER,
                highlights_count INTEGER,
                highlight_pages INTEGER,
                completed_at TEXT,
                error TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_follows_followed ON follows(followed_user_id);
            CREATE INDEX IF NOT EXISTS idx_saved_links_link ON saved_links(link_id);
            CREATE INDEX IF NOT EXISTS idx_highlights_user ON highlights(user_id);
            CREATE INDEX IF NOT EXISTS idx_highlights_link ON highlights(link_id);
            """
        )
        self.conn.commit()

    def request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{BASE_URL}{path}{query}"
        self.status["last_url"] = url
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        for attempt in range(6):
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self.status["requests"] += 1
                    data = json.load(response)
                if self.delay:
                    time.sleep(self.delay)
                return data
            except urllib.error.HTTPError as exc:
                body = exc.read(300).decode("utf-8", "replace")
                if exc.code == 404:
                    raise RuntimeError(f"404 for {url}: {body}") from exc
                wait = min(30, 2**attempt)
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 5:
                    raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
                time.sleep(wait)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == 5:
                    raise RuntimeError(f"request failed for {url}: {exc}") from exc
                time.sleep(min(30, 2**attempt))
        raise RuntimeError(f"request failed for {url}")

    def record_error(self, error: str, target: str = "") -> None:
        error = error[:1000]
        self.status["last_error"] = error
        self.status["errors"].append(f"{utc_now()} · {target} · {error}")
        self.status["errors"] = self.status["errors"][-20:]
        self.conn.execute(
            "INSERT INTO scrape_errors(at, phase, target, url, error) VALUES (?, ?, ?, ?, ?)",
            (utc_now(), self.status.get("phase"), target, self.status.get("last_url"), error),
        )
        self.conn.commit()

    def upsert_user(self, user: dict[str, Any]) -> None:
        user_id = user.get("id")
        if user_id is None:
            return
        self.conn.execute(
            """
            INSERT INTO users (
                user_id, user_link, first_name, last_name, school, github, twitter, website,
                created_at, modified_at, last_online, views, num_followers, raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_link=excluded.user_link,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                school=coalesce(excluded.school, users.school),
                github=coalesce(excluded.github, users.github),
                twitter=coalesce(excluded.twitter, users.twitter),
                website=coalesce(excluded.website, users.website),
                created_at=coalesce(excluded.created_at, users.created_at),
                modified_at=coalesce(excluded.modified_at, users.modified_at),
                last_online=coalesce(excluded.last_online, users.last_online),
                views=coalesce(excluded.views, users.views),
                num_followers=coalesce(excluded.num_followers, users.num_followers),
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                user.get("userLink"),
                user.get("firstName"),
                user.get("lastName"),
                user.get("school"),
                user.get("github"),
                user.get("twitter"),
                user.get("website"),
                user.get("createdDate"),
                user.get("modifiedDate"),
                user.get("lastOnline"),
                user.get("views"),
                user.get("numFollowers"),
                as_json(user),
                utc_now(),
            ),
        )

    def upsert_link(self, link: dict[str, Any]) -> None:
        link_id = link.get("id")
        if link_id is None:
            return
        self.conn.execute(
            """
            INSERT INTO links (
                link_id, url, title, snippet, created_by, created_at, modified_at,
                last_crawled, read_count, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(link_id) DO UPDATE SET
                url=coalesce(excluded.url, links.url),
                title=coalesce(excluded.title, links.title),
                snippet=coalesce(excluded.snippet, links.snippet),
                created_by=coalesce(excluded.created_by, links.created_by),
                created_at=coalesce(excluded.created_at, links.created_at),
                modified_at=coalesce(excluded.modified_at, links.modified_at),
                last_crawled=coalesce(excluded.last_crawled, links.last_crawled),
                read_count=coalesce(excluded.read_count, links.read_count),
                metadata_json=coalesce(excluded.metadata_json, links.metadata_json),
                updated_at=excluded.updated_at
            """,
            (
                link_id,
                link.get("link"),
                link.get("title"),
                link.get("snippet"),
                link.get("createdBy"),
                link.get("createdDate"),
                link.get("modifiedDate"),
                link.get("lastCrawled"),
                link.get("readCount"),
                clean_metadata(link.get("metadata")),
                utc_now(),
            ),
        )

    def count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    def scrape_social_graph(self, limit_users: int | None = None) -> None:
        self.status.update({"state": "running", "phase": "users/all"})
        self.write_progress()
        users = self.request_json("/users/all").get("users", [])
        if limit_users:
            users = users[:limit_users]
        self.status["users_total"] = len(users)
        with self.conn:
            for user in users:
                self.upsert_user(user)
        self.write_progress()

        for idx, user in enumerate(users, 1):
            user_link = user.get("userLink")
            user_id = user.get("id")
            self.status.update(
                {"phase": "social graph", "users_done": idx - 1, "current_user": user_link or user_id}
            )
            self.write_progress()
            if not user_link or user_id is None:
                continue
            try:
                profile = self.request_json(f"/users/{urllib.parse.quote(str(user_link), safe='')}").get("user")
                if not profile:
                    continue
                following = profile.get("followingUsers") or []
                with self.conn:
                    self.upsert_user(profile)
                    self.conn.execute("DELETE FROM follows WHERE follower_user_id = ?", (profile["id"],))
                    for followed in following:
                        self.upsert_user(followed)
                        followed_id = followed.get("id")
                        if followed_id is not None:
                            self.conn.execute(
                                """
                                INSERT OR REPLACE INTO follows(follower_user_id, followed_user_id, updated_at)
                                VALUES (?, ?, ?)
                                """,
                                (profile["id"], followed_id, utc_now()),
                            )
            except Exception as exc:  # keep long crawl moving
                self.record_error(str(exc), str(user_link))
            self.status.update({"users_done": idx, "follows": self.count("follows")})
            self.write_progress()

    def resolve_person(self, person: str) -> tuple[int, str]:
        self.status.update({"phase": "resolve person", "target_person": person})
        if person.isdigit():
            row = self.conn.execute("SELECT user_link FROM users WHERE user_id = ?", (int(person),)).fetchone()
            return int(person), row["user_link"] if row and row["user_link"] else person
        profile = self.request_json(f"/users/{urllib.parse.quote(person, safe='')}").get("user")
        if not profile or profile.get("id") is None:
            raise RuntimeError(f"No Curius user found for {person!r}")
        with self.conn:
            self.upsert_user(profile)
        return int(profile["id"]), str(profile.get("userLink") or person)

    def scrape_saved_links(self, user_id: int, label: str) -> int:
        self.status.update({"phase": "saved links", "target_person": label})
        self.write_progress()
        links = self.request_json(f"/users/{user_id}/searchLinks").get("links", [])
        with self.conn:
            self.conn.execute("DELETE FROM saved_links WHERE user_id = ?", (user_id,))
            for link in links:
                self.upsert_link(link)
                if link.get("id") is None:
                    continue
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO saved_links(
                        user_id, link_id, saved_at, modified_at, favorite, to_read, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        link.get("id"),
                        link.get("createdDate"),
                        link.get("modifiedDate"),
                        as_bool(link.get("favorite")),
                        as_bool(link.get("toRead")),
                        utc_now(),
                    ),
                )
        self.status["saved_links"] = len(links)
        self.write_progress()
        return len(links)

    def scrape_highlights(self, user_id: int, label: str, max_pages: int | None = None) -> tuple[int, int]:
        self.status.update({"phase": "highlights", "target_person": label})
        self.write_progress()
        highlights: list[dict[str, Any]] = []
        page = 0
        while True:
            if max_pages is not None and page >= max_pages:
                break
            batch = self.request_json("/snippets", {"uid": user_id, "page": page}).get("highlights", [])
            if not batch:
                break
            highlights.extend(batch)
            page += 1
            self.status.update({"highlight_pages": page, "highlights": len(highlights)})
            self.write_progress()

        with self.conn:
            self.conn.execute("DELETE FROM highlights WHERE user_id = ?", (user_id,))
            for highlight in highlights:
                link = highlight.get("link") or {}
                user = highlight.get("user") or {}
                self.upsert_link(link)
                self.upsert_user(user)
                if highlight.get("id") is None or highlight.get("linkId") is None:
                    continue
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO highlights(
                        highlight_id, user_id, link_id, highlight_text, raw_highlight,
                        left_context, right_context, position, verified, created_at,
                        comment_json, mentions_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        highlight.get("id"),
                        highlight.get("userId") or user_id,
                        highlight.get("linkId"),
                        sqlite_value(highlight.get("highlight")),
                        sqlite_value(highlight.get("rawHighlight")),
                        sqlite_value(highlight.get("leftContext")),
                        sqlite_value(highlight.get("rightContext")),
                        sqlite_value(highlight.get("position")),
                        as_bool(highlight.get("verified")),
                        highlight.get("createdDate"),
                        as_json(highlight.get("comment")),
                        as_json(highlight.get("mentions")),
                        utc_now(),
                    ),
                )
        self.status.update({"highlight_pages": page, "highlights": len(highlights)})
        self.write_progress()
        return len(highlights), page

    def scrape_person(self, person: str, max_highlight_pages: int | None = None) -> None:
        user_id, label = self.resolve_person(person)
        self.scrape_saved_links(user_id, label)
        self.scrape_highlights(user_id, label, max_highlight_pages)

    def known_people(self, limit: int | None = None) -> list[sqlite3.Row]:
        people = list(
            self.conn.execute(
                """
                SELECT user_id, user_link
                FROM users
                WHERE user_id IS NOT NULL
                ORDER BY user_id
                """
            )
        )
        if not people:
            self.status.update({"phase": "users/all"})
            users = self.request_json("/users/all").get("users", [])
            with self.conn:
                for user in users:
                    self.upsert_user(user)
            people = list(self.conn.execute("SELECT user_id, user_link FROM users ORDER BY user_id"))
        return people[:limit] if limit else people

    def person_done(self, user_id: int) -> bool:
        row = self.conn.execute(
            "SELECT completed_at FROM person_scrapes WHERE user_id = ?", (user_id,)
        ).fetchone()
        return bool(row and row["completed_at"])

    def mark_person_scraped(
        self,
        user_id: int,
        user_link: str,
        saved_count: int,
        highlight_count: int,
        highlight_pages: int,
        error: str | None = None,
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO person_scrapes(
                user_id, user_link, saved_links_count, highlights_count,
                highlight_pages, completed_at, error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_link=excluded.user_link,
                saved_links_count=excluded.saved_links_count,
                highlights_count=excluded.highlights_count,
                highlight_pages=excluded.highlight_pages,
                completed_at=excluded.completed_at,
                error=excluded.error,
                updated_at=excluded.updated_at
            """,
            (user_id, user_link, saved_count, highlight_count, highlight_pages, None if error else now, error, now),
        )

    def scrape_all_people(
        self,
        limit_users: int | None = None,
        max_highlight_pages: int | None = None,
        refresh: bool = False,
    ) -> None:
        people = self.known_people(limit_users)
        self.status.update({"state": "running", "phase": "all user links/highlights", "people_total": len(people)})
        self.write_progress()
        for idx, person in enumerate(people, 1):
            user_id = int(person["user_id"])
            user_link = str(person["user_link"] or user_id)
            if not refresh and max_highlight_pages is None and self.person_done(user_id):
                self.status.update({"people_done": idx, "target_person": user_link, "current_user": user_link})
                continue
            self.status.update(
                {
                    "phase": "all user links/highlights",
                    "people_done": idx - 1,
                    "target_person": user_link,
                    "current_user": user_link,
                    "saved_links": 0,
                    "highlight_pages": 0,
                    "highlights": 0,
                }
            )
            self.write_progress()
            try:
                saved_count = self.scrape_saved_links(user_id, user_link)
                highlight_count, highlight_pages = self.scrape_highlights(
                    user_id, user_link, max_highlight_pages
                )
                if max_highlight_pages is None:
                    with self.conn:
                        self.mark_person_scraped(
                            user_id, user_link, saved_count, highlight_count, highlight_pages
                        )
            except Exception as exc:
                self.record_error(str(exc), user_link)
                with self.conn:
                    self.mark_person_scraped(user_id, user_link, 0, 0, 0, str(exc)[:1000])
            self.status.update({"people_done": idx})
            self.write_progress()

    def write_progress(self) -> None:
        self.status["updated_at"] = utc_now()
        counts = {}
        for table in ["users", "follows", "links", "saved_links", "highlights", "person_scrapes", "scrape_errors"]:
            try:
                counts[table] = self.count(table)
            except sqlite3.Error:
                counts[table] = 0
        done = int(self.status.get("users_done") or 0)
        total = int(self.status.get("users_total") or 0)
        pct = f"{(done / total * 100):.1f}%" if total else "—"
        people_done = int(self.status.get("people_done") or 0)
        people_total = int(self.status.get("people_total") or 0)
        people_pct = f"{(people_done / people_total * 100):.1f}%" if people_total else "—"
        rows = {
            "state": self.status.get("state"),
            "phase": self.status.get("phase"),
            "started": self.status.get("started_at"),
            "updated": self.status.get("updated_at"),
            "requests": self.status.get("requests"),
            "social graph": f"{done}/{total} users ({pct})",
            "all-user links/highlights": f"{people_done}/{people_total} users ({people_pct})",
            "current user": self.status.get("current_user"),
            "target person": self.status.get("target_person"),
            "saved links this run": self.status.get("saved_links"),
            "highlight pages this run": self.status.get("highlight_pages"),
            "highlights this run": self.status.get("highlights"),
            "db": str(self.db_path),
            "last url": self.status.get("last_url"),
            "last error": self.status.get("last_error"),
            "mode": self.status.get("mode"),
            "refresh hours": self.status.get("refresh_hours"),
            "front page": self.status.get("frontpage"),
            "cycle": self.status.get("cycle"),
            "next sleep": self.status.get("next_sleep"),
        }
        table_rows = "\n".join(
            f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v or ''))}</td></tr>" for k, v in rows.items()
        )
        count_rows = "\n".join(
            f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in counts.items()
        )
        error_items = "\n".join(f"<li>{html.escape(err)}</li>" for err in self.status.get("errors", [])[-10:])
        title = html.escape(self.progress_title)
        self.progress_path.write_text(
            f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta http-equiv=\"refresh\" content=\"10\">
<title>{title}</title>
<style>
body {{ font: 14px/1.45 -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; color: #111; }}
h1 {{ font-size: 22px; margin-bottom: .2rem; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #eef; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ width: 190px; background: #f6f6f6; }}
code {{ background: #f1f1f1; padding: 1px 4px; border-radius: 3px; }}
.err {{ color: #9f1239; }}
</style>
</head>
<body>
<h1>{title} <span class=\"badge\">{html.escape(str(self.status.get('state')))}</span></h1>
<p>Auto-refreshes every 10 seconds. Database: <code>{html.escape(str(self.db_path))}</code></p>
<h2>Run</h2>
<table>{table_rows}</table>
<h2>Stored rows</h2>
<table><tr><th>table</th><th>rows</th></tr>{count_rows}</table>
<h2>Recent errors</h2>
<ul class=\"err\">{error_items or '<li>None.</li>'}</ul>
</body>
</html>
""",
            encoding="utf-8",
        )

    def close(self) -> None:
        self.conn.close()


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scraper = CuriusScraper(Path(tmp) / "curius.sqlite", Path(tmp) / "progress.html", 0, 5)
        with scraper.conn:
            scraper.upsert_user({"id": 1, "firstName": "Ada", "lastName": "L", "userLink": "ada"})
            scraper.upsert_user({"id": 2, "firstName": "Grace", "lastName": "H", "userLink": "grace"})
            scraper.upsert_link({"id": 9, "link": "https://example.com", "title": "Example"})
            scraper.conn.execute(
                "INSERT OR REPLACE INTO follows VALUES (?, ?, ?)", (1, 2, utc_now())
            )
        assert scraper.count("users") == 2
        assert scraper.count("links") == 1
        assert scraper.count("follows") == 1
        scraper.write_progress()
        assert "Curius scrape progress" in scraper.progress_path.read_text(encoding="utf-8")
        scraper.close()
    print("self-test ok")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape public Curius data into SQLite.")
    parser.add_argument("--person", action="append", help="userLink or uid to scrape saved links + highlights")
    parser.add_argument("--all-people", action="store_true", help="scrape saved links + highlights for every known user")
    parser.add_argument("--refresh-people", action="store_true", help="redo completed --all-people users")
    parser.add_argument("--skip-social", action="store_true", help="skip the full users/follows crawl")
    parser.add_argument("--limit-users", type=int, help="only crawl the first N users; useful for checks")
    parser.add_argument("--max-highlight-pages", type=int, help="cap highlight pages per person")
    parser.add_argument("--delay", type=float, default=0.2, help="seconds to sleep after each successful request")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--progress-html", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        self_test()
        return 0
    if args.skip_social and not args.person and not args.all_people:
        sys.exit("Nothing to do: remove --skip-social, add --person USERLINK_OR_UID, or add --all-people.")

    scraper = CuriusScraper(args.db, args.progress_html, args.delay, args.timeout)
    try:
        if not args.skip_social:
            scraper.scrape_social_graph(args.limit_users)
        if args.all_people:
            scraper.scrape_all_people(args.limit_users, args.max_highlight_pages, args.refresh_people)
        for person in args.person or []:
            scraper.scrape_person(person, args.max_highlight_pages)
        scraper.status.update({"state": "done", "phase": "complete"})
        scraper.write_progress()
        return 0
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
