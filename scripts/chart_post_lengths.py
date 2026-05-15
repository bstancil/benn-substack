import csv
import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
POSTS_JSONL = ROOT / "posts.jsonl"
OUT_DIR = ROOT / "charts"
OUT_CSV = OUT_DIR / "post-lengths.csv"
OUT_PNG = OUT_DIR / "post-lengths-over-time.png"


def markdown_to_countable_text(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^---+$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^#+\s*", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^\[\^[^\]]+\]:", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\[\^[^\]]+\]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_`>~#|]", " ", text)
    return text


def word_count(markdown: str) -> int:
    text = markdown_to_countable_text(markdown)
    return len(re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?", text))


def load_posts():
    posts = []
    with POSTS_JSONL.open() as f:
        for line in f:
            post = json.loads(line)
            date = datetime.fromisoformat(post["post_date"].replace("Z", "+00:00"))
            posts.append(
                {
                    "date": date,
                    "title": post["title"],
                    "post_id": post["post_id"],
                    "words": word_count(post["content"]),
                }
            )
    return sorted(posts, key=lambda post: post["date"])


def rolling_average(values, window=8):
    averages = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        window_values = values[start : index + 1]
        averages.append(sum(window_values) / len(window_values))
    return averages


def write_csv(posts):
    OUT_DIR.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["post_date", "post_id", "title", "words"])
        writer.writeheader()
        for post in posts:
            writer.writerow(
                {
                    "post_date": post["date"].date().isoformat(),
                    "post_id": post["post_id"],
                    "title": post["title"],
                    "words": post["words"],
                }
            )


def write_chart(posts):
    OUT_DIR.mkdir(exist_ok=True)
    dates = [post["date"] for post in posts]
    words = [post["words"] for post in posts]
    trend = rolling_average(words)

    fig, ax = plt.subplots(figsize=(14, 7), dpi=160)
    ax.scatter(dates, words, s=22, color="#3B82F6", alpha=0.58, linewidth=0)
    ax.plot(dates, trend, color="#111827", linewidth=2.4, label="8-post rolling average")

    ax.set_title("Benn Substack Post Lengths Over Time", fontsize=18, pad=18)
    ax.set_ylabel("Words per post", fontsize=12)
    ax.set_xlabel("")
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.9)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D1D5DB")
    ax.spines["bottom"].set_color("#D1D5DB")
    ax.tick_params(colors="#374151")
    ax.legend(frameon=False, loc="upper left")

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate(rotation=0)

    longest = max(posts, key=lambda post: post["words"])
    ax.annotate(
        f"Longest: {longest['title']} ({longest['words']:,})",
        xy=(longest["date"], longest["words"]),
        xytext=(16, 16),
        textcoords="offset points",
        fontsize=9,
        color="#111827",
        arrowprops={"arrowstyle": "->", "color": "#6B7280", "lw": 1},
    )

    fig.tight_layout()
    fig.savefig(OUT_PNG, bbox_inches="tight")
    plt.close(fig)


def main():
    posts = load_posts()
    write_csv(posts)
    write_chart(posts)
    print(f"Wrote {OUT_PNG.relative_to(ROOT)}")
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"Charted {len(posts)} posts")


if __name__ == "__main__":
    main()
