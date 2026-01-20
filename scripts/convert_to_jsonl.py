#!/usr/bin/env python3
"""
Convert markdown posts to JSONL format.
Combines data from posts.csv with markdown content.
"""

import argparse
import json
import csv
from pathlib import Path


def load_posts_metadata(csv_path):
    """Load post metadata from posts.csv."""
    posts = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            post_id = row['post_id']
            posts[post_id] = {
                'post_id': post_id,
                'post_date': row['post_date'],
                'title': row['title'],
                'subtitle': row['subtitle'],
                'is_published': row.get('is_published', ''),
                'type': row.get('type', ''),
                'audience': row.get('audience', '')
            }

    return posts


def load_markdown_content(markdown_path):
    """Load markdown content from a file and return as a single-line string."""
    with open(markdown_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return content


def main():
    """Convert markdown posts to JSONL."""
    parser = argparse.ArgumentParser(description='Convert markdown posts to JSONL format.')
    parser.add_argument('export_dir', help='Export directory name (e.g., export-2025-01-20)')
    args = parser.parse_args()

    # Use paths relative to script location
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    csv_path = root_dir / args.export_dir / 'posts.csv'
    markdown_dir = root_dir / 'posts'
    output_path = root_dir / 'posts.jsonl'

    # Validate CSV exists
    if not csv_path.exists():
        print(f"Error: posts.csv not found: {csv_path}")
        return 1

    # Load post metadata
    print(f"Loading post metadata from {csv_path}...")
    posts_metadata = load_posts_metadata(csv_path)
    print(f"Loaded metadata for {len(posts_metadata)} posts")

    # Find all markdown files
    markdown_files = list(markdown_dir.glob('*.md'))
    print(f"Found {len(markdown_files)} markdown files\n")

    # Create JSONL entries
    jsonl_entries = []
    processed_count = 0
    missing_count = 0

    for md_file in markdown_files:
        post_id = md_file.stem  # e.g., "177675177.a-strange-delight"

        # Check if we have metadata for this post
        if post_id not in posts_metadata:
            print(f"Warning: No metadata found for {post_id}")
            missing_count += 1
            continue

        # Load markdown content
        try:
            content = load_markdown_content(md_file)
        except Exception as e:
            print(f"Error reading {md_file.name}: {e}")
            continue

        # Create JSONL entry
        entry = {
            'post_id': post_id,
            'post_date': posts_metadata[post_id]['post_date'],
            'title': posts_metadata[post_id]['title'],
            'subtitle': posts_metadata[post_id]['subtitle'],
            'content': content
        }

        jsonl_entries.append(entry)
        processed_count += 1

    # Sort by post_date (newest first)
    jsonl_entries.sort(key=lambda x: x['post_date'], reverse=True)

    # Write JSONL file
    print(f"Writing JSONL file to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in jsonl_entries:
            json_line = json.dumps(entry, ensure_ascii=False)
            f.write(json_line + '\n')

    print(f"\nConversion complete!")
    print(f"  Processed: {processed_count} posts")
    print(f"  Missing metadata: {missing_count} posts")
    print(f"  Output: {output_path}")


if __name__ == '__main__':
    main()
