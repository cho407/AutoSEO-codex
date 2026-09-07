#!/usr/bin/env python3
"""Advisory style diagnostics, not a factual-quality or ranking score.

The legacy ``overall_quality`` key is retained for callers, but now describes
style patterns and repetition only. English name/number density is descriptive;
it is unmeasured for Korean and never contributes to the score. There is no
length bonus. Factual accuracy, usefulness, originality and authorship all need
independent semantic review. These heuristics cannot prove AI authorship or
classify a page's Google Quality Rater Guidelines rating.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Iterable

from file_safety import read_stream_limited, read_text_limited
from korean_text import normalize_text, tokenize

# Padding / filler phrases that QRG §4.6 flags as "little-to-no value".
# Each phrase scores 1 hit; threshold tuned at ~3 hits per 1000 tokens.
_FILLER_PHRASES: tuple[str, ...] = (
    "it's important to note that",
    "in this article, we'll explore",
    "in this article we will explore",
    "in today's fast-paced world",
    "in today's digital age",
    "in today's competitive landscape",
    "needless to say",
    "at the end of the day",
    "when it comes to",
    "when all is said and done",
    "in the realm of",
    "in the world of",
    "the bottom line is",
    "without further ado",
    "first and foremost",
    "last but not least",
    "for what it's worth",
    "it goes without saying",
    "as we all know",
    "the truth is that",
    "the fact of the matter is",
    "more often than not",
    "let's dive in",
    "let's dive into",
    "let's take a closer look",
    "let's take a deeper look",
)


# Conservative AutoSEO style patterns. Adding to this list should require
# corpus evidence and a false-positive review, not intuition alone.
_AI_PATTERNS: tuple[str, ...] = (
    "delve into",
    "delve deeper into",
    "in the ever-evolving",
    "ever-evolving landscape",
    "ever-changing landscape",
    "in the dynamic landscape",
    "navigating the",
    "navigate the complexities",
    "tapestry of",
    "rich tapestry",
    "intricate tapestry",
    "embark on a journey",
    "embarking on this",
    "a testament to",
    "a beacon of",
    "the cornerstone of",
    "a cornerstone of",
    "at the heart of",
    "at its core",
    "in essence,",
    "in conclusion,",
    "ultimately,",
    "moreover,",
    "furthermore,",
    "however, it's worth noting",
    "it's worth noting that",
    "by leveraging",
    "leverage the power of",
    "leveraging the power of",
    "harness the power of",
    "unlock the potential",
    "unlock the full potential",
    "the realm of possibilities",
    "open up a world of",
    "a world of possibilities",
    "elevate your",
    "transform your",
    "revolutionize the way",
    "game-changer",
    "game-changing",
    "cutting-edge",
    "state-of-the-art",
    "in summary,",
    "to summarize,",
    "to put it simply,",
    "in a nutshell,",
)


_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?(?:%|st|nd|rd|th)?\b")
# Capitalised multi-word names: rough proper-noun heuristic. Two or more
# capitalised tokens in a row count as one entity.
_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")


def _count_phrase_hits(text: str, patterns: Iterable[str]) -> list[str]:
    """Return the patterns that appear at least once in ``text`` (case-insensitive)."""
    lowered = text.lower()
    return [p for p in patterns if p in lowered]


def _repetition_score(tokens: list[str]) -> float:
    """Bigram repetition: fraction of bigrams that recur more than once."""
    if len(tokens) < 4:
        return 0.0
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]
    counts = Counter(bigrams)
    repeated = sum(1 for v in counts.values() if v > 1)
    return repeated / max(1, len(counts))


def analyse(text: str) -> dict:
    """Diagnose observable style signals without inferring semantic quality."""
    if not text or not text.strip():
        return {
            "filler_score": 0,
            "ai_pattern_score": 0,
            "information_density": None,
            "score_kind": "style-diagnostics",
            "semantic_quality": "unmeasured",
            "repetition_score": 0,
            "overall_quality": 0,
            "flags": ["empty-input"],
            "matches": {"filler": [], "ai_patterns": []},
            "tokens": 0,
            "unique_tokens": 0,
        }

    text = normalize_text(text)
    tokens = tokenize(text)
    n_tokens = len(tokens)
    unique = len(set(tokens))

    filler_hits = _count_phrase_hits(text, _FILLER_PHRASES)
    ai_hits = _count_phrase_hits(text, _AI_PATTERNS)

    # Density: entities + numbers per 100 tokens. A typical high-density
    # article (case studies, data journalism) lands at ~5+; a generic
    # filler post lands at <2.
    entities = len(_ENTITY_RE.findall(text))
    numbers = len(_NUMBER_RE.findall(text))
    density_per_100 = (entities + numbers) * 100.0 / max(1, n_tokens)
    is_korean = bool(re.search(r"[가-힣]", text))
    information_density = None if is_korean else min(1.0, density_per_100 / 10.0)

    rep = _repetition_score(tokens)
    rep_score = int(round(rep * 100))

    # Scale to per-1000 tokens so the score is comparable across page lengths.
    scale = max(1.0, n_tokens / 1000.0)
    filler_per_kt = len(filler_hits) / scale
    ai_per_kt = len(ai_hits) / scale

    filler_score = min(100, int(round(filler_per_kt * 25)))
    ai_pattern_score = min(100, int(round(ai_per_kt * 15)))

    flags: list[str] = []
    if filler_score >= 50:
        flags.append("filler")
    if ai_pattern_score >= 40:
        flags.append("ai-patterns")
    if rep_score >= 30:
        flags.append("repetitive")

    # Composite: invert penalty signals, weight by impact.
    overall = (
        (100 - filler_score) * 0.30
        + (100 - ai_pattern_score) * 0.30
        + (100 - rep_score) * 0.40
    )

    return {
        "filler_score": filler_score,
        "ai_pattern_score": ai_pattern_score,
        "information_density": round(information_density, 3) if information_density is not None else None,
        "score_kind": "style-diagnostics",
        "semantic_quality": "unmeasured",
        "limitations": ["Style patterns are not evidence of factuality, usefulness or AI authorship.",
                        "English name/number density is descriptive only; unavailable for Korean. No length bonus."],
        "repetition_score": rep_score,
        "overall_quality": int(round(overall)),
        "flags": flags,
        "matches": {"filler": filler_hits, "ai_patterns": ai_hits},
        "tokens": n_tokens,
        "unique_tokens": unique,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advisory style and repetition diagnostics."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Path to a text/HTML file, or '-' to read stdin (default '-').",
        default="-",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=60,
        help="Exit non-zero if overall_quality is below this (default 60).",
    )
    args = parser.parse_args()

    if args.source == "-":
        try:
            text = read_stream_limited(sys.stdin)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            text = read_text_limited(args.source)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    result = analyse(text)

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Style diagnostic:      {result['overall_quality']}/100 (semantic quality unmeasured)")
        print(f"  Filler score:        {result['filler_score']}/100 (higher = worse)")
        print(f"  AI-pattern score:    {result['ai_pattern_score']}/100 (higher = worse)")
        print(f"  Information density: {result['information_density']} (diagnostic only)")
        print(f"  Repetition:          {result['repetition_score']}/100 (higher = worse)")
        print(f"  Tokens:              {result['tokens']} ({result['unique_tokens']} unique)")
        if result["flags"]:
            print(f"  Flags:               {', '.join(result['flags'])}")
        if result["matches"]["filler"]:
            print(f"  Filler hits:         {', '.join(result['matches']['filler'][:5])}"
                  f"{' …' if len(result['matches']['filler']) > 5 else ''}")
        if result["matches"]["ai_patterns"]:
            print(f"  AI-pattern hits:     {', '.join(result['matches']['ai_patterns'][:5])}"
                  f"{' …' if len(result['matches']['ai_patterns']) > 5 else ''}")

    return 0 if result["overall_quality"] >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
