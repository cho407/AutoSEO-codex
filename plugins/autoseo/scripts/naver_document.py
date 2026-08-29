#!/usr/bin/env python3
"""Validate NaverDocument v1 and compile deterministic editor operations."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

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
    identifier = block.get("id")
    if not isinstance(identifier, str) or not DOCUMENT_ID_RE.fullmatch(identifier):
        raise ValueError("each block requires a stable alphanumeric id")
    block_type = block.get("type")
    if block_type not in BLOCK_TYPES:
        raise ValueError(f"unsupported block type: {block_type}")
    normalized = copy.deepcopy(block)
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
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("NaverDocument schema_version must be 1")
    document_id = document.get("document_id")
    if not isinstance(document_id, str) or not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("document_id must be a safe stable identifier")
    title = document.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("title must contain between 1 and 200 characters")
    background = document.get("background", {"type": "none"})
    if not isinstance(background, dict) or background.get("type") not in {
        "none",
        "color",
        "image",
    }:
        raise ValueError("background type must be none, color, or image")
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
    settings = {**DEFAULT_PUBLISH_SETTINGS, **(document.get("publish_settings") or {})}
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
    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "title": title,
        "background": normalized_background,
        "blocks": normalized_blocks,
        "tags": [tag.strip() for tag in tags],
        "publish_settings": settings,
        "editor_options": {"spellcheck": editor_options.get("spellcheck", False)},
    }


def document_hash(document: object) -> str:
    normalized = validate_document(document)
    payload = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
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


def build_operations(document: object) -> list[dict[str, Any]]:
    """Compile stable, resumable operations without persisting their payloads."""
    value = validate_document(document)
    operations: list[dict[str, Any]] = []

    def add(feature_id: str, payload: dict[str, Any], *, guided: bool = False) -> None:
        operations.append(_operation(len(operations) + 1, feature_id, payload, guided=guided))

    add("title", {"text": value["title"]})
    if value["background"]["type"] != "none":
        add("title-background", value["background"], guided=True)
    for block in value["blocks"]:
        feature = BLOCK_FEATURES[block["type"]]
        add(feature, block, guided=block["type"] in GUIDED_BLOCK_TYPES)
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
    for feature_id, key in (
        ("category", "category"),
        ("visibility", "visibility"),
        ("search-allowed", "search_allowed"),
        ("comments-allowed", "comments_allowed"),
        ("sympathy-allowed", "sympathy_allowed"),
        ("ccl", "ccl"),
        ("share-allowed", "share_allowed"),
    ):
        add(feature_id, {"value": settings[key]})
    if settings["mode"] == "draft":
        add("draft-save", {})
    return operations
