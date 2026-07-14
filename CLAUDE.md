# benn-substack

Archive and analytics for the Substack publication configured in `.env`
(`SUBSTACK_URL`). Posts live as markdown in `posts/`; everything else lives
in a local DuckDB database at `data/substack.duckdb` (gitignored — the repo
is public, the stats are not).

To refresh all data: `python scripts/update.py` (see README.md). The database
is disposable — it's rebuilt from `data/raw/` on every run, so never treat it
as the only copy of anything.

## Querying the database

```bash
python3 -c "import duckdb; print(duckdb.connect('data/substack.duckdb', read_only=True).execute('...').df())"
```

or the `duckdb` CLI if installed: `duckdb -readonly data/substack.duckdb "..."`.
Use `read_only=True` — the pipeline may hold the write lock otherwise.

## Schema

| Table | Grain | Notes |
|---|---|---|
| `posts` | one row per post | public metadata: post_id, slug, title, subtitle, post_date, type, audience, canonical_url, wordcount, tags |
| `post_content` | one row per post | `markdown` and `body_html` full text |
| `post_engagement_history` | post × fetched_date | public counts: reaction_count (likes), comment_count, child_comment_count, restacks |
| `post_stats_history` | post × fetched_date | private email/web stats: deliveries, opens, open_rate, sent, clicks, views, signups, subscribes, signups_within_1_day, subscriptions_within_1_day, unsubscribes_within_1_day, disables_within_1_day, comments, likes, shares |
| `subscriber_timeseries` | one row per day | total subscriber count since 2021-02 |
| `traffic_daily` | one row per day | site visits, full daily history since 2021-02 (fetched in 80-day windows) |
| `visitor_sources_monthly` | month × source | acquisition: views, users, free_signups, subscribed per traffic source (email, direct, google.com, …) with source_category |
| `subscribers` | one row per subscriber | full audience export (43 cols, snake_cased): email, start_date, subscription_source_free/paid, activity, country, per-window engagement (emails_opened_6mo/7d/30d, post_views, comments, shares, days_active_30d…). Loaded from the newest CSV in `data/subscriber-exports/` |
| `subscriber_events` | one row per subscribe/unsubscribe event | captured_at, event (`add`/`drop`/`drop-old`), occurred_at, email; downloaded by a personal fetcher in `scripts/local/` (gitignored). Bulk digest emails appear as synthetic `no-email-*@no-email.com` rows |

Views: `post_stats` and `post_engagement` (newest snapshot per post),
**`posts_overview`** — posts joined to both latest snapshots; start
there for almost any per-post question — and `subscriber_sources` (signup
month × acquisition source rollup of `subscribers`).

The `_history` tables are snapshots: multiple rows per post, one per fetch
date. Use them for "how did stats evolve"; `post_stats` / `post_engagement`
(or `posts_overview`) always hold just the current numbers.

## Example queries

```sql
-- best-performing posts by views
SELECT title, post_date::DATE AS d, views, opens, open_rate, likes
FROM posts_overview ORDER BY views DESC LIMIT 15;

-- subscriber growth by month
SELECT date_trunc('month', date) AS month, max(subscribers) AS subscribers
FROM subscriber_timeseries GROUP BY 1 ORDER BY 1;

-- do longer posts do better?
SELECT round(wordcount, -3) AS words, count(*) n, avg(open_rate) avg_open, avg(views) avg_views
FROM posts_overview GROUP BY 1 ORDER BY 1;

-- full-text search the posts
SELECT p.title, p.post_date::DATE
FROM post_content c JOIN posts p USING (post_id)
WHERE c.markdown ILIKE '%data warehouse%' ORDER BY p.post_date DESC;
```

The full post texts are also in `posts/*.md` and `posts.jsonl` if grepping is
easier than SQL.

## Pipeline map (scripts/)

`update.py` orchestrates: `fetch_posts.py` (public API → `data/raw/posts/`) →
`fetch_stats.py` (cookie-authed API → `data/raw/stats/<date>/`; also runs any
personal fetchers in gitignored `scripts/local/`) → `render_posts.py`
(markdown + posts.csv) → `convert_to_jsonl.py` + `batch_by_quarter.py` →
`build_db.py` → `build_dashboard.py` → `push_bq.py` (optional, see `.env`).
`substack_api.py` is the shared client; the stats cookie lives in `.env`
(`SUBSTACK_COOKIE`). `process_export.py` is the fallback path for official
Substack exports.
