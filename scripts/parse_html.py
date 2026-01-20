#!/usr/bin/env python3
"""
Convert Substack HTML blog posts to clean markdown.
"""

import argparse
import re
import csv
from pathlib import Path
from bs4 import BeautifulSoup


def convert_html_to_markdown(html_content, title=None, subtitle=None):
    """Convert Substack HTML to clean markdown."""
    soup = BeautifulSoup(html_content, 'html.parser')

    markdown_lines = []

    # Add title and subtitle at the top if available
    if title:
        markdown_lines.append(f"# {title}")
        if subtitle:
            markdown_lines.append(f"*{subtitle}*")
        markdown_lines.append("---")  # Add separator

    footnote_references = {}
    footnote_counter = 1

    # Process all top-level elements
    for element in soup.children:
        if element.name is None:  # Skip text nodes at root level
            continue

        result = process_element(element, footnote_references, footnote_counter)
        if result:
            markdown_lines.append(result)
            # Update counter if we added footnotes
            footnote_counter = len(footnote_references) + 1

    # Add footnotes at the end if any exist
    if footnote_references:
        markdown_lines.append('\n---\n')
        for ref_num in sorted(footnote_references.keys()):
            markdown_lines.append(f"[^{ref_num}]: {footnote_references[ref_num]}")

    return '\n\n'.join(markdown_lines).strip()


def process_element(element, footnote_refs, counter):
    """Process a single HTML element and convert to markdown."""
    if element.name is None:
        # Text node
        text = element.strip()
        return text if text else None

    # Handle different element types
    if element.name == 'h1':
        return f"# {get_text_content(element, footnote_refs, counter)}"

    elif element.name == 'h2':
        return f"## {get_text_content(element, footnote_refs, counter)}"

    elif element.name == 'h3':
        return f"### {get_text_content(element, footnote_refs, counter)}"

    elif element.name == 'p':
        return get_text_content(element, footnote_refs, counter)

    elif element.name == 'blockquote':
        # Handle blockquotes
        lines = []
        for child in element.children:
            if child.name == 'p':
                lines.append(f"> {get_text_content(child, footnote_refs, counter)}")
        return '\n'.join(lines)

    elif element.name == 'div':
        # Check for special div types
        classes = element.get('class', [])

        # Handle images
        if 'captioned-image-container' in classes:
            return handle_image(element)

        # Handle footnotes at the bottom
        if 'footnote' in classes:
            return handle_footnote_definition(element, footnote_refs, counter)

        # For other divs, process children
        results = []
        for child in element.children:
            if child.name:
                result = process_element(child, footnote_refs, counter)
                if result:
                    results.append(result)
        return '\n\n'.join(results) if results else None

    return None


def get_text_content(element, footnote_refs, counter):
    """Extract text content from an element, handling inline formatting."""
    if element.name is None:
        return element.strip()

    result = []

    for child in element.children:
        if child.name is None:
            # Plain text
            result.append(str(child))

        elif child.name == 'a':
            # Check if it's a footnote anchor
            if 'footnote-anchor' in child.get('class', []):
                # Extract the footnote number from the href
                href = child.get('href', '')
                match = re.search(r'#footnote-(\d+)', href)
                if match:
                    footnote_num = match.group(1)
                    result.append(f"[^{footnote_num}]")
            else:
                # Regular link
                href = child.get('href', '')
                text = child.get_text()
                if href and text:
                    result.append(f"[{text}]({href})")
                else:
                    result.append(text)

        elif child.name == 'em':
            text = get_text_content(child, footnote_refs, counter)
            result.append(f"*{text}*")

        elif child.name == 'strong':
            text = get_text_content(child, footnote_refs, counter)
            result.append(f"**{text}**")

        elif child.name == 'code':
            result.append(f"`{child.get_text()}`")

        else:
            # Recursively get text from other elements
            result.append(get_text_content(child, footnote_refs, counter))

    return ''.join(result)


def handle_image(element):
    """Extract image information and convert to markdown, replacing Bucketeer URLs."""
    # Find the img tag
    img = element.find('img')
    if img:
        alt_text = img.get('alt', '')
        src = img.get('src', '')

        # Check if there's a parent link with substackcdn URL
        parent_link = element.find('a', class_='image-link')
        if parent_link:
            href = parent_link.get('href', '')
            # Prefer substackcdn URL from href over direct bucketeer URL
            if href and 'substackcdn.com' in href:
                src = href
            elif 'bucketeer' in src and href:
                # If src is bucketeer but href exists, use href
                src = href

        # Try to find caption
        caption = element.find('figcaption')
        if caption:
            # Get caption text, handling links within it
            caption_link = caption.find('a')
            if caption_link:
                caption_text = caption_link.get_text()
                caption_url = caption_link.get('href', '')
                return f"![{alt_text}]({src})\n*[{caption_text}]({caption_url})*"
            else:
                caption_text = caption.get_text()
                return f"![{alt_text}]({src})\n*{caption_text}*"

        return f"![{alt_text}]({src})"

    return None


def handle_footnote_definition(element, footnote_refs, counter):
    """Handle footnote definitions at the bottom of the document."""
    # Find the footnote number
    footnote_num_elem = element.find('a', class_='footnote-number')
    if footnote_num_elem:
        # Extract the footnote number from the href
        href = footnote_num_elem.get('href', '')
        match = re.search(r'footnote-anchor-(\d+)', href)
        if match:
            footnote_num = int(match.group(1))

            # Find the content
            content_elem = element.find('div', class_='footnote-content')
            if content_elem:
                # Get all text content from the footnote
                content_text = get_text_content(content_elem, {}, counter)
                footnote_refs[footnote_num] = content_text.strip()

    return None  # Don't add to main content, we'll add all footnotes at the end


def convert_file(input_path, output_path, post_metadata):
    """Convert a single HTML file to markdown."""
    with open(input_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Extract filename (e.g., "100667069.insight-industrial-complex")
    filename = input_path.stem

    # Get metadata for this post
    title = post_metadata.get(filename, {}).get('title')
    subtitle = post_metadata.get(filename, {}).get('subtitle')

    markdown_content = convert_html_to_markdown(html_content, title, subtitle)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)


def load_post_metadata(csv_path):
    """Load post metadata from posts.csv."""
    metadata = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            post_id = row['post_id']  # This is like "177675177.a-strange-delight"
            metadata[post_id] = {
                'title': row['title'],
                'subtitle': row['subtitle'],
                'post_date': row['post_date']
            }

    return metadata


def main():
    """Convert all HTML files in the posts directory."""
    parser = argparse.ArgumentParser(description='Convert Substack HTML exports to markdown.')
    parser.add_argument('export_dir', help='Export directory name (e.g., export-2025-01-20)')
    args = parser.parse_args()

    # Use paths relative to script location
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    posts_dir = root_dir / args.export_dir / 'posts'
    output_dir = root_dir / 'posts'
    csv_path = root_dir / args.export_dir / 'posts.csv'

    # Validate input directory exists
    if not posts_dir.exists():
        print(f"Error: Posts directory not found: {posts_dir}")
        return 1

    if not csv_path.exists():
        print(f"Error: posts.csv not found: {csv_path}")
        return 1

    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)

    # Load post metadata
    print(f"Loading post metadata from {csv_path}...")
    post_metadata = load_post_metadata(csv_path)
    print(f"Loaded metadata for {len(post_metadata)} posts")

    # Find all HTML files
    html_files = list(posts_dir.glob('*.html'))

    print(f"Found {len(html_files)} HTML files to convert\n")

    for i, html_file in enumerate(html_files, 1):
        output_file = output_dir / (html_file.stem + '.md')

        try:
            convert_file(html_file, output_file, post_metadata)
            print(f"[{i}/{len(html_files)}] Converted: {html_file.name}")
        except Exception as e:
            print(f"[{i}/{len(html_files)}] ERROR converting {html_file.name}: {e}")

    print(f"\nConversion complete!")
    print(f"  Markdown files: {output_dir}")
    return 0


if __name__ == '__main__':
    main()
