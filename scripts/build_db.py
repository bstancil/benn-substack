#!/usr/bin/env python3
"""
Rebuild data/substack.duckdb from the raw files in data/raw/.

The database is disposable: every run drops and rebuilds all tables by
scanning every dated snapshot, so history (traffic, per-post stat snapshots)
accumulates in the raw files, not in the DB.

Tables:
  posts                  one row per post (public metadata)
  post_content           post_id -> markdown + body_html
  post_engagement_history  public engagement per post per fetch (likes, comments, restacks)
  post_stats_history       private stats per post per fetch (opens, views, signups, ...)
  subscriber_timeseries  daily subscriber counts
  traffic_daily          daily site visits (deduped across fetches, latest wins)
Views:
  post_stats             newest stats snapshot per post
  post_engagement        newest engagement snapshot per post
  posts_overview         posts joined to latest stats + engagement
"""

import csv
import json
import re
from datetime import date, datetime
from pathlib import Path

import duckdb

from substack_api import ROOT_DIR

DB_PATH = ROOT_DIR / "data" / "substack.duckdb"
RAW_POSTS_DIR = ROOT_DIR / "data" / "raw" / "posts"
RAW_STATS_DIR = ROOT_DIR / "data" / "raw" / "stats"
POSTS_DIR = ROOT_DIR / "posts"

POST_STATS_FIELDS = [
    "deliveries", "opens", "open_rate", "sent", "clicks", "views",
    "signups", "subscribes", "signups_within_1_day", "subscriptions_within_1_day",
    "unsubscribes_within_1_day", "disables_within_1_day", "comments", "likes", "shares",
]


def parse_date(value):
    """Parse a date from the several formats that show up in this data."""
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) and not isinstance(value, datetime) else value.date()
    value = str(value).strip()
    for fmt in ("%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def to_num(value):
    if value is None or value == "":
        return None
    try:
        f = float(value)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def normalize_timeseries(data):
    """Normalize a timeseries to [(date, value)].

    Handles both list-of-dicts ({date: ..., <count>: ...}) and list-of-lists
    with a header row (the shape the old browser-console script consumed).
    """
    if not data:
        return []
    rows = []
    if isinstance(data[0], dict):
        for item in data:
            keys = list(item.keys())
            date_key = next((k for k in keys if "date" in k.lower()), keys[0])
            value_key = next(k for k in keys if k != date_key)
            rows.append((parse_date(item[date_key]), to_num(item[value_key])))
    else:
        # Skip a header row like ["date", "emails"]
        start = 1 if len(data[0]) >= 2 and to_num(data[0][1]) is None else 0
        for item in data[start:]:
            rows.append((parse_date(item[0]), to_num(item[1])))
    return rows


def stats_snapshot_dirs():
    if not RAW_STATS_DIR.exists():
        return []
    return sorted(d for d in RAW_STATS_DIR.iterdir() if d.is_dir())


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- table builders ----------

def build_posts(con):
    con.execute("""
        CREATE TABLE posts (
            post_id BIGINT PRIMARY KEY, slug VARCHAR, title VARCHAR, subtitle VARCHAR,
            description VARCHAR, post_date TIMESTAMP, type VARCHAR, audience VARCHAR,
            canonical_url VARCHAR, wordcount INTEGER, cover_image VARCHAR,
            podcast_url VARCHAR, tags VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE post_content (
            post_id BIGINT PRIMARY KEY, slug VARCHAR, markdown VARCHAR, body_html VARCHAR
        )
    """)

    count = 0
    for path in sorted(RAW_POSTS_DIR.glob("*.json")):
        p = load_json(path)
        tags = ", ".join(t.get("name", "") for t in (p.get("postTags") or []))
        con.execute(
            "INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                p["id"], p["slug"], p.get("title"), p.get("subtitle"),
                p.get("description"), parse_date(p["post_date"]), p.get("type"),
                p.get("audience"), p.get("canonical_url"), p.get("wordcount"),
                p.get("cover_image"), p.get("podcast_url"), tags,
            ],
        )
        md_path = POSTS_DIR / f"{p['id']}.{p['slug']}.md"
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else None
        con.execute(
            "INSERT INTO post_content VALUES (?, ?, ?, ?)",
            [p["id"], p["slug"], markdown, p.get("body_html")],
        )
        count += 1
    print(f"  posts: {count} rows")


def build_engagement(con):
    con.execute("""
        CREATE TABLE post_engagement_history (
            fetched_date DATE, post_id BIGINT, reaction_count INTEGER,
            comment_count INTEGER, child_comment_count INTEGER, restacks INTEGER
        )
    """)
    count = 0
    for snap_dir in stats_snapshot_dirs():
        archive_path = snap_dir / "archive.json"
        if not archive_path.exists():
            continue
        fetched = parse_date(snap_dir.name)
        for item in load_json(archive_path):
            con.execute(
                "INSERT INTO post_engagement_history VALUES (?, ?, ?, ?, ?, ?)",
                [
                    fetched, item["id"], to_num(item.get("reaction_count")),
                    to_num(item.get("comment_count")), to_num(item.get("child_comment_count")),
                    to_num(item.get("restacks")),
                ],
            )
            count += 1
    print(f"  post_engagement_history: {count} rows")


def build_post_stats(con):
    cols = ", ".join(
        f"{f} {'DOUBLE' if f == 'open_rate' else 'INTEGER'}" for f in POST_STATS_FIELDS
    )
    con.execute(f"""
        CREATE TABLE post_stats_history (
            fetched_date DATE, post_id BIGINT, title VARCHAR, post_date TIMESTAMP,
            {cols}
        )
    """)

    count = 0
    # email_stats rows enriched with per-post draft stats, one layer per snapshot
    for snap_dir in stats_snapshot_dirs():
        email_path = snap_dir / "email_stats.json"
        if not email_path.exists():
            continue
        fetched = parse_date(snap_dir.name)
        detail = load_json(snap_dir / "post_stats.json") if (snap_dir / "post_stats.json").exists() else {}
        for row in load_json(email_path):
            merged = {**row, **detail.get(str(row["post_id"]), {})}
            values = [to_num(merged.get(f)) for f in POST_STATS_FIELDS]
            con.execute(
                f"INSERT INTO post_stats_history VALUES (?, ?, ?, ?, {', '.join('?' * len(POST_STATS_FIELDS))})",
                [fetched, row["post_id"], row.get("title"), parse_date(row["post_date"]), *values],
            )
            count += 1
    print(f"  post_stats_history: {count} rows")


def build_subscribers(con):
    con.execute("CREATE TABLE subscriber_timeseries (date DATE, subscribers INTEGER)")

    # The newest snapshot contains the full history
    rows = []
    for snap_dir in reversed(stats_snapshot_dirs()):
        if (snap_dir / "subscribers.json").exists():
            rows = normalize_timeseries(load_json(snap_dir / "subscribers.json"))
            break

    for d, v in rows:
        con.execute("INSERT INTO subscriber_timeseries VALUES (?, ?)", [d, v])
    print(f"  subscriber_timeseries: {len(rows)} rows")


def build_traffic(con):
    con.execute("CREATE TABLE traffic_daily (date DATE, visits INTEGER)")

    # date -> (fetched_date, visits); later fetches win on overlap
    merged = {}

    for snap_dir in stats_snapshot_dirs():
        traffic_path = snap_dir / "traffic.json"
        if not traffic_path.exists():
            continue
        fetched = parse_date(snap_dir.name)
        for d, v in normalize_timeseries(load_json(traffic_path)):
            if d not in merged or fetched >= merged[d][0]:
                merged[d] = (fetched, v)

    for d in sorted(merged):
        con.execute("INSERT INTO traffic_daily VALUES (?, ?)", [d, merged[d][1]])
    print(f"  traffic_daily: {len(merged)} rows")


def build_visitor_sources(con):
    con.execute("""
        CREATE TABLE visitor_sources_monthly (
            month DATE, source VARCHAR, source_category VARCHAR,
            views INTEGER, users INTEGER, free_signups INTEGER, subscribed INTEGER
        )
    """)
    # newest snapshot wins wholesale — each snapshot carries the full history
    count = 0
    for snap_dir in reversed(stats_snapshot_dirs()):
        path = snap_dir / "visitor_sources.json"
        if not path.exists():
            continue
        for month, rows in load_json(path).items():
            for r in rows:
                con.execute(
                    "INSERT INTO visitor_sources_monthly VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        parse_date(month), r.get("source"), r.get("source_category"),
                        to_num(r.get("views")), to_num(r.get("users")),
                        to_num(r.get("free_signup")), to_num(r.get("subscribed")),
                    ],
                )
                count += 1
        break
    print(f"  visitor_sources_monthly: {count} rows")


def normalize_column(name):
    """'Emails opened (6mo)' -> 'emails_opened_6mo'."""
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


def build_subscriber_table(con):
    """Load the newest audience-dashboard subscriber export (if present) as a
    one-row-per-subscriber table, plus a subscriber_sources rollup view.

    The DB and exports live under data/ (gitignored) — subscriber data stays
    local, it just isn't aggregated away.
    """
    exports_dir = ROOT_DIR / "data" / "subscriber-exports"
    latest = max(exports_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, default=None) \
        if exports_dir.exists() else None

    if latest is None:
        con.execute("""
            CREATE TABLE subscribers (
                email VARCHAR, start_date TIMESTAMP, first_paid_date TIMESTAMP,
                subscription_source_free VARCHAR, subscription_source_paid VARCHAR,
                activity VARCHAR, country VARCHAR
            )
        """)
        print("  subscribers: 0 rows (no export in data/subscriber-exports/)")
    else:
        with open(latest, encoding="utf-8") as f:
            header = next(csv.reader(f))
        selects = []
        for col in header:
            alias = normalize_column(col)
            if alias == "revenue":
                selects.append(f'TRY_CAST(replace("{col}", \'$\', \'\') AS DOUBLE) AS revenue')
            else:
                selects.append(f'"{col}" AS {alias}')
        con.execute(
            f"CREATE TABLE subscribers AS SELECT {', '.join(selects)} "
            f"FROM read_csv(?, header = true)",
            [str(latest)],
        )
        n = con.execute("SELECT count(*) FROM subscribers").fetchone()[0]
        print(f"  subscribers: {n} rows (from {latest.name})")

    con.execute("""
        CREATE VIEW subscriber_sources AS
        SELECT
            date_trunc('month', start_date)::DATE AS signup_month,
            coalesce(nullif(trim(subscription_source_free), ''), 'unknown') AS source,
            count(*)::INTEGER AS subscribers,
            count(first_paid_date)::INTEGER AS paid
        FROM subscribers
        WHERE start_date IS NOT NULL
        GROUP BY 1, 2
    """)


def build_subscriber_events(con):
    """Load the subscribe/unsubscribe event log, if a local fetcher
    (scripts/local/) downloads one. Newest snapshot wins wholesale — the log
    is append-only and each download contains the full history."""
    con.execute("""
        CREATE TABLE subscriber_events (
            captured_at TIMESTAMP, event VARCHAR, occurred_at TIMESTAMP, email VARCHAR
        )
    """)
    for snap_dir in reversed(stats_snapshot_dirs()):
        path = snap_dir / "subscriber_events.csv"
        if not path.exists():
            continue
        con.execute("""
            INSERT INTO subscriber_events
            SELECT
                TRY_CAST(replace(captured_at, 'Z', '') AS TIMESTAMP),
                trim(event),
                TRY_CAST(replace(occurred_at, 'Z', '') AS TIMESTAMP),
                trim(email)
            FROM read_csv(?, header = true, all_varchar = true)
        """, [str(path)])
        break
    n = con.execute("SELECT count(*) FROM subscriber_events").fetchone()[0]
    print(f"  subscriber_events: {n} rows")


def build_views(con):
    con.execute("""
        CREATE VIEW post_stats AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY post_id ORDER BY fetched_date DESC) AS rn
            FROM post_stats_history
        ) WHERE rn = 1
    """)
    con.execute("""
        CREATE VIEW post_engagement AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY post_id ORDER BY fetched_date DESC) AS rn
            FROM post_engagement_history
        ) WHERE rn = 1
    """)
    con.execute("""
        CREATE VIEW posts_overview AS
        SELECT
            p.post_id, p.slug, p.title, p.subtitle, p.post_date, p.wordcount,
            p.canonical_url, p.tags,
            s.deliveries, s.opens, s.open_rate, s.views, s.clicks,
            s.signups, s.subscribes, s.signups_within_1_day,
            s.unsubscribes_within_1_day, s.fetched_date AS stats_fetched_date,
            e.reaction_count AS likes, e.comment_count AS comments, e.restacks
        FROM posts p
        LEFT JOIN post_stats s USING (post_id)
        LEFT JOIN post_engagement e USING (post_id)
        ORDER BY p.post_date DESC
    """)
    print("  views: post_stats, post_engagement, posts_overview")


def build_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DB_PATH.with_suffix(".duckdb.tmp")
    tmp_path.unlink(missing_ok=True)

    print(f"Building {DB_PATH.name}...")
    con = duckdb.connect(str(tmp_path))
    try:
        build_posts(con)
        build_engagement(con)
        build_post_stats(con)
        build_subscribers(con)
        build_traffic(con)
        build_visitor_sources(con)
        build_subscriber_table(con)
        build_subscriber_events(con)
        build_views(con)
    finally:
        con.close()

    tmp_path.replace(DB_PATH)
    print(f"Done: {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build_db())
