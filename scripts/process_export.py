#!/usr/bin/env python3
"""
Process a Substack export: parse HTML, convert to JSONL, and batch by quarter.

Usage: python process_export.py <export_dir>
Example: python process_export.py export-2025-01-20
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_script(script_path, export_dir):
    """Run a Python script and return success status."""
    result = subprocess.run(
        [sys.executable, str(script_path), export_dir],
        cwd=script_path.parent.parent
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description='Process a Substack export.')
    parser.add_argument('export_dir', help='Export directory name (e.g., export-2025-01-20)')
    args = parser.parse_args()

    script_dir = Path(__file__).parent

    steps = [
        ('Step 1/3: Converting HTML to Markdown', 'parse_html.py'),
        ('Step 2/3: Converting to JSONL', 'convert_to_jsonl.py'),
        ('Step 3/3: Batching by quarter', 'batch_by_quarter.py'),
    ]

    print("=" * 50)
    print(f"Processing Substack export: {args.export_dir}")
    print("=" * 50)
    print()

    for description, script_name in steps:
        print(description)
        print("-" * 50)

        script_path = script_dir / script_name
        if not run_script(script_path, args.export_dir):
            print(f"\nError: {script_name} failed")
            return 1
        print()

    print("=" * 50)
    print("All processing complete!")
    print("=" * 50)
    return 0


if __name__ == '__main__':
    sys.exit(main())
