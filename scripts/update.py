#!/usr/bin/env python3
"""
Update everything: fetch posts and stats from Substack, rebuild the DuckDB
database, regenerate the markdown/CSV/JSONL content assets, and rebuild the
dashboard.

Usage:
  python scripts/update.py               # the one command
  python scripts/update.py --full        # also refetch all post content
  python scripts/update.py --skip-stats  # content assets only, no cookie needed
  python scripts/update.py --check-auth  # just validate the Substack cookie
"""

import argparse
import subprocess
import sys
from pathlib import Path

import requests

from substack_api import ROOT_DIR, AuthError, SubstackClient
from fetch_posts import fetch_posts
from fetch_stats import fetch_stats
from render_posts import render_posts
from build_db import build_db
from build_dashboard import build_dashboard
from push_bq import push_bq

SCRIPT_DIR = Path(__file__).parent


def run_step(title, fn):
    print(f"\n=== {title} " + "=" * max(0, 50 - len(title)))
    fn()


def main():
    parser = argparse.ArgumentParser(description="Update all Substack assets.")
    parser.add_argument("--full", action="store_true", help="Refetch all post content")
    parser.add_argument("--skip-stats", action="store_true", help="Skip the private stats fetch")
    parser.add_argument("--check-auth", action="store_true", help="Validate the Substack cookie and exit")
    parser.add_argument("--skip-bq", action="store_true", help="Skip the BigQuery push")
    args = parser.parse_args()

    client = SubstackClient()

    if args.check_auth:
        if client.check_auth():
            print("Cookie works: stats API is accessible.")
            return 0
        print(AuthError())
        return 1

    stats_ok = True

    run_step("Fetching posts (public API)", lambda: fetch_posts(client, full=args.full))

    if args.skip_stats:
        print("\nSkipping stats fetch (--skip-stats)")
    else:
        print(f"\n=== Fetching stats (private API) " + "=" * 17)
        try:
            fetch_stats(client)
        except AuthError as e:
            stats_ok = False
            print(f"\nWARNING: stats fetch skipped.\n\n{e}")
        except requests.RequestException as e:
            stats_ok = False
            print(f"\nWARNING: stats fetch failed ({e}); continuing without fresh stats.")

    run_step("Rendering content assets", render_posts)

    for script in ("convert_to_jsonl.py", "batch_by_quarter.py"):
        run_step(script, lambda s=script: subprocess.run(
            [sys.executable, str(SCRIPT_DIR / s), str(ROOT_DIR / "posts.csv")], check=True
        ))

    run_step("Building DuckDB", build_db)
    run_step("Building dashboard", build_dashboard)

    if args.skip_bq:
        print("\nSkipping BigQuery push (--skip-bq)")
    else:
        print(f"\n=== Pushing to BigQuery " + "=" * 27)
        try:
            push_bq()
        except Exception as e:
            print(f"\nWARNING: BigQuery push failed ({e}); everything else succeeded.")

    print("\n" + "=" * 55)
    if stats_ok:
        print("Update complete.")
    else:
        print("Update complete, but WITHOUT fresh stats (cookie problem — see above).")
    print(f"  Dashboard: {ROOT_DIR / 'dashboard' / 'dashboard.html'}")
    print(f"  Database:  {ROOT_DIR / 'data' / 'substack.duckdb'}")
    return 0 if stats_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
