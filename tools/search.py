#!/usr/bin/env python3
"""
tools/search.py — Full-text search over the wiki.

Scores pages by:
  * Title match         × 10
  * H2/H3 header match  × 5
  * Body term frequency × 1

Usage
-----
  python tools/search.py "DV01 bucket"
  python tools/search.py "zaronia curve bootstrap" -n 10
  python tools/search.py "hedge" --paths
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path


WIKI_DIR = Path(__file__).parent.parent / "wiki"
SNIPPET_RADIUS = 120   # chars around first match for context


def _tokenise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _load_pages() -> list[dict]:
    pages = []
    for path in sorted(WIKI_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        # Extract title (first # heading)
        title = path.stem
        headers: list[str] = []
        body_lines: list[str] = []
        for line in lines:
            if line.startswith("# ") and title == path.stem:
                title = line[2:].strip()
            elif line.startswith("## ") or line.startswith("### "):
                headers.append(re.sub(r"^#{2,3}\s+", "", line))
            else:
                body_lines.append(line)

        body = " ".join(body_lines)
        rel = path.relative_to(WIKI_DIR).with_suffix("")

        pages.append({
            "path":    path,
            "rel":     str(rel),
            "title":   title,
            "headers": headers,
            "body":    body,
            "raw":     text,
        })
    return pages


def _score(page: dict, query_tokens: list[str]) -> float:
    score = 0.0
    title_tokens  = _tokenise(page["title"])
    header_tokens = _tokenise(" ".join(page["headers"]))
    body_tokens   = _tokenise(page["body"])

    body_len = max(len(body_tokens), 1)

    for qt in query_tokens:
        # Title hit
        score += 10 * title_tokens.count(qt)

        # Header hit
        score += 5 * header_tokens.count(qt)

        # Body TF (log-scaled)
        tf = body_tokens.count(qt)
        if tf:
            score += 1 + math.log(tf)

    return score


def _snippet(raw: str, query_tokens: list[str]) -> str:
    """Return a short excerpt around the first query token occurrence."""
    text_lower = raw.lower()
    best_pos = len(raw)
    for qt in query_tokens:
        idx = text_lower.find(qt)
        if 0 <= idx < best_pos:
            best_pos = idx

    if best_pos == len(raw):
        # No match found in raw text — return first non-heading line
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped[:200]
        return ""

    start = max(0, best_pos - SNIPPET_RADIUS)
    end   = min(len(raw), best_pos + SNIPPET_RADIUS)
    excerpt = raw[start:end].replace("\n", " ").strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(raw):
        excerpt = excerpt + "…"
    return excerpt


def search(query: str, n: int = 5, paths_only: bool = False) -> None:
    query_tokens = _tokenise(query)
    if not query_tokens:
        print("No query terms provided.", file=sys.stderr)
        sys.exit(1)

    pages = _load_pages()
    scored = sorted(
        ((p, _score(p, query_tokens)) for p in pages),
        key=lambda x: x[1],
        reverse=True,
    )
    # Filter zero scores
    results = [(p, s) for p, s in scored if s > 0][:n]

    if not results:
        print(f"No results for: {query!r}")
        return

    if paths_only:
        for page, _ in results:
            print(f"wiki/{page['rel']}.md")
        return

    width = 72
    print(f"\n  Search: {query!r}  —  {len(results)} result(s)\n")
    print("  " + "─" * width)

    for rank, (page, score) in enumerate(results, 1):
        rel_link = f"[[{page['rel']}]]"
        print(f"\n  {rank}. {page['title']}")
        print(f"     {rel_link}  (score {score:.1f})")
        snippet = _snippet(page["raw"], query_tokens)
        if snippet:
            # Wrap snippet to width
            words = snippet.split()
            line, out = [], []
            for w in words:
                line.append(w)
                if len(" ".join(line)) > 64:
                    out.append("     " + " ".join(line[:-1]))
                    line = [w]
            if line:
                out.append("     " + " ".join(line))
            print("\n".join(out))

    print("\n  " + "─" * width + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search the wiki.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="+", help="Search terms")
    parser.add_argument("-n", type=int, default=5, help="Number of results (default 5)")
    parser.add_argument("--paths", action="store_true", help="Print file paths only")
    args = parser.parse_args()

    search(" ".join(args.query), n=args.n, paths_only=args.paths)


if __name__ == "__main__":
    main()
