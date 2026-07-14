#!/usr/bin/env python3
"""
Fetch post content and metadata from Substack's public API.

Saves full post JSON (including body_html) to data/raw/posts/{id}.{slug}.json
and an archive-listing snapshot (engagement counts for every post) to
data/raw/stats/{today}/archive.json. No auth required.
"""

import argparse
import time

from substack_api import ROOT_DIR, SubstackClient, save_json, today_str

RAW_POSTS_DIR = ROOT_DIR / "data" / "raw" / "posts"
RAW_STATS_DIR = ROOT_DIR / "data" / "raw" / "stats"


def fetch_posts(client=None, full=False):
    """Sync data/raw/posts/ with the publication archive. Returns archive list."""
    client = client or SubstackClient()

    print("Fetching archive listing...")
    archive = [p for p in client.iter_archive() if p.get("type") != "thread"]
    print(f"Found {len(archive)} posts")

    save_json(RAW_STATS_DIR / today_str() / "archive.json", archive)

    # Refetch the newest few posts unconditionally to pick up post-publish edits
    refresh_newest = 3

    fetched = 0
    for i, item in enumerate(archive):
        post_id, slug = item["id"], item["slug"]
        path = RAW_POSTS_DIR / f"{post_id}.{slug}.json"
        if path.exists() and not full and i >= refresh_newest:
            continue

        post = client.get_post(slug)
        save_json(path, post)
        fetched += 1
        print(f"  [{fetched}] fetched {post_id}.{slug}")
        time.sleep(client.delay)

    print(f"Post content: {fetched} fetched, {len(archive) - fetched} already cached")
    return archive


def main():
    parser = argparse.ArgumentParser(description="Fetch posts from the Substack API.")
    parser.add_argument("--full", action="store_true", help="Refetch all post content")
    args = parser.parse_args()

    fetch_posts(full=args.full)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
