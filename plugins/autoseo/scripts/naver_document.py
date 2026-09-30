#!/usr/bin/env python3
"""Validate NaverDocument v1 and compile deterministic editor operations."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from typing import Any

from blog_format import catalog as format_catalog
from blog_format import effective_style, validate_preset, validate_role
from blog_image import normalize_generated_images
from file_safety import resolve_input_file
from url_safety import validate_url

SCHEMA_VERSION = 1
MAX_BLOCKS = 300
MAX_TOTAL_TEXT_CHARS = 1_000_000
MAX_TAGS = 30
MAX_ATTACHMENTS = 50
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_SCHEDULE_DAYS = 365

DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
BLOCK_TYPES = {
    "paragraph",
    "heading",
    "quote",
    "special-character",
    "divider",
    "photo",
    "group-photo",
    "sticker",
    "video",
    "place",
    "multi-attach",
    "external-link",
    "file",
    "schedule",
    "table",
    "equation",
    "template",
    "library",
    "talktalk",
}
TEXT_BLOCK_TYPES = {"paragraph", "heading", "quote", "special-character"}
PATH_BLOCK_TYPES = {"photo", "video", "file"}
GUIDED_BLOCK_TYPES = {
    "sticker",
    "place",
    "template",
    "library",
    "talktalk",
}
BLOCK_FEATURES = {
    "paragraph": "paragraph",
    "heading": "heading",
    "quote": "quote",
    "special-character": "special-character",
    "divider": "divider",
    "photo": "photo",
    "group-photo": "group-photo",
    "sticker": "sticker",
    "video": "video",
    "place": "place",
    "multi-attach": "multi-attach",
    "external-link": "external-link",
    "file": "file",
    "schedule": "schedule-component",
    "table": "table",
    "equation": "equation",
    "template": "template",
    "library": "library",
    "talktalk": "talktalk",
}
STYLE_KEYS = {
    "font",
    "size",
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "color",
    "alignment",
    "line_spacing",
    "superscript",
    "subscript",
}
DEFAULT_PUBLISH_SETTINGS = {
    "mode": "draft",
    "category": None,
    "visibility": "public",
    "search_allowed": True,
    "comments_allowed": True,
    "sympathy_allowed": True,
    "ccl": "none",
    "share_allowed": True,
    "scheduled_at": None,
}

# This surface is Naver-only. It never changes the shared layout preset defaults.
NATIVE_FONT_SIZES = frozenset({11, 13, 15, 16, 19, 24, 28, 30, 34, 38})
NATIVE_ROLE_SIZES = {
    "short-answer": {15, 16},
    "intro": {15, 16},
    "question-heading": {19, 24},
    "minor-heading": {16, 19},
    "summary": {16, 19},
    "caution": {16, 19},
    "quote": {16, 19},
    "body": {15, 16},
    "detail": {15, 16},
    "caption": {11, 13},
    "source-heading": {15, 16, 19},
    "source": {11, 13},
}
NATIVE_BOLD_ROLES = {"question-heading", "minor-heading", "summary", "caution", "source-heading"}
NATIVE_MEDIA_ROLES = {"cover", "explainer"}
NATIVE_PROFILE_FIELDS = {"schema_version", "preset", "roles", "source_divider", "media", "max_callouts"}
NATIVE_LIST_MARKERS = {"neutral": "", "circle": "● "}
NATIVE_BLOCK_FIELDS = {
    "paragraph": {"id", "type", "text", "style", "links", "format_role", "design_role", "list_marker_style", "spacing_before"},
    "heading": {"id", "type", "text", "level", "style", "links", "design_role", "spacing_before"},
    "quote": {"id", "type", "text", "style", "links", "design_role", "spacing_before"},
    "photo": {"id", "type", "path", "design_role", "design_review", "related_block_id"},
    "divider": {"id", "type", "design_role"},
}


def _validate_native_style(role: str, style: object, *, partial: bool = False) -> dict[str, Any]:
    if not isinstance(style, dict) or set(style) - {"size", "bold", "alignment", "line_spacing"}:
        raise ValueError("native design styles allow only size, bold, alignment and line_spacing")
    if not partial and not {"size", "bold"} <= set(style):
        raise ValueError("native design styles require size and bold")
    if "size" in style and (
        type(style["size"]) is not int
        or style["size"] not in NATIVE_FONT_SIZES
        or style["size"] not in NATIVE_ROLE_SIZES[role]
    ):
        raise ValueError(f"unsupported native design size for {role}")
    if "bold" in style and (
        type(style["bold"]) is not bool or style["bold"] != (role in NATIVE_BOLD_ROLES)
    ):
        raise ValueError(f"native design emphasis conflicts with {role}")
    if "alignment" in style and style["alignment"] not in ("left", "center"):
        raise ValueError("unsupported native alignment")
    if "line_spacing" in style and (
        type(style["line_spacing"]) not in (int, float)
        or style["line_spacing"] not in (1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1)
    ):
        raise ValueError("unsupported native line_spacing")
    return copy.deepcopy(style)


def validate_design_profile(profile: object) -> dict[str, Any]:
    """Explicit data only: no account identity, paths, URLs, selectors or code."""
    if not isinstance(profile, dict) or set(profile) - NATIVE_PROFILE_FIELDS:
        raise ValueError("unsupported native design profile fields")
    if type(profile.get("schema_version")) is not int or profile["schema_version"] != 1:
        raise ValueError("native design profile schema_version must be 1")
    if profile.get("preset") != "compact-native":
        raise ValueError("unsupported native design preset")
    defaults = format_catalog()["naver_native_design"]
    overrides = profile.get("roles", {})
    if not isinstance(overrides, dict) or set(overrides) - NATIVE_ROLE_SIZES.keys():
        raise ValueError("unsupported native design roles")
    roles = {
        role: _validate_native_style(
            role, {**defaults["roles"][role], **_validate_native_style(role, overrides.get(role, {}), partial=True)}
        )
        for role in NATIVE_ROLE_SIZES
    }
    divider = profile.get("source_divider", defaults["source_divider"])
    media = profile.get("media", defaults["media"])
    callouts = profile.get("max_callouts", defaults["max_callouts"])
    if divider not in ("none", "single"):
        raise ValueError("native source_divider must be none or single")
    if media not in ("optional", "reviewed-cover-and-explainer"):
        raise ValueError("unsupported native media expectation")
    if type(callouts) is not int or callouts not in (0, 1, 2):
        raise ValueError("native max_callouts must be 0, 1 or 2")
    return {
        "schema_version": 1,
        "preset": "compact-native",
        "roles": roles,
        "source_divider": divider,
        "media": media,
        "max_callouts": callouts,
    }


def native_design_role(block: dict[str, Any]) -> str:
    if "design_role" in block:
        return block["design_role"]
    if block["type"] == "paragraph":
        return block.get("format_role", "body")
    if block["type"] == "heading":
        return "question-heading" if block.get("level", 2) == 2 else "minor-heading"
    if block["type"] == "quote":
        return "quote"
    if block["type"] == "divider":
        return "source-divider"
    return block["type"]


def _native_style(block: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    role = native_design_role(block)
    explicit = _validate_native_style(role, block.get("style", {}), partial=True)
    return {**profile["roles"][role], **explicit}


def rendered_text(block: dict[str, Any]) -> str:
    """Render the explicit marker once; never mutate the source block."""
    text = block["text"]
    if block.get("list_marker_style", "neutral") == "circle" and not text.startswith("●"):
        return NATIVE_LIST_MARKERS["circle"] + text
    return text


def _validate_native_design(document: dict[str, Any]) -> None:
    profile = document.get("design_profile")
    blocks = document["blocks"]
    if profile is None:
        if any(set(block) & {"design_role", "design_review", "related_block_id", "list_marker_style", "spacing_before"} for block in blocks):
            raise ValueError("native design fields require an explicit design_profile")
        return
    if document.get("layout_preset") not in (None, "none"):
        raise ValueError("design_profile and an active layout_preset cannot be combined")
    if document["background"] != {"type": "none"}:
        raise ValueError("native design does not support background styling or unreviewed background media")
    roles = [native_design_role(block) for block in blocks]
    callout_roles = {"quote", "summary", "caution"}
    callouts = sum(role in callout_roles for role in roles)
    if callouts > profile["max_callouts"]:
        raise ValueError("native design exceeds max_callouts; do not decorate every paragraph")
    if any(roles.count(role) > 1 for role in callout_roles):
        raise ValueError("native design forbids duplicated callout roles")
    for index, (block, role) in enumerate(zip(blocks, roles)):
        allowed_fields = NATIVE_BLOCK_FIELDS.get(block["type"])
        if allowed_fields is None or set(block) - allowed_fields:
            raise ValueError("unsupported fields or block type for native design")
        if block["type"] in TEXT_BLOCK_TYPES:
            if block.get("spacing_before", "normal") not in ("normal", "section"):
                raise ValueError("unsupported native spacing_before")
            if block.get("spacing_before") == "section" and (
                index == 0 or blocks[index - 1]["type"] not in TEXT_BLOCK_TYPES
            ):
                raise ValueError("section spacing requires a preceding semantic text boundary")
            if role not in NATIVE_ROLE_SIZES:
                raise ValueError("unsupported native text role")
            if "format_role" in block and "design_role" in block and block["format_role"] != role:
                raise ValueError("format_role and design_role conflict")
            _native_style(block, profile)
            text = block["text"].replace("\r\n", "\n").replace("\r", "\n")
            if text != text.strip() or any(not line.strip() for line in text.split("\n")):
                raise ValueError("native design forbids blank spacer lines and padded paragraphs")
            if role not in {"body", "detail", "source"} and "\n" in text:
                raise ValueError("compact native roles require one semantic paragraph")
            if role in callout_roles and any(
                other["id"] != block["id"] and other["type"] in TEXT_BLOCK_TYPES
                and " ".join(other["text"].split()) == " ".join(text.split())
                for other in blocks
            ):
                raise ValueError("native design forbids duplicated callout content")
            if block["type"] == "heading" and (
                (role == "question-heading" and block.get("level", 2) != 2)
                or (role == "minor-heading" and block.get("level", 2) != 3)
            ):
                raise ValueError("native heading level conflicts with design_role")
            if "list_marker_style" in block and (
                block["type"] != "paragraph" or role not in {"body", "detail"} or "\n" in text
            ):
                raise ValueError("native list markers require a single body or detail paragraph")
            if role in {"question-heading", "minor-heading", "source-heading"} and (
                index + 1 == len(blocks) or roles[index + 1] in NATIVE_BOLD_ROLES
            ):
                raise ValueError("native headings require a following non-heading content block")
            if role == "caption" and (index == 0 or blocks[index - 1]["type"] != "photo"):
                raise ValueError("native captions must immediately follow their image")
            if role == "source" and (
                not block.get("links")
                or any(link["text"] == link["url"] for link in block["links"])
            ):
                raise ValueError("native sources require readable labeled links")
        elif block["type"] == "photo":
            if role not in NATIVE_MEDIA_ROLES:
                raise ValueError("native photos require a cover or explainer design_role")
            review = block.get("design_review")
            if (
                not isinstance(review, dict)
                or set(review) != {"approved", "sha256", "provenance", "relevance_checked"}
                or review["approved"] is not True
                or review["relevance_checked"] is not True
                or review["provenance"] not in ("original", "licensed", "public-domain", "authorized")
                or not isinstance(review["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", review["sha256"])
            ):
                raise ValueError("native media requires an approved, relevant, hash-bound provenance review")
            if block.get("replace_path") or block.get("properties") or block.get("edit_actions"):
                raise ValueError("native design cannot replace or edit media")
            if role == "cover":
                if "related_block_id" in block:
                    raise ValueError("native cover does not take related_block_id")
                if any(item in {"question-heading", "minor-heading", "detail", "source-heading", "source"} for item in roles[:index]):
                    raise ValueError("native cover must precede the detailed sections")
            else:
                related = block.get("related_block_id")
                neighbors = []
                if index:
                    neighbors.append(blocks[index - 1])
                following = index + 1
                if following < len(blocks) and roles[following] == "caption":
                    following += 1
                if following < len(blocks):
                    neighbors.append(blocks[following])
                if not isinstance(related, str) or not any(
                    neighbor["id"] == related and neighbor["type"] in {"paragraph", "heading"}
                    and native_design_role(neighbor) not in {"caption", "source", "source-heading"}
                    for neighbor in neighbors
                ):
                    raise ValueError("native explainer must be adjacent to its related content block")
        elif block["type"] != "divider":
            raise ValueError("native design supports text, reviewed photos and a source divider only")

    if roles.count("cover") > 1:
        raise ValueError("native design allows one cover")
    if profile["media"] == "reviewed-cover-and-explainer" and (
        roles.count("cover") != 1 or "explainer" not in roles
    ):
        raise ValueError("native design requires one reviewed cover and a relevant explainer")
    source_indexes = [index for index, role in enumerate(roles) if role in {"source-heading", "source"}]
    if source_indexes:
        first = source_indexes[0]
        if source_indexes != list(range(first, len(blocks))) or "source" not in roles[first:]:
            raise ValueError("native sources must form one final source section")
        if roles.count("source-heading") > 1 or (
            "source-heading" in roles and roles[first] != "source-heading"
        ):
            raise ValueError("native source heading must uniquely start the source section")
    dividers = [index for index, block in enumerate(blocks) if block["type"] == "divider"]
    if profile["source_divider"] == "none" and dividers:
        raise ValueError("native source divider is not requested")
    if profile["source_divider"] == "single":
        if not source_indexes or source_indexes[0] == 0:
            raise ValueError("a single source divider requires an exact content/source boundary")
        if len(dividers) > 1 or (dividers and dividers[0] != source_indexes[0] - 1):
            raise ValueError("only one native divider immediately above sources is allowed")
        boundary = source_indexes[0] - (2 if dividers else 1)
        if boundary < 0 or roles[boundary] in {"source-heading", "source", "source-divider"}:
            raise ValueError("native source divider has no exact preceding content block")
    require_design_media_reviews(document)


def native_design_plan(document: object) -> dict[str, Any]:
    """Deterministic plan, not a claim of live quote/divider/upload readiness."""
    value = validate_document(document)
    profile = value.get("design_profile")
    if profile is None:
        raise ValueError("native design planning requires an explicit design_profile")
    paragraphs = []
    media = []
    blocks = value["blocks"]
    for block in blocks:
        role = native_design_role(block)
        if block["type"] in TEXT_BLOCK_TYPES:
            marker_style = block.get("list_marker_style", "neutral")
            marker = {
                "style": marker_style,
                "prefix": NATIVE_LIST_MARKERS[marker_style],
                "availability": "not-requested" if marker_style == "neutral" else "unavailable",
                "gate": "none" if marker_style == "neutral" else "list-marker-rendering-unverified",
            }
            if marker_style != "neutral":
                marker["preview_text"] = rendered_text(block)
            paragraphs.append({
                "block_id": block["id"], "role": role, "style": _native_style(block, profile),
                "native_target": "quote" if role == "quote" else "paragraph-property-toolbar",
                "availability": "unavailable",
                "gate": "quote-placement-unverified" if role == "quote" else "input-buffer-native-formatting-unverified",
                "verification_required": "exact-buffer-and-computed-style",
                "list_marker": marker,
                "spacing_before": block.get("spacing_before", "normal"),
                "rendered_text": rendered_text(block),
                "transition": "one-native-empty-paragraph" if block.get("spacing_before") == "section" else "semantic-paragraph-boundary-no-spacers",
            })
        elif block["type"] == "photo":
            media.append({
                "block_id": block["id"], "role": role,
                "related_block_id": block.get("related_block_id"),
                "availability": "unavailable",
                "gate": "reviewed-asset-and-exact-hosted-placement; upload-unverified",
            })
    divider: dict[str, Any] = {
        "mode": profile["source_divider"], "action": "none", "availability": "not-requested",
    }
    if profile["source_divider"] == "single":
        source_index = next(index for index, block in enumerate(blocks) if native_design_role(block) in {"source-heading", "source"})
        existing = blocks[source_index - 1]["type"] == "divider"
        divider.update(
            action="verify-existing" if existing else "insert-unavailable",
            availability="unavailable",
            before_block_id=blocks[source_index]["id"],
            after_block_id=blocks[source_index - (2 if existing else 1)]["id"],
            existing_block_id=blocks[source_index - 1]["id"] if existing else None,
            gate="divider-placement-unverified; exact-native-boundary-readback-required",
        )
    return {
        "schema_version": 1, "document_id": value["document_id"], "profile": profile,
        "paragraphs": paragraphs, "divider": divider, "media": media,
        "writes_performed": False, "live_publish_ready": False,
        "save_boundary": "separate-authorized-draft-save",
        "publication_boundary": "separate-exact-settings-approval-and-public-readback",
    }


def _attachment_limit(block_type: str, override: int | None) -> int:
    if override is not None:
        return override
    if block_type == "video":
        return MAX_VIDEO_BYTES
    if block_type in {"photo", "group-photo", "sticker"}:
        return MAX_IMAGE_BYTES
    return MAX_FILE_BYTES


def _validate_attachment(
    raw_path: object,
    *,
    block_type: str,
    max_attachment_bytes: int | None,
) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{block_type} attachment path is required")
    path = resolve_input_file(raw_path)
    limit = _attachment_limit(block_type, max_attachment_bytes)
    if path.stat().st_size > limit:
        raise ValueError(
            f"{block_type} attachment exceeds the {limit}-byte attachment limit"
        )
    return str(path)


def validate_schedule(
    value: str, *, now: datetime | None = None
) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("scheduled_at must be an ISO 8601 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduled_at must include a timezone")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if parsed <= reference:
        raise ValueError("scheduled_at must be in the future")
    if parsed > reference + timedelta(days=MAX_SCHEDULE_DAYS):
        raise ValueError(f"scheduled_at must be within {MAX_SCHEDULE_DAYS} days")
    return value


def _validate_style(style: object) -> dict[str, Any]:
    if style is None:
        return {}
    if not isinstance(style, dict):
        raise ValueError("block style must be an object")
    unknown = set(style) - STYLE_KEYS
    if unknown:
        raise ValueError(f"unsupported style fields: {sorted(unknown)}")
    normalized = copy.deepcopy(style)
    for field in (
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "superscript",
        "subscript",
    ):
        if field in normalized and not isinstance(normalized[field], bool):
            raise ValueError(f"style.{field} must be boolean")
    if "alignment" in normalized and normalized["alignment"] not in {
        "left",
        "center",
        "right",
        "justify",
    }:
        raise ValueError("style.alignment is unsupported")
    if "color" in normalized and not COLOR_RE.fullmatch(str(normalized["color"])):
        raise ValueError("style.color must use #RRGGBB")
    return normalized


def _validate_links(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError("block links must be a list with at most 50 entries")
    links: list[dict[str, Any]] = []
    for link in value:
        if not isinstance(link, dict) or not isinstance(link.get("url"), str):
            raise ValueError("each text link requires a URL")
        if not validate_url(link["url"]):
            raise ValueError("text links must use a public HTTP(S) URL")
        label = str(link.get("text") or "").strip()
        if not label:
            raise ValueError("each text link requires non-empty anchor text")
        links.append({"text": label, "url": link["url"]})
    return links


def _bounded_mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field} must be a non-empty object")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded) > 20_000:
        raise ValueError(f"{field} exceeds the 20000-character limit")
    return copy.deepcopy(value)


def _validate_block(
    block: object,
    *,
    max_attachment_bytes: int | None,
) -> tuple[dict[str, Any], int, int]:
    if not isinstance(block, dict):
        raise ValueError("each block must be an object")
    unknown = set(block) - {
        "id", "type", "text", "level", "style", "format_role", "links",
        "path", "replace_path", "properties", "edit_actions", "paths", "url", "query",
        "start", "end", "rows", "expression", "template_id", "library_item_id",
        "talktalk_id", "sticker_id", "design_role", "design_review", "related_block_id",
        "list_marker_style", "spacing_before",
    }
    if unknown:
        raise ValueError(f"unsupported block fields: {sorted(unknown)}")
    identifier = block.get("id")
    if not isinstance(identifier, str) or not DOCUMENT_ID_RE.fullmatch(identifier):
        raise ValueError("each block requires a stable alphanumeric id")
    block_type = block.get("type")
    if block_type not in BLOCK_TYPES:
        raise ValueError(f"unsupported block type: {block_type}")
    allowed_paths = {"path"} if block_type in PATH_BLOCK_TYPES else set()
    if block_type == "photo":
        allowed_paths.add("replace_path")
    if block_type in {"group-photo", "multi-attach"}:
        allowed_paths.add("paths")
    if (set(block) & {"path", "paths", "replace_path"}) - allowed_paths:
        raise ValueError(f"unsupported attachment fields for {block_type} block")
    normalized = copy.deepcopy(block)
    validate_role(block)
    if "design_role" in block:
        role = block["design_role"]
        allowed_roles = {
            "paragraph": set(NATIVE_ROLE_SIZES) - {"quote"},
            "heading": {"question-heading", "minor-heading", "source-heading"},
            "quote": {"quote"},
            "photo": NATIVE_MEDIA_ROLES,
            "divider": {"source-divider"},
        }.get(block_type, set())
        if not isinstance(role, str) or role not in allowed_roles:
            raise ValueError("design_role conflicts with the native block type")
    if block_type != "photo" and set(block) & {"design_review", "related_block_id"}:
        raise ValueError("native media metadata requires a photo block")
    if "spacing_before" in block and block_type not in TEXT_BLOCK_TYPES:
        raise ValueError("spacing_before requires a text block")
    if "list_marker_style" in block and (
        block_type != "paragraph" or not isinstance(block["list_marker_style"], str)
        or block["list_marker_style"] not in NATIVE_LIST_MARKERS
    ):
        raise ValueError("unsupported native paragraph list_marker_style")
    text_chars = 0
    attachment_count = 0
    if block_type in TEXT_BLOCK_TYPES:
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{block_type} block text is required")
        if len(text) > 100_000:
            raise ValueError("one text block cannot exceed 100000 characters")
        normalized["text"] = text
        normalized["style"] = _validate_style(block.get("style"))
        normalized["links"] = _validate_links(block.get("links"))
        for link in normalized["links"]:
            if text.count(link["text"]) != 1:
                raise ValueError(
                    "text link anchor must occur exactly once in its text block"
                )
        text_chars += len(text)
        if block_type == "heading" and block.get("level", 2) not in {2, 3}:
            raise ValueError("heading level must be 2 or 3")
    elif block_type in PATH_BLOCK_TYPES:
        normalized["path"] = _validate_attachment(
            block.get("path"),
            block_type=block_type,
            max_attachment_bytes=max_attachment_bytes,
        )
        attachment_count += 1
        if block_type == "photo" and block.get("replace_path") is not None:
            normalized["replace_path"] = _validate_attachment(
                block.get("replace_path"),
                block_type="photo",
                max_attachment_bytes=max_attachment_bytes,
            )
            attachment_count += 1
        if block_type == "photo" and block.get("properties") is not None:
            normalized["properties"] = _bounded_mapping(
                block.get("properties"), field="photo properties"
            )
        if block_type == "photo" and block.get("edit_actions") is not None:
            actions = block.get("edit_actions")
            if (
                not isinstance(actions, list)
                or not 1 <= len(actions) <= 20
                or any(not isinstance(action, dict) or not action for action in actions)
            ):
                raise ValueError("photo edit_actions must contain 1-20 action objects")
            normalized["edit_actions"] = copy.deepcopy(actions)
    elif block_type in {"group-photo", "multi-attach"}:
        paths = block.get("paths")
        if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
            raise ValueError(f"{block_type} requires between 1 and 20 paths")
        normalized["paths"] = [
            _validate_attachment(
                path,
                block_type="photo" if block_type == "group-photo" else "file",
                max_attachment_bytes=max_attachment_bytes,
            )
            for path in paths
        ]
        attachment_count += len(paths)
    elif block_type == "external-link":
        url = block.get("url")
        if not isinstance(url, str) or not validate_url(url):
            raise ValueError("external-link requires a public HTTP(S) URL")
    elif block_type == "table":
        rows = block.get("rows")
        if (
            not isinstance(rows, list)
            or not 1 <= len(rows) <= 50
            or any(not isinstance(row, list) or len(row) > 20 for row in rows)
        ):
            raise ValueError("table requires 1-50 rows and at most 20 columns")
        text_chars += sum(len(str(cell)) for row in rows for cell in row)
    elif block_type == "equation":
        expression = block.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("equation expression is required")
        text_chars += len(expression)
    elif block_type == "schedule":
        if not isinstance(block.get("start"), str) or not block["start"].strip():
            raise ValueError("schedule component start is required")
    elif block_type == "place":
        if not str(block.get("query") or "").strip():
            raise ValueError("place requires a search query")
    elif block_type == "sticker":
        if not str(block.get("sticker_id") or block.get("query") or "").strip():
            raise ValueError("sticker requires a sticker_id or search query")
    elif block_type == "template":
        if not str(block.get("template_id") or block.get("query") or "").strip():
            raise ValueError("template requires a template_id or search query")
    elif block_type == "library":
        if not str(block.get("library_item_id") or block.get("query") or "").strip():
            raise ValueError("library requires a library_item_id or search query")
    elif block_type == "talktalk":
        if not str(block.get("talktalk_id") or "").strip():
            raise ValueError("talktalk requires a talktalk_id")
    return normalized, text_chars, attachment_count


def validate_document(
    document: object,
    *,
    max_attachment_bytes: int | None = None,
) -> dict[str, Any]:
    """Validate and normalize a NaverDocument v1 object."""
    if not isinstance(document, dict):
        raise ValueError("NaverDocument must be an object")
    unknown = set(document) - {
        "schema_version", "document_id", "title", "layout_preset", "design_profile",
        "generated_images", "background", "blocks", "tags", "publish_settings", "editor_options",
    }
    if unknown:
        raise ValueError(f"unsupported document fields: {sorted(unknown)}")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("NaverDocument schema_version must be 1")
    document_id = document.get("document_id")
    if not isinstance(document_id, str) or not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("document_id must be a safe stable identifier")
    title = document.get("title")
    preset = validate_preset(document["layout_preset"]) if "layout_preset" in document else None
    design_profile = validate_design_profile(document["design_profile"]) if "design_profile" in document else None
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("title must contain between 1 and 200 characters")
    background = document.get("background", {"type": "none"})
    if not isinstance(background, dict) or background.get("type") not in {
        "none",
        "color",
        "image",
    }:
        raise ValueError("background type must be none, color, or image")
    if set(background) - {"type", "value", "path"}:
        raise ValueError("unsupported background fields")
    normalized_background = copy.deepcopy(background)
    if background["type"] == "color" and not COLOR_RE.fullmatch(
        str(background.get("value") or "")
    ):
        raise ValueError("background color must use #RRGGBB")
    if background["type"] == "image":
        normalized_background["path"] = _validate_attachment(
            background.get("path"),
            block_type="photo",
            max_attachment_bytes=max_attachment_bytes,
        )

    blocks = document.get("blocks")
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS:
        raise ValueError(f"blocks must contain between 1 and {MAX_BLOCKS} entries")
    normalized_blocks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_text = len(title)
    total_attachments = 1 if background["type"] == "image" else 0
    for block in blocks:
        normalized, text_chars, attachment_count = _validate_block(
            block, max_attachment_bytes=max_attachment_bytes
        )
        if normalized["id"] in seen_ids:
            raise ValueError(f"duplicate block id: {normalized['id']}")
        seen_ids.add(normalized["id"])
        normalized_blocks.append(normalized)
        total_text += text_chars
        total_attachments += attachment_count
    if total_text > MAX_TOTAL_TEXT_CHARS:
        raise ValueError(f"document text exceeds {MAX_TOTAL_TEXT_CHARS} characters")
    if total_attachments > MAX_ATTACHMENTS:
        raise ValueError(f"document exceeds {MAX_ATTACHMENTS} attachments")

    tags = document.get("tags", [])
    if (
        not isinstance(tags, list)
        or len(tags) > MAX_TAGS
        or any(not isinstance(tag, str) or not tag.strip() or len(tag) > 50 for tag in tags)
    ):
        raise ValueError(f"tags must contain at most {MAX_TAGS} non-empty values")
    raw_settings = document.get("publish_settings")
    if raw_settings is not None and (
        not isinstance(raw_settings, dict) or set(raw_settings) - DEFAULT_PUBLISH_SETTINGS.keys()
    ):
        raise ValueError("unsupported publish_settings fields")
    settings = {**DEFAULT_PUBLISH_SETTINGS, **(raw_settings or {})}
    if settings["mode"] not in {"draft", "publish", "schedule"}:
        raise ValueError("publish_settings.mode must be draft, publish, or schedule")
    if settings["visibility"] not in {"public", "neighbors", "private"}:
        raise ValueError("publish_settings.visibility is unsupported")
    for field in (
        "search_allowed",
        "comments_allowed",
        "sympathy_allowed",
        "share_allowed",
    ):
        if not isinstance(settings[field], bool):
            raise ValueError(f"publish_settings.{field} must be boolean")
    if not isinstance(settings["ccl"], str):
        raise ValueError("publish_settings.ccl must be a string")
    if settings["mode"] == "schedule":
        settings["scheduled_at"] = validate_schedule(settings.get("scheduled_at"))
    elif settings.get("scheduled_at") is not None:
        raise ValueError("scheduled_at is allowed only when mode is schedule")
    editor_options = document.get("editor_options") or {}
    if not isinstance(editor_options, dict) or set(editor_options) - {"spellcheck"}:
        raise ValueError("editor_options supports only spellcheck")
    if not isinstance(editor_options.get("spellcheck", False), bool):
        raise ValueError("editor_options.spellcheck must be boolean")
    result = {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "title": title,
        "background": normalized_background,
        "blocks": normalized_blocks,
        "tags": [tag.strip() for tag in tags],
        "publish_settings": settings,
        "editor_options": {"spellcheck": editor_options.get("spellcheck", False)},
        **({"layout_preset": preset} if preset is not None else {}),
        **({"design_profile": design_profile} if design_profile is not None else {}),
        **({"generated_images": normalize_generated_images(document)} if "generated_images" in document else {}),
    }
    _validate_native_design(result)
    return result


def _attachment_hash(path: str, limit: int) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("attachment must be a bounded regular file")
        total = 0
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            if total > limit:
                raise ValueError("attachment grew beyond its byte limit while hashing")
            digest.update(chunk)
    return digest.hexdigest()


def require_design_media_reviews(document: dict[str, Any]) -> None:
    """Bind human provenance/relevance review to the exact local media bytes."""
    for block in document["blocks"]:
        if block["type"] == "photo" and (
            _attachment_hash(block["path"], MAX_IMAGE_BYTES) != block["design_review"]["sha256"]
        ):
            raise ValueError("native media changed after review; review the exact asset again")


def document_hash(document: object) -> str:
    normalized = validate_document(document)
    paths: dict[str, int] = {}
    if normalized["background"]["type"] == "image":
        paths[normalized["background"]["path"]] = MAX_IMAGE_BYTES
    for block in normalized["blocks"]:
        block_type = block["type"]
        attachments = []
        if block_type in PATH_BLOCK_TYPES:
            attachments = [block["path"]]
            if block_type == "photo" and block.get("replace_path"):
                attachments.append(block["replace_path"])
        elif block_type in {"group-photo", "multi-attach"}:
            attachments = block["paths"]
        limit = _attachment_limit("photo" if block_type == "group-photo" else block_type, None)
        for path in attachments:
            paths[path] = min(paths.get(path, limit), limit)
    attachment_hashes = {path: _attachment_hash(path, limit) for path, limit in paths.items()}
    payload = json.dumps(
        {"document": normalized, "attachment_hashes": attachment_hashes},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _operation(
    index: int,
    feature_id: str,
    payload: dict[str, Any],
    *,
    guided: bool = False,
) -> dict[str, Any]:
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "operation_id": f"{index:04d}:{feature_id}:{digest}",
        "feature_id": feature_id,
        "payload": payload,
        "guided": guided,
        "precondition": "target editor surface is uniquely identified",
        "postcondition": "requested component or setting is visibly applied",
    }


def build_operations(document: object, *, experimental_native_text: bool = False) -> list[dict[str, Any]]:
    """Compile stable, resumable operations without persisting their payloads."""
    value = validate_document(document)
    if experimental_native_text:
        profile = value.get("design_profile")
        if profile is None:
            raise ValueError("experimental native text requires an explicit design_profile")
        if (
            profile["source_divider"] != "none" or value["tags"]
            or value["editor_options"]["spellcheck"]
            or value["publish_settings"]["mode"] != "draft"
            or any(block["type"] not in {"paragraph", "heading"} or block.get("links")
                   or "\n" in block["text"] or "\r" in block["text"] for block in value["blocks"])
        ):
            raise ValueError("experimental native text supports only single-line paragraphs/headings and draft-save")
    if "design_profile" in value:
        if not experimental_native_text and any(block.get("list_marker_style", "neutral") != "neutral" for block in value["blocks"]):
            raise ValueError("native circle list markers are plan-only; live rendering is unavailable")
        if value["design_profile"]["source_divider"] == "single" and not any(
            block["type"] == "divider" for block in value["blocks"]
        ):
            raise ValueError("native source divider insertion is plan-only; live placement is unavailable")
    operations: list[dict[str, Any]] = []

    def add(feature_id: str, payload: dict[str, Any], *, guided: bool = False) -> None:
        operations.append(_operation(len(operations) + 1, feature_id, payload, guided=guided))

    add("title", {"text": value["title"]})
    if value["background"]["type"] != "none":
        add("title-background", value["background"], guided=True)
    for block in value["blocks"]:
        feature = BLOCK_FEATURES[block["type"]]
        payload = block
        if block["type"] in TEXT_BLOCK_TYPES:
            style = (
                _native_style(block, value["design_profile"])
                if "design_profile" in value else effective_style(block, value.get("layout_preset"))
            )
            payload = {**block, "style": style}
            if experimental_native_text:
                feature = "paragraph"
                payload = {
                    **block, "text": rendered_text(block), "native_text": True,
                    "spacing_before": block.get("spacing_before", "normal"),
                    "style": {"alignment": "left", "line_spacing": 1.5, **style},
                }
        add(feature, payload, guided=block["type"] in GUIDED_BLOCK_TYPES)
        if block["type"] in TEXT_BLOCK_TYPES:
            for link in block.get("links", []):
                add(
                    "link",
                    {
                        "block_id": block["id"],
                        "block_text": block["text"],
                        "text": link["text"],
                        "url": link["url"],
                    },
                )
        if block["type"] == "photo":
            if block.get("replace_path"):
                add(
                    "photo-replace",
                    {"block_id": block["id"], "path": block["replace_path"]},
                    guided=True,
                )
            if block.get("properties"):
                add(
                    "photo-properties",
                    {"block_id": block["id"], "properties": block["properties"]},
                    guided=True,
                )
            if block.get("edit_actions"):
                add(
                    "photo-editor",
                    {"block_id": block["id"], "actions": block["edit_actions"]},
                    guided=True,
                )
    if value["tags"]:
        add("tags", {"tags": value["tags"]})
    if value["editor_options"]["spellcheck"]:
        add("spellcheck", {}, guided=True)
    settings = value["publish_settings"]
    # Final publication settings belong to the approval-bound dialog, not compose.
    if settings["mode"] == "draft":
        add("draft-save", {})
    return operations
