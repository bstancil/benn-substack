# Data collection stuff

I obviously did not write this and have no idea how any of this works. But
the robots tell me that these are the data files that get generated:

- `data/substack.duckdb` — the database (posts, content, engagement, email
  stats, subscriber counts, traffic)
- `data/raw/` — raw JSON from the Substack API; the source of truth the
  database is rebuilt from
- `dashboard/dashboard.html` — self-contained dashboard; just open it

## Updating everything

```
pip install -r requirements.txt   # once
python scripts/update.py
```

One-time config: copy `.env.example` to `.env` and set `SUBSTACK_URL` to the
publication (and optionally `SUBSTACK_START_DATE`, the earliest date worth
fetching stats for).

That one command fetches new posts (public API), fetches stats (private API),
rebuilds the database, regenerates all the content assets, and rewrites the
dashboard.

Flags: `--full` refetches all post content, `--skip-stats` skips the private
stats, `--check-auth` just tests the cookie.

### Auth for stats

Post content is public, but stats need a logged-in Substack session:

1. Log in to the publication in a browser
2. Devtools → Application → Cookies → copy the value of `substack.sid`
3. Add it to `.env`:

   ```
   SUBSTACK_COOKIE=substack.sid=<value>
   ```

Sessions last for months. When the cookie expires, `update.py` says so plainly
and still completes everything that doesn't need it.

### Subscriber sources

The private API doesn't expose per-subscriber data, but the subscriber export
from the Substack audience dashboard does (acquisition source, engagement,
country, and more, per subscriber). Download one occasionally and drop it in
`data/subscriber-exports/` — the next database rebuild loads the newest file
into the `subscribers` table. Like everything under `data/`, it's gitignored
and never leaves this machine.

### Local-only fetchers

Anything in `scripts/local/` (gitignored) that defines a `run(out_dir)`
function gets called during the stats fetch with the day's raw-snapshot
directory. It's an extension point for personal data sources that don't
belong in a public repo; drop a CSV or JSON into `out_dir` and add a matching
loader in `build_db.py`.

### BigQuery

Optionally, each update can push every table to BigQuery. One-time setup:

1. Enable the **BigQuery API** on the target project
2. Create a service account, save its JSON key as `data/service-account.json`,
   and grant it **BigQuery Data Editor** and **BigQuery Job User** on that
   project (IAM → add the service account's email)
3. Set `BQ_DATASET` (and `BQ_PROJECT`, if it differs from the service
   account's project) in `.env`

Tables are fully replaced on each run; DuckDB views (`posts_overview`,
`post_stats`, …) land as ordinary tables. `--skip-bq` skips the push;
leaving `BQ_DATASET` unset disables it.

## Fallback: official Substack exports

The old export path still works and produces identical markdown (both paths
share the same HTML→markdown converter):

1. Download an export from Substack settings, unzip to `export-[date]/`
2. `python scripts/process_export.py export-[date]`

Useful if the API changes, or for export-only data like the email list.

## Analyzing the data

`data/substack.duckdb` has everything — see [CLAUDE.md](CLAUDE.md) for the
schema and example queries.
