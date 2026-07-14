#!/usr/bin/env python3
"""
Render content assets from the raw post JSON fetched by fetch_posts.py:
  posts/{id}.{slug}.md   markdown for each post
  posts.csv              post metadata (same format as a Substack export)

Uses the same HTML->markdown conversion as the export path (parse_html.py),
so output is identical whichever way the posts were obtained.
"""

import csv
import json

from parse_html import convert_html_to_markdown
from substack_api import ROOT_DIR

RAW_POSTS_DIR = ROOT_DIR / "data" / "raw" / "posts"
POSTS_DIR = ROOT_DIR / "posts"
CSV_PATH = ROOT_DIR / "posts.csv"

# Matches the header of posts.csv in official Substack exports, so the
# downstream scripts (convert_to_jsonl, batch_by_quarter) work with both
CSV_COLUMNS = [
    "post_id", "post_date", "is_published", "email_sent_at", "inbox_sent_at",
    "type", "audience", "title", "subtitle", "podcast_url",
]


def load_raw_posts():
    posts = []
    for path in sorted(RAW_POSTS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            posts.append(json.load(f))
    posts.sort(key=lambda p: p["post_date"], reverse=True)
    return posts


def render_posts():
    posts = load_raw_posts()
    if not posts:
        print("No raw posts found — run fetch_posts.py first")
        return 1

    POSTS_DIR.mkdir(exist_ok=True)

    print(f"Rendering {len(posts)} posts to markdown...")
    for post in posts:
        markdown = convert_html_to_markdown(
            post.get("body_html") or "", post.get("title"), post.get("subtitle")
        )
        md_path = POSTS_DIR / f"{post['id']}.{post['slug']}.md"
        md_path.write_text(markdown, encoding="utf-8")

    print(f"Writing {CSV_PATH.name}...")
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for post in posts:
            writer.writerow({
                "post_id": f"{post['id']}.{post['slug']}",
                "post_date": post["post_date"],
                "is_published": "true",
                "email_sent_at": post.get("email_sent_at") or "",
                "inbox_sent_at": post.get("inbox_sent_at") or "",
                "type": post.get("type") or "",
                "audience": post.get("audience") or "",
                "title": post.get("title") or "",
                "subtitle": post.get("subtitle") or "",
                "podcast_url": post.get("podcast_url") or "",
            })

    print(f"Rendered {len(posts)} posts -> {POSTS_DIR}, {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(render_posts())
