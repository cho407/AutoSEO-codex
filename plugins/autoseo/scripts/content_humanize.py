#!/usr/bin/env python3
"""
AI-pattern remover. Rewrites filler / AI-typical phrasings into
direct prose. Conservative by design: only replaces phrases listed in
``_REPLACEMENTS``. Unknown idiom? Leave it alone.

Use case: a content editor running last-mile cleanup on a draft. This
is NOT a paraphraser or a translation tool; it does not introduce new
content. English cleanup and conservative Korean calque cleanup are
deterministic. Ambiguous Korean phrasing is reported rather than guessed.

The replacement table is an AutoSEO-maintained set of conservative editorial
rules for common filler and promotional phrasing. It is intentionally small,
deterministic, and not an authorship detector.

CLI::

    python scripts/content_humanize.py draft.md -o cleaned.md
    cat draft.md | python scripts/content_humanize.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from file_safety import read_text_limited, write_text_safely

# AutoSEO replacements run in order. Each entry is (pattern, replacement, label).
# Patterns are compiled with re.IGNORECASE and \b word boundaries where
# appropriate. The replacement preserves the original case of the first
# character (e.g. "Leverage X" -> "Use X", not "use X").
_REPLACEMENTS: tuple[tuple[str, str, str], ...] = (
    (r"\bdelve\s+deeper\s+into\b", "explore", "delve-deeper-into"),
    (r"\bdelve\s+into\b", "explore", "delve-into"),
    (r"\bin\s+the\s+ever-evolving\s+landscape\s+of\b", "in", "ever-evolving-landscape"),
    (r"\bin\s+the\s+ever-evolving\s+world\s+of\b", "in", "ever-evolving-world"),
    (r"\bever-evolving\b", "changing", "ever-evolving"),
    (r"\bever-changing\b", "changing", "ever-changing"),
    (r"\bnavigating\s+the\s+complexities\s+of\b", "handling", "navigating-complexities"),
    (r"\btapestry\s+of\b", "range of", "tapestry-of"),
    (r"\b(rich|intricate|complex)\s+tapestry\b", "range", "rich-tapestry"),
    (r"\bembark\s+on\s+a\s+journey\b", "begin", "embark-journey"),
    (r"\ba\s+testament\s+to\b", "evidence of", "testament-to"),
    (r"\ba\s+beacon\s+of\b", "a leader in", "beacon-of"),
    (r"\b(the\s+|a\s+)?cornerstone\s+of\b", "central to", "cornerstone-of"),
    (r"\bat\s+the\s+heart\s+of\b", "central to", "at-the-heart-of"),
    (r"\bin\s+essence,\s*", "", "in-essence"),
    (r"\bin\s+conclusion,\s*", "", "in-conclusion"),
    (r"\bultimately,\s*", "", "ultimately-comma"),
    (r"\bmoreover,\s*", "", "moreover-comma"),
    (r"\bfurthermore,\s*", "", "furthermore-comma"),
    (r"\bhowever,\s+it'?s\s+worth\s+noting\s+that\b", "however,", "worth-noting-clause"),
    (r"\bit'?s\s+worth\s+noting\s+that\b", "note:", "worth-noting"),
    (r"\bby\s+leveraging\b", "by using", "by-leveraging"),
    (r"\bleverage\s+the\s+power\s+of\b", "use", "leverage-power"),
    (r"\bleveraging\s+the\s+power\s+of\b", "using", "leveraging-power"),
    (r"\bharness\s+the\s+power\s+of\b", "use", "harness-power"),
    (r"\bunlock\s+(?:the\s+(?:full\s+)?)?potential\b", "use", "unlock-potential"),
    (r"\bopen\s+up\s+a\s+world\s+of\b", "enable", "open-world"),
    (r"\ba\s+world\s+of\s+possibilities\b", "options", "world-possibilities"),
    (r"\belevate\s+your\b", "improve your", "elevate-your"),
    (r"\btransform\s+your\b", "improve your", "transform-your"),
    (r"\brevolutionize\s+the\s+way\b", "change how", "revolutionize-the-way"),
    (r"\bgame-?changer\b", "important", "game-changer"),
    (r"\bcutting-?edge\b", "modern", "cutting-edge"),
    (r"\bstate-of-the-art\b", "modern", "state-of-the-art"),
    (r"\bin\s+summary,\s*", "", "in-summary"),
    (r"\bto\s+summarize,\s*", "", "to-summarize"),
    (r"\bto\s+put\s+it\s+simply,\s*", "", "to-put-simply"),
    (r"\bin\s+a\s+nutshell,\s*", "", "in-nutshell"),
    (r"\bit'?s\s+important\s+to\s+note\s+that\b", "note:", "important-note"),
    (r"\bin\s+today'?s\s+(fast-paced|digital|competitive)\s+(world|age|landscape)\b",
     "today", "today-cliche"),
    (r"\bneedless\s+to\s+say,?\s*", "", "needless-to-say"),
    (r"\bat\s+the\s+end\s+of\s+the\s+day\b", "ultimately", "end-of-the-day"),
    (r"\bwhen\s+it\s+comes\s+to\b", "for", "when-it-comes-to"),
    (r"\bfirst\s+and\s+foremost,?\s*", "first,", "first-and-foremost"),
    (r"\blast\s+but\s+not\s+least,?\s*", "finally,", "last-but-not-least"),
    (r"\blet'?s\s+dive\s+(in|into)\b", "starting with", "let-us-dive"),
    (r"\blet'?s\s+take\s+a\s+(closer|deeper)\s+look\b", "look at", "let-us-take-look"),
)


_ENGLISH_PATTERNS = [
    (re.compile(p, re.IGNORECASE), repl, label)
    for p, repl, label in _REPLACEMENTS
]

_KOREAN_REPLACEMENTS: tuple[tuple[str, str, str], ...] = (
    (
        r"(확인|설정|사용|진행|제공|결정|고려|설명)(?:을|를)\s+하는 것이 가능합니다",
        r"\1할 수 있습니다",
        "명사화-가능합니다",
    ),
    (r"하는 것이 가능합니다", "할 수 있습니다", "가능합니다-번역투"),
    (
        r"(확인|설정|사용|진행|제공|결정|고려|설명)(?:을|를)\s+하",
        r"\1하",
        "불필요한-명사화",
    ),
    (r"되어집니다", "됩니다", "이중피동-되어집니다"),
    (r"되어지는", "되는", "이중피동-되어지는"),
    (r"되어질", "될", "이중피동-되어질"),
    (r"되어졌", "됐", "이중피동-되어졌"),
    (r"필요로 합니다", "필요합니다", "필요로-합니다"),
)
_KOREAN_PATTERNS = [
    (re.compile(pattern), replacement, label)
    for pattern, replacement, label in _KOREAN_REPLACEMENTS
]

_KOREAN_REVIEW_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"에 있어서"),
        "에-있어서",
        "문맥에 따라 '에서', '에는', 또는 문장 재구성이 자연스러울 수 있습니다.",
    ),
    (
        re.compile(r"에 의해"),
        "에-의해",
        "행위 주체가 중요하면 능동문으로 바꿀 수 있지만 사실관계를 먼저 확인하세요.",
    ),
    (
        re.compile(r"(?:이것|그것)은"),
        "지시대명사",
        "무엇을 가리키는지 명사로 밝혀야 하는지 확인하세요.",
    ),
    (
        re.compile(r"라는 것을 알 수 있(?:습니다|어요)"),
        "라는-것을-알-수",
        "근거가 명확하면 결론을 직접 말하는 편이 자연스러울 수 있습니다.",
    ),
)

_TONE_ENDINGS: dict[str, str] = {
    "friendly": "haeyo",
    "expert-friendly": "haeyo",
    "conversational": "haeyo",
    "warm": "haeyo",
    "persuasive": "haeyo",
    "professional": "hamnida",
    "concise": "hamnida",
    "custom": "custom",
}


def _preserve_case(match_text: str, replacement: str) -> str:
    """If the original starts uppercase, capitalise the replacement."""
    if not replacement:
        return ""
    if match_text and match_text[0].isupper() and not replacement[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _language(text: str, requested: str) -> str:
    if requested != "auto":
        return requested
    korean = sum("가" <= char <= "힣" for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    return "ko" if korean > latin else "en"


def _review_findings(text: str) -> list[dict]:
    findings: list[dict] = []
    for pattern, label, guidance in _KOREAN_REVIEW_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            findings.append(
                {
                    "label": label,
                    "count": len(matches),
                    "examples": [match.group(0) for match in matches[:3]],
                    "guidance": guidance,
                    "automatic": False,
                }
            )
    return findings


def _tone_validation(text: str, tone: str | None) -> dict:
    requested_ending = _TONE_ENDINGS.get(tone or "")
    if not tone:
        return {
            "requested": None,
            "expected_ending": None,
            "compliant": None,
            "matching_endings": 0,
            "conflicting_endings": 0,
            "note": "No tone preset was requested.",
        }
    if requested_ending == "custom":
        return {
            "requested": tone,
            "expected_ending": "custom",
            "compliant": None,
            "matching_endings": 0,
            "conflicting_endings": 0,
            "note": "Custom tone requires semantic review against the confirmed profile.",
        }
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+|\n+", text)
        if item.strip()
    ]
    friendly = sum(bool(re.search(r"요[.!?]?$", item)) for item in sentences)
    formal = sum(
        bool(re.search(r"(?:니다|십시오)[.!?]?$", item))
        for item in sentences
    )
    matching = friendly if requested_ending == "haeyo" else formal
    conflicting = formal if requested_ending == "haeyo" else friendly
    compliant = matching > 0 and conflicting == 0
    note = (
        "Sentence endings match the requested preset."
        if compliant
        else "Review mixed or unmatched sentence endings before publication."
    )
    return {
        "requested": tone,
        "expected_ending": requested_ending,
        "compliant": compliant,
        "matching_endings": matching,
        "conflicting_endings": conflicting,
        "note": note,
    }


def humanize(text: str, *, language: str = "auto", tone: str | None = None) -> dict:
    """Apply safe replacements and return cleanup plus Korean diagnostics."""
    if language not in {"auto", "en", "ko"}:
        raise ValueError("language must be auto, en, or ko")
    if tone is not None and tone not in _TONE_ENDINGS:
        raise ValueError(f"unsupported tone preset: {tone}")
    changes: list[dict] = []
    cleaned = text
    detected_language = _language(text, language)
    patterns = list(_ENGLISH_PATTERNS)
    if detected_language == "ko":
        patterns.extend(_KOREAN_PATTERNS)

    for pattern, replacement, label in patterns:
        def _repl(match):
            original = match.group(0)
            new = _preserve_case(original, match.expand(replacement))
            changes.append({
                "label": label,
                "from": original,
                "to": new,
            })
            return new
        cleaned = pattern.sub(_repl, cleaned)

    # Collapse double spaces introduced by deleted phrases, but leave
    # newlines and intentional spacing alone.
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r" ([,.;:!?])", r"\1", cleaned)

    return {
        "cleaned": cleaned,
        "changes": changes,
        "change_count": len(changes),
        "language": detected_language,
        "translationese_findings": (
            _review_findings(cleaned) if detected_language == "ko" else []
        ),
        "tone_validation": _tone_validation(cleaned, tone),
        "limitations": [
            "Only meaning-preserving deterministic replacements are automatic.",
            "Natural Korean flow and custom voice still require semantic editorial review.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Conservative draft polish and Korean tone diagnostic."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Path to a text/markdown file, or '-' for stdin (default '-').",
        default="-",
    )
    parser.add_argument("--output", "-o", help="Write cleaned text to this path.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of an existing output file",
    )
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON with cleaned text + change log.")
    parser.add_argument(
        "--language",
        choices=("auto", "en", "ko"),
        default="auto",
        help="Language used for deterministic cleanup (default: auto).",
    )
    parser.add_argument(
        "--tone",
        choices=tuple(_TONE_ENDINGS),
        help="Validate Korean sentence endings against a writing tone preset.",
    )
    args = parser.parse_args()

    if args.source == "-":
        text = sys.stdin.read()
    else:
        try:
            text = read_text_limited(args.source)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    try:
        result = humanize(text, language=args.language, tone=args.tone)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.output:
        try:
            output_path = write_text_safely(
                args.output,
                result["cleaned"],
                overwrite=args.overwrite,
                extensions={".md", ".markdown", ".txt"},
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(
            f"Wrote {output_path} ({result['change_count']} replacements)",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(result["cleaned"])

    if result["change_count"]:
        print(f"\n--- {result['change_count']} replacements ---", file=sys.stderr)
        seen: set[str] = set()
        for change in result["changes"]:
            key = change["label"]
            if key in seen:
                continue
            seen.add(key)
            print(f"  {change['from']!r} -> {change['to']!r}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
