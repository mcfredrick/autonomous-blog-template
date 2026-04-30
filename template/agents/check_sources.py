"""Check that all configured sources return items and are relevant to the blog topic.

Run any time to verify sources are working:
    python agents/check_sources.py
    python agents/check_sources.py --keywords "climate energy solar"

Exit code 1 if more than half the sources returned 0 items.
"""

import argparse
import sys

from config import BLOG_DESCRIPTION, BLOG_NAME
from sources import ALL_SOURCES

RELEVANCE_THRESHOLD = 0.5  # Fraction of items that must contain a keyword


def extract_keywords(description: str) -> list[str]:
    """Pull meaningful words from the blog description (4+ chars, deduplicated)."""
    stopwords = {
        "for", "the", "and", "with", "that", "this", "from", "about",
        "daily", "blog", "news", "digest", "post", "site",
    }
    words = [w.strip(".,;:!?\"'()") for w in description.lower().split()]
    seen: set[str] = set()
    result = []
    for w in words:
        if len(w) >= 4 and w not in stopwords and w not in seen:
            seen.add(w)
            result.append(w)
    return result


def is_relevant(item: dict, keywords: list[str]) -> bool:
    haystack = (item.get("title", "") + " " + item.get("text", "")).lower()
    return any(kw.lower() in haystack for kw in keywords)


def check_source(name: str, fetcher, keywords: list[str]) -> dict:
    try:
        items = fetcher()
    except Exception as e:
        return {"name": name, "error": str(e), "count": 0, "relevant": 0, "samples": []}

    count = len(items)
    relevant = sum(1 for item in items if is_relevant(item, keywords)) if keywords else 0
    samples = [item.get("title", "(no title)") for item in items[:3]]

    return {
        "name": name,
        "error": None,
        "count": count,
        "relevant": relevant,
        "samples": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Check sources for {BLOG_NAME}")
    parser.add_argument(
        "--keywords",
        nargs="+",
        help="Keywords to check relevance against (space-separated). "
             "Defaults to words extracted from BLOG_DESCRIPTION.",
    )
    args = parser.parse_args()

    keywords = args.keywords or extract_keywords(BLOG_DESCRIPTION)

    print(f"Checking sources for: {BLOG_NAME}")
    print(f"Relevance keywords: {', '.join(keywords)}\n")

    results = []
    for name, fetcher in ALL_SOURCES.items():
        print(f"  [{name}]")
        result = check_source(name, fetcher, keywords)
        results.append(result)

        if result["error"]:
            print(f"    ERROR: {result['error']}")
        else:
            rel_str = f"{result['relevant']}/{result['count']} relevant" if keywords else "no keywords"
            print(f"    {result['count']} items — {rel_str}")
            for title in result["samples"]:
                print(f"    - {title}")
        print()

    # Summary
    total = len(results)
    zero_count = sum(1 for r in results if r["count"] == 0)
    passed_relevance = sum(
        1 for r in results
        if r["count"] > 0 and (not keywords or r["relevant"] / r["count"] >= RELEVANCE_THRESHOLD)
    )

    print("=" * 60)
    print(f"Sources checked:   {total}")
    print(f"Returned 0 items:  {zero_count}")
    print(f"Passed relevance:  {passed_relevance}/{total - zero_count} (threshold: {int(RELEVANCE_THRESHOLD * 100)}%)")

    if zero_count > total / 2:
        print("\nFAIL: More than half the sources returned 0 items.", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nOK: Source check passed.")


if __name__ == "__main__":
    main()
