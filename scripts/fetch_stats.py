#!/usr/bin/env python3
"""
Fetch private Substack stats (requires session cookie in .env).

Saves raw JSON snapshots under data/raw/stats/{today}/:
  email_stats.json      one row per emailed post (deliveries, opens, ...)
  post_stats.json       {post_id: detailed stats} (views, clicks, signups, ...)
  subscribers.json      full daily subscriber-count timeseries
  traffic.json          full daily site-traffic history
  visitor_sources.json  monthly acquisition-source stats

Also runs any personal fetchers in scripts/local/ (gitignored) first.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path

from substack_api import (
    PUBLICATION_START, ROOT_DIR, AuthError, SubstackClient, save_json, today_str,
)

RAW_STATS_DIR = ROOT_DIR / "data" / "raw" / "stats"
PUBLICATION_FIRST_MONTH = date.fromisoformat(PUBLICATION_START[:10]).replace(day=1)


def month_starts(since=PUBLICATION_FIRST_MONTH):
    """First-of-month dates from `since` through the current month."""
    months, cur, today = [], since, date.today()
    while cur <= today:
        months.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def latest_snapshot_file(name):
    """Most recent data/raw/stats/<date>/<name>, or None."""
    if not RAW_STATS_DIR.exists():
        return None
    for snap_dir in sorted((d for d in RAW_STATS_DIR.iterdir() if d.is_dir()), reverse=True):
        if (snap_dir / name).exists():
            return snap_dir / name
    return None


def fetch_visitor_sources(client, out_dir):
    """Monthly acquisition-source stats: {YYYY-MM-01: [source rows]}.

    Past months are stable, so reuse them from the previous snapshot and only
    fetch missing months plus the two most recent (late-arriving attribution).
    """
    data = {}
    prev_path = latest_snapshot_file("visitor_sources.json")
    if prev_path:
        with open(prev_path, encoding="utf-8") as f:
            data = json.load(f)

    months = month_starts()
    to_fetch = [m for m in months if m.isoformat() not in data] + months[-2:]
    for m in sorted(set(to_fetch)):
        month_end = min((m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), date.today())
        data[m.isoformat()] = client.get_visitor_sources(m.isoformat(), month_end.isoformat())
        time.sleep(client.delay)

    save_json(out_dir / "visitor_sources.json", data)
    return data


LOCAL_FETCHERS_DIR = Path(__file__).parent / "local"


def run_local_fetchers(out_dir):
    """Run any local-only fetchers in scripts/local/ (gitignored).

    Each *.py there with a run(out_dir) function gets called with the day's
    raw-stats snapshot directory — an extension point for personal data
    sources that don't belong in the public repo.
    """
    if not LOCAL_FETCHERS_DIR.exists():
        return
    import importlib.util

    for path in sorted(LOCAL_FETCHERS_DIR.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"local_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            if hasattr(module, "run"):
                module.run(out_dir)
        except Exception as e:
            print(f"  WARNING: local fetcher {path.name} failed ({e}) — continuing.")


def fetch_stats(client=None):
    """Fetch all stats snapshots. Raises AuthError if the cookie is missing/stale."""
    client = client or SubstackClient()
    out_dir = RAW_STATS_DIR / today_str()

    run_local_fetchers(out_dir)

    print("Fetching email stats...")
    email_stats = client.get_email_stats()
    save_json(out_dir / "email_stats.json", email_stats)
    print(f"  {len(email_stats)} posts")

    print("Fetching per-post stats...")
    post_stats = {}
    for i, row in enumerate(email_stats, 1):
        post_id = row["post_id"]
        post_stats[str(post_id)] = client.get_post_stats(post_id)
        if i % 25 == 0:
            print(f"  {i}/{len(email_stats)}")
        time.sleep(client.delay)
    save_json(out_dir / "post_stats.json", post_stats)

    print("Fetching subscriber timeseries...")
    subs = client.get_subscriber_timeseries()
    save_json(out_dir / "subscribers.json", subs)
    print(f"  {len(subs)} days")

    print("Fetching traffic timeseries (full history, windowed)...")
    traffic = client.get_traffic_timeseries()
    save_json(out_dir / "traffic.json", traffic)
    print(f"  {len(traffic)} days")

    print("Fetching visitor sources by month...")
    sources = fetch_visitor_sources(client, out_dir)
    print(f"  {len(sources)} months")

    print(f"Stats saved to {out_dir}")


def main():
    try:
        fetch_stats()
    except AuthError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
