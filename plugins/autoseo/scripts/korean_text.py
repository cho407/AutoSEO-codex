#!/usr/bin/env python3
"""Small dependency-free Korean normalization, token, and intent helpers."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

TOKEN_RE = re.compile(
    r"[가-힣]+|[A-Za-z]+(?:['-][A-Za-z]+)*|\d+(?:[.,]\d+)?",
    re.UNICODE,
)
_SPACE_RE = re.compile(r"\s+")

INTENT_TERMS = {
    "informational": {
        "무엇",
        "뭐",
        "뜻",
        "왜",
        "어떻게",
        "방법",
        "가이드",
        "정보",
        "알려",
        "what",
        "why",
        "how",
        "guide",
        "meaning",
        "tutorial",
    },
    "commercial": {
        "가격",
        "비교",
        "후기",
        "리뷰",
        "추천",
        "장단점",
        "견적",
        "best",
        "compare",
        "price",
        "review",
        "recommend",
    },
    "local": {
        "근처",
        "주변",
        "위치",
        "지역",
        "맛집",
        "병원",
        "매장",
        "서울",
        "부산",
        "제주",
        "near",
        "nearby",
        "location",
    },
    "transactional": {
        "구매",
        "주문",
        "예약",
        "신청",
        "가입",
        "결제",
        "다운로드",
        "문의하기",
        "buy",
        "book",
        "order",
        "apply",
        "download",
        "subscribe",
    },
}
_INTENT_PRIORITY = ("transactional", "local", "commercial", "informational")


def normalize_text(value: str) -> str:
    """Return NFKC-normalized text with stable whitespace."""
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def tokenize(value: str) -> list[str]:
    """Tokenize Korean, Latin words, and numbers without an external model."""
    normalized = normalize_text(value)
    return [token.casefold() for token in TOKEN_RE.findall(normalized)]


def classify_intent(value: str) -> dict[str, Any]:
    """Classify Korean or English query intent with transparent term matches."""
    normalized = normalize_text(value).casefold()
    tokens = set(tokenize(normalized))
    matches: dict[str, list[str]] = {}
    for intent, terms in INTENT_TERMS.items():
        found = sorted(
            term
            for term in terms
            if term.casefold() in tokens or term.casefold() in normalized
        )
        if found:
            matches[intent] = found
    primary = next((intent for intent in _INTENT_PRIORITY if intent in matches), None)
    return {
        "primary": primary or "mixed-or-unclear",
        "matches": matches,
        "method": "nfkc-transparent-intent-lexicon-v1",
    }
