#!/usr/bin/env python3
"""Collect GitHub repository traffic metrics into SQLite."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_OWNER = "4stm4"
DEFAULT_REPOS = (
    "4stm4",
    "nanodhcp",
    "tinyWiFi",
    "nervum",
    "testum",
    "pyjobkit",
    "ehatrom",
    "ocultum",
)
DEFAULT_DB_PATH = Path("data/github_traffic.sqlite3")
DEFAULT_API_VERSION = "2026-03-10"
API_BASE_URL = "https://api.github.com"


class GitHubApiError(RuntimeError):
    """Raised when GitHub returns an endpoint-level error."""


@dataclass
class RepoResult:
    repo: str
    rows: dict[str, int]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GitHub traffic metrics into SQLite.")
    parser.add_argument(
        "--owner",
        default=os.environ.get("GITHUB_OWNER", DEFAULT_OWNER),
        help="GitHub repository owner. Defaults to GITHUB_OWNER or 4stm4.",
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repos",
        help="Repository name to collect. Repeat to override the default repository list.",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("GITHUB_TRAFFIC_DB", str(DEFAULT_DB_PATH)),
        help="SQLite database path. Defaults to data/github_traffic.sqlite3.",
    )
    parser.add_argument(
        "--api-version",
        default=os.environ.get("GITHUB_API_VERSION", DEFAULT_API_VERSION),
        help="GitHub REST API version header.",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=20,
        help="HTTP timeout per request in seconds.",
    )
    return parser.parse_args()


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS collector_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            owner TEXT NOT NULL,
            status TEXT NOT NULL,
            repos_requested INTEGER NOT NULL,
            repos_succeeded INTEGER NOT NULL DEFAULT 0,
            repos_failed INTEGER NOT NULL DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS repo_views (
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            collected_at TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            PRIMARY KEY (owner, repo, timestamp),
            FOREIGN KEY (run_id) REFERENCES collector_runs (id)
        );

        CREATE TABLE IF NOT EXISTS repo_clones (
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            collected_at TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            PRIMARY KEY (owner, repo, timestamp),
            FOREIGN KEY (run_id) REFERENCES collector_runs (id)
        );

        CREATE TABLE IF NOT EXISTS repo_referrers (
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            referrer TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            collected_at TEXT NOT NULL,
            collection_date TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            PRIMARY KEY (owner, repo, referrer, collection_date),
            FOREIGN KEY (run_id) REFERENCES collector_runs (id)
        );

        CREATE TABLE IF NOT EXISTS repo_paths (
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            collected_at TEXT NOT NULL,
            collection_date TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            PRIMARY KEY (owner, repo, path, collection_date),
            FOREIGN KEY (run_id) REFERENCES collector_runs (id)
        );

        CREATE INDEX IF NOT EXISTS idx_repo_views_repo_timestamp
            ON repo_views (owner, repo, timestamp);

        CREATE INDEX IF NOT EXISTS idx_repo_clones_repo_timestamp
            ON repo_clones (owner, repo, timestamp);

        CREATE INDEX IF NOT EXISTS idx_repo_referrers_repo_date
            ON repo_referrers (owner, repo, collection_date);

        CREATE INDEX IF NOT EXISTS idx_repo_paths_repo_date
            ON repo_paths (owner, repo, collection_date);
        """
    )
    conn.commit()


def start_run(conn: sqlite3.Connection, owner: str, repos_requested: int, started_at: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO collector_runs (started_at, owner, status, repos_requested)
        VALUES (?, ?, ?, ?)
        """,
        (started_at, owner, "running", repos_requested),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    repos_succeeded: int,
    repos_failed: int,
    notes: str | None,
) -> None:
    conn.execute(
        """
        UPDATE collector_runs
        SET completed_at = ?, status = ?, repos_succeeded = ?, repos_failed = ?, notes = ?
        WHERE id = ?
        """,
        (utc_now(), status, repos_succeeded, repos_failed, notes, run_id),
    )
    conn.commit()


def github_get(
    token: str,
    owner: str,
    repo: str,
    endpoint: str,
    query: dict[str, str] | None,
    timeout: int,
    api_version: str,
) -> Any:
    url = f"{API_BASE_URL}/repos/{owner}/{repo}/{endpoint}"
    if query:
        url = f"{url}?{urlencode(query)}"

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "4stm4-github-traffic-collector",
            "X-GitHub-Api-Version": api_version,
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubApiError(format_http_error(exc.code, detail)) from exc
    except URLError as exc:
        raise GitHubApiError(f"network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubApiError(f"invalid JSON response: {exc}") from exc


def format_http_error(status_code: int, detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        payload = {}

    message = payload.get("message") if isinstance(payload, dict) else None
    if message:
        return f"HTTP {status_code}: {message}"
    return f"HTTP {status_code}: {detail[:200]}"


def int_value(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if value is None:
        return 0
    return int(value)


def collect_views(
    conn: sqlite3.Connection,
    token: str,
    owner: str,
    repo: str,
    run_id: int,
    collected_at: str,
    timeout: int,
    api_version: str,
) -> int:
    data = github_get(token, owner, repo, "traffic/views", {"per": "day"}, timeout, api_version)
    views = data.get("views", []) if isinstance(data, dict) else []
    rows = 0

    for item in views:
        timestamp = item.get("timestamp")
        if not timestamp:
            continue
        conn.execute(
            """
            INSERT INTO repo_views (owner, repo, timestamp, count, uniques, collected_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner, repo, timestamp) DO UPDATE SET
                count = excluded.count,
                uniques = excluded.uniques,
                collected_at = excluded.collected_at,
                run_id = excluded.run_id
            """,
            (
                owner,
                repo,
                timestamp,
                int_value(item, "count"),
                int_value(item, "uniques"),
                collected_at,
                run_id,
            ),
        )
        rows += 1

    return rows


def collect_clones(
    conn: sqlite3.Connection,
    token: str,
    owner: str,
    repo: str,
    run_id: int,
    collected_at: str,
    timeout: int,
    api_version: str,
) -> int:
    data = github_get(token, owner, repo, "traffic/clones", {"per": "day"}, timeout, api_version)
    clones = data.get("clones", []) if isinstance(data, dict) else []
    rows = 0

    for item in clones:
        timestamp = item.get("timestamp")
        if not timestamp:
            continue
        conn.execute(
            """
            INSERT INTO repo_clones (owner, repo, timestamp, count, uniques, collected_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner, repo, timestamp) DO UPDATE SET
                count = excluded.count,
                uniques = excluded.uniques,
                collected_at = excluded.collected_at,
                run_id = excluded.run_id
            """,
            (
                owner,
                repo,
                timestamp,
                int_value(item, "count"),
                int_value(item, "uniques"),
                collected_at,
                run_id,
            ),
        )
        rows += 1

    return rows


def collect_referrers(
    conn: sqlite3.Connection,
    token: str,
    owner: str,
    repo: str,
    run_id: int,
    collected_at: str,
    timeout: int,
    api_version: str,
) -> int:
    data = github_get(token, owner, repo, "traffic/popular/referrers", None, timeout, api_version)
    if not isinstance(data, list):
        raise GitHubApiError("unexpected referrers response shape")

    collection_date = collected_at[:10]
    rows = 0
    for item in data:
        referrer = item.get("referrer")
        if not referrer:
            continue
        conn.execute(
            """
            INSERT INTO repo_referrers (
                owner, repo, referrer, count, uniques, collected_at, collection_date, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner, repo, referrer, collection_date) DO UPDATE SET
                count = excluded.count,
                uniques = excluded.uniques,
                collected_at = excluded.collected_at,
                run_id = excluded.run_id
            """,
            (
                owner,
                repo,
                referrer,
                int_value(item, "count"),
                int_value(item, "uniques"),
                collected_at,
                collection_date,
                run_id,
            ),
        )
        rows += 1

    return rows


def collect_paths(
    conn: sqlite3.Connection,
    token: str,
    owner: str,
    repo: str,
    run_id: int,
    collected_at: str,
    timeout: int,
    api_version: str,
) -> int:
    data = github_get(token, owner, repo, "traffic/popular/paths", None, timeout, api_version)
    if not isinstance(data, list):
        raise GitHubApiError("unexpected paths response shape")

    collection_date = collected_at[:10]
    rows = 0
    for item in data:
        path = item.get("path")
        if not path:
            continue
        conn.execute(
            """
            INSERT INTO repo_paths (
                owner, repo, path, title, count, uniques, collected_at, collection_date, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner, repo, path, collection_date) DO UPDATE SET
                title = excluded.title,
                count = excluded.count,
                uniques = excluded.uniques,
                collected_at = excluded.collected_at,
                run_id = excluded.run_id
            """,
            (
                owner,
                repo,
                path,
                item.get("title") or "",
                int_value(item, "count"),
                int_value(item, "uniques"),
                collected_at,
                collection_date,
                run_id,
            ),
        )
        rows += 1

    return rows


Collector = Callable[[sqlite3.Connection, str, str, str, int, str, int, str], int]


def collect_repo(
    conn: sqlite3.Connection,
    token: str,
    owner: str,
    repo: str,
    run_id: int,
    collected_at: str,
    timeout: int,
    api_version: str,
) -> RepoResult:
    collectors: tuple[tuple[str, Collector], ...] = (
        ("views", collect_views),
        ("clones", collect_clones),
        ("referrers", collect_referrers),
        ("paths", collect_paths),
    )
    rows: dict[str, int] = {}
    errors: list[str] = []

    for label, collector in collectors:
        try:
            rows[label] = collector(conn, token, owner, repo, run_id, collected_at, timeout, api_version)
            conn.commit()
        except GitHubApiError as exc:
            errors.append(f"{label}: {exc}")
        except Exception as exc:  # Keep the run alive for the remaining repositories.
            errors.append(f"{label}: {type(exc).__name__}: {exc}")

    return RepoResult(repo=repo, rows=rows, errors=errors)


def print_summary(run_id: int, owner: str, collected_at: str, results: list[RepoResult]) -> None:
    ok_count = sum(1 for result in results if result.ok)
    failed_count = len(results) - ok_count

    print("GitHub traffic collection complete")
    print(f"run_id={run_id} owner={owner} collected_at={collected_at}")
    print(f"repos={len(results)} ok={ok_count} failed={failed_count}")

    for result in results:
        status = "ok" if result.ok else "partial"
        row_counts = ", ".join(f"{key}={value}" for key, value in result.rows.items()) or "rows=0"
        print(f"- {result.repo}: {status} ({row_counts})")
        for error in result.errors:
            print(f"  error: {error}")


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required.", file=sys.stderr)
        return 2

    owner = args.owner
    repos = tuple(args.repos) if args.repos else DEFAULT_REPOS
    collected_at = utc_now()

    conn = connect_database(Path(args.database))
    try:
        create_schema(conn)
        run_id = start_run(conn, owner, len(repos), collected_at)

        results = [
            collect_repo(conn, token, owner, repo, run_id, collected_at, args.timeout, args.api_version)
            for repo in repos
        ]
        repos_succeeded = sum(1 for result in results if result.ok)
        repos_failed = len(results) - repos_succeeded
        status = "ok" if repos_failed == 0 else "partial"
        notes = None
        if repos_failed:
            notes = json.dumps(
                {result.repo: result.errors for result in results if result.errors},
                sort_keys=True,
            )

        finish_run(conn, run_id, status, repos_succeeded, repos_failed, notes)
        print_summary(run_id, owner, collected_at, results)
        return 0 if repos_failed == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
