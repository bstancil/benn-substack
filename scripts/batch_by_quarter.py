#!/usr/bin/env python3
"""
Batch markdown posts by quarter for BookLM.
Creates combined files with all posts from each quarter.
"""

import argparse
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def get_quarter(date_string):
    """Extract year and quarter from ISO date string (e.g., '2025-10-31T18:07:24.508Z')."""
    # Parse the date
    date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))

    # Calculate quarter (1-4)
    quarter = (date.month - 1) // 3 + 1

    return f"{date.year}-Q{quarter}"


def load_posts_by_quarter(csv_path):
    """Load post metadata and organize by quarter."""
    posts_by_quarter = defaultdict(list)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            post_id = row['post_id']
            post_date = row['post_date']
            title = row['title']

            quarter = get_quarter(post_date)

            posts_by_quarter[quarter].append({
                'post_id': post_id,
                'post_date': post_date,
                'title': title
            })

    # Sort posts within each quarter by date
    for quarter in posts_by_quarter:
        posts_by_quarter[quarter].sort(key=lambda x: x['post_date'])

    return posts_by_quarter


def load_markdown_content(markdown_path):
    """Load markdown content from a file."""
    with open(markdown_path, 'r', encoding='utf-8') as f:
        return f.read()


def main():
    """Batch markdown posts by quarter."""
    parser = argparse.ArgumentParser(description='Batch markdown posts by quarter.')
    parser.add_argument('export_dir', help='Export directory name (e.g., export-2025-01-20)')
    args = parser.parse_args()

    # Use paths relative to script location
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    csv_path = root_dir / args.export_dir / 'posts.csv'
    markdown_dir = root_dir / 'posts'
    output_dir = root_dir / 'posts-batched'

    # Validate CSV exists
    if not csv_path.exists():
        print(f"Error: posts.csv not found: {csv_path}")
        return 1

    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)

    # Load posts organized by quarter
    print(f"Loading post metadata from {csv_path}...")
    posts_by_quarter = load_posts_by_quarter(csv_path)
    print(f"Found posts in {len(posts_by_quarter)} quarters\n")

    # Process each quarter
    total_posts = 0
    for quarter in sorted(posts_by_quarter.keys()):
        posts = posts_by_quarter[quarter]
        print(f"Processing {quarter}: {len(posts)} posts")

        # Create output file for this quarter
        output_file = output_dir / f"{quarter}.md"

        with open(output_file, 'w', encoding='utf-8') as out_f:
            # Write header for the quarter
            out_f.write(f"# Posts from {quarter}\n\n")
            out_f.write(f"This file contains {len(posts)} posts from {quarter}.\n\n")
            out_f.write("=" * 80 + "\n\n")

            # Process each post in the quarter
            for i, post_info in enumerate(posts, 1):
                post_id = post_info['post_id']
                markdown_path = markdown_dir / f"{post_id}.md"

                # Check if markdown file exists
                if not markdown_path.exists():
                    print(f"  Warning: Markdown file not found for {post_id}")
                    continue

                # Load markdown content
                try:
                    content = load_markdown_content(markdown_path)

                    # Write post separator and content
                    if i > 1:
                        out_f.write("\n\n" + "=" * 80 + "\n\n")

                    out_f.write(content)

                    total_posts += 1

                except Exception as e:
                    print(f"  Error reading {post_id}: {e}")

        # Report file size
        file_size = output_file.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        print(f"  Created: {output_file.name} ({file_size_mb:.2f} MB)")

    print(f"\nBatching complete!")
    print(f"  Total posts processed: {total_posts}")
    print(f"  Quarterly files created: {len(posts_by_quarter)}")
    print(f"  Output directory: {output_dir}")


if __name__ == '__main__':
    main()
