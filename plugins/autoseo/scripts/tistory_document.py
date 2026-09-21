#!/usr/bin/env python3
"""Validate and render TistoryDocument v1 as safe Markdown or HTML."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from blog_format import (
    html_attributes,
    requires_html,
    validate_preset,
    validate_role,
    validate_style,
)
from blog_image import normalize_generated_images
from file_safety import read_text_limited, resolve_input_file, write_text_safely

SCHEMA_VERSION = 1
DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FACE_ID_RE = re.compile(r"^face-[1-9][0-9]*$")
MAX_DOCUMENT_CHARS = 500_000
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_SCHEDULE_DAYS = 365
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BLOCK_TYPES = {
    "paragraph",
    "heading",
    "quote",
    "unordered-list",
    "ordered-list",
    "code",
    "table",
    "divider",
    "image",
}
DEFAULT_PRIVACY = {
    "mode": "background-people",
    "keep_face_ids": [],
    "mosaic_face_ids": [],
    "main_face_id": None,
    "regions": [],
    "padding": 0.18,
    "block_size": 14,
    "strip_metadata": True,
}
DEFAULT_PUBLISH_SETTINGS = {
    "mode": "draft",
    "category": None,
    "visibility": "public",
    "comments_allowed": True,
    "scheduled_at": None,
}
ALLOWED_MEDIA_HOST_SUFFIXES = (
    ".kakaocdn.net",
    ".daumcdn.net",
    ".tistory.com",
    ".kakao.com",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_schedule(value: str, *, now: datetime | None = None) -> str:
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


def _face_ids(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not FACE_ID_RE.fullmatch(item) for item in value
    ):
        raise ValueError(f"privacy.{field} must contain face-N identifiers")
    if len(value) != len(set(value)):
        raise ValueError(f"privacy.{field} contains duplicates")
    return list(value)


def _privacy(value: object) -> dict[str, Any]:
    if value is None:
        return copy.deepcopy(DEFAULT_PRIVACY)
    if not isinstance(value, dict):
        raise ValueError("media privacy must be an object")
    unknown = set(value) - set(DEFAULT_PRIVACY)
    if unknown:
        raise ValueError(f"unsupported media privacy fields: {sorted(unknown)}")
    result = copy.deepcopy(DEFAULT_PRIVACY)
    result.update(copy.deepcopy(value))
    if result["mode"] not in {"background-people", "all", "none", "selected"}:
        raise ValueError("unsupported media privacy mode")
    result["keep_face_ids"] = _face_ids(
        result["keep_face_ids"], field="keep_face_ids"
    )
    result["mosaic_face_ids"] = _face_ids(
        result["mosaic_face_ids"], field="mosaic_face_ids"
    )
    conflicts = set(result["keep_face_ids"]) & set(result["mosaic_face_ids"])
    if conflicts:
        raise ValueError("a face cannot be both kept and mosaicked")
    main = result["main_face_id"]
    if main is not None and (not isinstance(main, str) or not FACE_ID_RE.fullmatch(main)):
        raise ValueError("privacy.main_face_id must be a face-N identifier or null")
    if main is not None and main in result["mosaic_face_ids"]:
        raise ValueError("main face cannot also be mosaicked")
    if not isinstance(result["regions"], list) or len(result["regions"]) > 100:
        raise ValueError("privacy.regions must be a list with at most 100 entries")
    regions: list[dict[str, int]] = []
    for region in result["regions"]:
        if not isinstance(region, dict) or set(region) != {"x", "y", "width", "height"}:
            raise ValueError("each privacy region requires x, y, width, and height")
        if any(isinstance(region[key], bool) or not isinstance(region[key], int) for key in region):
            raise ValueError("privacy region coordinates must be integers")
        if region["x"] < 0 or region["y"] < 0 or region["width"] <= 0 or region["height"] <= 0:
            raise ValueError("privacy region coordinates are invalid")
        regions.append(copy.deepcopy(region))
    result["regions"] = regions
    if isinstance(result["padding"], bool) or not isinstance(result["padding"], (int, float)):
        raise ValueError("privacy.padding must be numeric")
    result["padding"] = float(result["padding"])
    if not 0 <= result["padding"] <= 1:
        raise ValueError("privacy.padding must be between 0 and 1")
    if isinstance(result["block_size"], bool) or not isinstance(result["block_size"], int):
        raise ValueError("privacy.block_size must be an integer")
    if not 2 <= result["block_size"] <= 100:
        raise ValueError("privacy.block_size must be between 2 and 100")
    if not isinstance(result["strip_metadata"], bool):
        raise ValueError("privacy.strip_metadata must be boolean")
    return result


def _validate_media(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("media must be a list with at most 100 entries")
    media: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each media entry must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not DOCUMENT_ID_RE.fullmatch(identifier):
            raise ValueError("each media entry requires a stable alphanumeric id")
        if identifier in identifiers:
            raise ValueError(f"duplicate media id: {identifier}")
        identifiers.add(identifier)
        path = resolve_input_file(item.get("path", ""), extensions=IMAGE_EXTENSIONS)
        if path.stat().st_size > MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"media attachment exceeds the {MAX_ATTACHMENT_BYTES}-byte limit"
            )
        alt = item.get("alt")
        if not isinstance(alt, str) or not alt.strip() or len(alt) > 300:
            raise ValueError("each media entry requires concise non-empty alt text")
        caption = item.get("caption")
        if caption is not None and (not isinstance(caption, str) or len(caption) > 500):
            raise ValueError("media caption must be a string with at most 500 characters")
        privacy = _privacy(item.get("privacy"))
        if path.suffix.casefold() == ".gif" and privacy["mode"] != "none":
            raise ValueError("animated GIF privacy processing is unavailable; use mode=none")
        media.append(
            {
                "id": identifier,
                "path": str(path),
                "alt": alt.strip(),
                "caption": caption.strip() if isinstance(caption, str) else None,
                "privacy": privacy,
            }
        )
    return media


def _text(value: object, *, field: str, limit: int = 100_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds the {limit}-character limit")
    return value


def _validate_block(value: object) -> tuple[dict[str, Any], int]:
    if not isinstance(value, dict):
        raise ValueError("each block must be an object")
    identifier = value.get("id")
    if not isinstance(identifier, str) or not DOCUMENT_ID_RE.fullmatch(identifier):
        raise ValueError("each block requires a stable alphanumeric id")
    block_type = value.get("type")
    if block_type not in BLOCK_TYPES:
        raise ValueError(f"unsupported Tistory block type: {block_type}")
    result = {"id": identifier, "type": block_type}
    validate_role(value)
    if "format_role" in value:
        result["format_role"] = value["format_role"]
    if "style" in value:
        if block_type not in {"paragraph", "heading", "quote"}:
            raise ValueError("style is supported on text blocks only")
        result["style"] = validate_style(value["style"])
    characters = 0
    if block_type in {"paragraph", "quote"}:
        result["text"] = _text(value.get("text"), field=f"{block_type}.text")
        characters += len(result["text"])
    elif block_type == "heading":
        result["text"] = _text(value.get("text"), field="heading.text", limit=500)
        level = value.get("level", 2)
        if level not in {2, 3, 4}:
            raise ValueError("heading.level must be 2, 3, or 4")
        result["level"] = level
        characters += len(result["text"])
    elif block_type in {"unordered-list", "ordered-list"}:
        items = value.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 200:
            raise ValueError(f"{block_type}.items must contain 1-200 entries")
        result["items"] = [
            _text(item, field=f"{block_type}.items", limit=5_000) for item in items
        ]
        characters += sum(len(item) for item in result["items"])
    elif block_type == "code":
        result["code"] = _text(value.get("code"), field="code.code")
        language = str(value.get("language") or "").strip()
        if language and not re.fullmatch(r"[A-Za-z0-9_+.#-]{1,32}", language):
            raise ValueError("code.language is invalid")
        result["language"] = language
        characters += len(result["code"])
    elif block_type == "table":
        headers = value.get("headers")
        rows = value.get("rows")
        if not isinstance(headers, list) or not 1 <= len(headers) <= 20:
            raise ValueError("table.headers must contain 1-20 columns")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError("table.rows must contain 1-100 rows")
        normalized_headers = [str(item) for item in headers]
        normalized_rows: list[list[str]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(normalized_headers):
                raise ValueError("each table row must match the header column count")
            normalized_rows.append([str(item) for item in row])
        result["headers"] = normalized_headers
        result["rows"] = normalized_rows
        characters += sum(len(item) for item in normalized_headers)
        characters += sum(len(item) for row in normalized_rows for item in row)
    elif block_type == "image":
        media_id = value.get("media_id")
        if not isinstance(media_id, str) or not DOCUMENT_ID_RE.fullmatch(media_id):
            raise ValueError("image.media_id is required")
        result["media_id"] = media_id
    return result, characters


def _publish_settings(value: object) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("publish_settings must be an object")
    unknown = set(value) - set(DEFAULT_PUBLISH_SETTINGS)
    if unknown:
        raise ValueError(f"unsupported publish settings: {sorted(unknown)}")
    result = copy.deepcopy(DEFAULT_PUBLISH_SETTINGS)
    result.update(copy.deepcopy(value))
    if result["mode"] not in {"draft", "publish", "schedule"}:
        raise ValueError("publish_settings.mode is unsupported")
    category = result["category"]
    if category is not None and (not isinstance(category, str) or not category.strip()):
        raise ValueError("publish_settings.category must be non-empty text or null")
    result["category"] = category.strip() if isinstance(category, str) else None
    if result["visibility"] not in {"public", "private"}:
        raise ValueError("publish_settings.visibility must be public or private")
    if not isinstance(result["comments_allowed"], bool):
        raise ValueError("publish_settings.comments_allowed must be boolean")
    if result["mode"] == "schedule":
        if not isinstance(result["scheduled_at"], str):
            raise ValueError("schedule mode requires scheduled_at")
        result["scheduled_at"] = validate_schedule(result["scheduled_at"])
    elif result["scheduled_at"] is not None:
        raise ValueError("scheduled_at is only valid in schedule mode")
    return result


def validate_document(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("TistoryDocument schema_version must be 1")
    document_id = value.get("document_id")
    if not isinstance(document_id, str) or not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("TistoryDocument requires a stable document_id")
    title = _text(value.get("title"), field="title", limit=200).strip()
    preset = validate_preset(value["layout_preset"]) if "layout_preset" in value else None
    raw_format = value.get("format", "auto")
    if raw_format not in {"auto", "markdown", "html"}:
        raise ValueError("format must be auto, markdown, or html")
    output_format = "markdown" if raw_format == "auto" else raw_format
    media = _validate_media(value.get("media"))
    media_ids = {item["id"] for item in media}
    blocks_raw = value.get("blocks")
    if not isinstance(blocks_raw, list) or not 1 <= len(blocks_raw) <= 1_000:
        raise ValueError("blocks must contain 1-1000 entries")
    blocks: list[dict[str, Any]] = []
    block_ids: set[str] = set()
    total_chars = len(title)
    referenced_media: set[str] = set()
    for raw_block in blocks_raw:
        block, characters = _validate_block(raw_block)
        if block["id"] in block_ids:
            raise ValueError(f"duplicate block id: {block['id']}")
        block_ids.add(block["id"])
        if block["type"] == "image":
            if block["media_id"] not in media_ids:
                raise ValueError(f"image block references unknown media: {block['media_id']}")
            if block["media_id"] in referenced_media:
                raise ValueError(f"media is referenced more than once: {block['media_id']}")
            referenced_media.add(block["media_id"])
        blocks.append(block)
        total_chars += characters
    if total_chars > MAX_DOCUMENT_CHARS:
        raise ValueError(
            f"TistoryDocument exceeds the {MAX_DOCUMENT_CHARS}-character limit"
        )
    unreferenced = media_ids - referenced_media
    if unreferenced:
        raise ValueError(f"unreferenced media entries: {sorted(unreferenced)}")
    styled = requires_html({"layout_preset": preset, "blocks": blocks})
    if styled:
        if raw_format == "markdown":
            raise ValueError("layout presets and block styles require HTML; use format=auto/html or remove styling")
        output_format = "html"
    tags_raw = value.get("tags") or []
    if not isinstance(tags_raw, list) or not len(tags_raw) <= 30:
        raise ValueError("tags must be a list with at most 30 entries")
    tags: list[str] = []
    for tag in tags_raw:
        if not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 50:
            raise ValueError("each tag must contain 1-50 characters")
        normalized = tag.strip()
        if normalized not in tags:
            tags.append(normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "title": title,
        "format": output_format,
        "blocks": blocks,
        "media": media,
        "tags": tags,
        "publish_settings": _publish_settings(value.get("publish_settings")),
        **({"layout_preset": preset} if preset is not None else {}),
        **({"generated_images": normalize_generated_images(value)} if "generated_images" in value else {}),
    }


def document_hash(value: object) -> str:
    document = validate_document(value)
    attachment_hashes = {
        item["id"]: _sha256_file(Path(item["path"])) for item in document["media"]
    }
    material = json.dumps(
        {"document": document, "attachment_hashes": attachment_hashes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_media_url(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or not any(host.endswith(suffix) for suffix in ALLOWED_MEDIA_HOST_SUFFIXES)
    ):
        raise ValueError("uploaded media URL is not an allowlisted Tistory/Kakao CDN URL")
    return value


def _media_source(media: dict[str, Any], media_urls: dict[str, str] | None) -> str:
    if media_urls is not None:
        try:
            return validate_media_url(media_urls[media["id"]])
        except KeyError as exc:
            raise ValueError(f"uploaded URL is missing for media: {media['id']}") from exc
    path = Path(media["path"])
    return quote(path.as_posix(), safe="/._-")


def _markdown_text(value: str) -> str:
    return html.escape(value, quote=False).replace("\r\n", "\n").replace("\r", "\n")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("|", "\\|").replace("\n", "<br>")


def render_document(
    value: object,
    *,
    output_format: str | None = None,
    media_urls: dict[str, str] | None = None,
) -> str:
    document = validate_document(value)
    target = output_format or document["format"]
    if target not in {"markdown", "html"}:
        raise ValueError("output_format must be markdown or html")
    if target == "markdown" and requires_html(document):
        raise ValueError("styled documents require HTML; Markdown cannot preserve the layout")
    media = {item["id"]: item for item in document["media"]}
    rendered: list[str] = []
    for block in document["blocks"]:
        block_type = block["type"]
        if target == "markdown":
            if block_type == "paragraph":
                rendered.append(_markdown_text(block["text"]))
            elif block_type == "heading":
                rendered.append(f"{'#' * block['level']} {_markdown_text(block['text'])}")
            elif block_type == "quote":
                rendered.append(
                    "\n".join(f"> {line}" for line in _markdown_text(block["text"]).splitlines())
                )
            elif block_type in {"unordered-list", "ordered-list"}:
                prefix = "-" if block_type == "unordered-list" else None
                rendered.append(
                    "\n".join(
                        f"{prefix or f'{index}.'} {_markdown_text(item)}"
                        for index, item in enumerate(block["items"], 1)
                    )
                )
            elif block_type == "code":
                code = block["code"].replace("```", "` ` `")
                rendered.append(f"```{block['language']}\n{code}\n```")
            elif block_type == "table":
                header = "| " + " | ".join(_markdown_cell(item) for item in block["headers"]) + " |"
                divider = "| " + " | ".join("---" for _ in block["headers"]) + " |"
                rows = [
                    "| " + " | ".join(_markdown_cell(item) for item in row) + " |"
                    for row in block["rows"]
                ]
                rendered.append("\n".join([header, divider, *rows]))
            elif block_type == "divider":
                rendered.append("---")
            elif block_type == "image":
                item = media[block["media_id"]]
                source = _media_source(item, media_urls)
                value = f"![{_markdown_text(item['alt'])}]({source})"
                if item["caption"]:
                    value += f"\n\n*{_markdown_text(item['caption'])}*"
                rendered.append(value)
        else:
            attrs = html_attributes(block, document.get("layout_preset"))
            def text(content):
                escaped = html.escape(content)
                return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>") if attrs else escaped
            if block_type == "paragraph":
                rendered.append(f"<p{attrs}>{text(block['text'])}</p>")
            elif block_type == "heading":
                rendered.append(
                    f"<h{block['level']}{attrs}>{text(block['text'])}</h{block['level']}>"
                )
            elif block_type == "quote":
                rendered.append(f"<blockquote{attrs}>{text(block['text'])}</blockquote>")
            elif block_type in {"unordered-list", "ordered-list"}:
                tag = "ul" if block_type == "unordered-list" else "ol"
                items = "".join(f"<li>{html.escape(item)}</li>" for item in block["items"])
                rendered.append(f"<{tag}{attrs}>{items}</{tag}>")
            elif block_type == "code":
                language = html.escape(block["language"], quote=True)
                class_name = f' class="language-{language}"' if language else ""
                rendered.append(
                    f"<pre{attrs}><code{class_name}>{html.escape(block['code'])}</code></pre>"
                )
            elif block_type == "table":
                headers = "".join(f"<th>{html.escape(item)}</th>" for item in block["headers"])
                rows = "".join(
                    "<tr>" + "".join(f"<td>{html.escape(item)}</td>" for item in row) + "</tr>"
                    for row in block["rows"]
                )
                table = f"<table{attrs}><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"
                rendered.append(f'<div style="overflow-x:auto">{table}</div>' if attrs else table)
            elif block_type == "divider":
                rendered.append(f"<hr{attrs}>")
            elif block_type == "image":
                item = media[block["media_id"]]
                source = html.escape(_media_source(item, media_urls), quote=True)
                alt = html.escape(item["alt"], quote=True)
                caption_attrs = html_attributes({"type": "paragraph", "format_role": "caption"}, document.get("layout_preset"))
                caption = (
                    f"<figcaption{caption_attrs}>{html.escape(item['caption'])}</figcaption>"
                    if item["caption"]
                    else ""
                )
                rendered.append(
                    f'<figure class="imageblock"{attrs}><img src="{source}" alt="{alt}">{caption}</figure>'
                )
    return "\n\n".join(rendered).strip() + "\n"


def build_operations(
    value: object, media_urls: dict[str, str]
) -> list[dict[str, Any]]:
    document = validate_document(value)
    body = render_document(
        document,
        output_format=document["format"],
        media_urls=media_urls,
    )
    definitions = [
        ("editor-mode", {"format": document["format"]}),
        ("title", {"text": document["title"]}),
        ("body-source", {"format": document["format"], "text": body}),
        ("tags", {"tags": document["tags"]}),
        ("draft-save", {}),
    ]
    operations: list[dict[str, Any]] = []
    for index, (feature_id, payload) in enumerate(definitions, 1):
        material = json.dumps(
            {"feature_id": feature_id, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        operations.append(
            {
                "operation_id": f"{index:03d}-{feature_id}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:12]}",
                "feature_id": feature_id,
                "payload": payload,
            }
        )
    return operations


def _load_document(path: Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    return validate_document(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("document", type=Path)
    render = sub.add_parser("render")
    render.add_argument("document", type=Path)
    render.add_argument("--format", choices=("markdown", "html"))
    render.add_argument("--output", type=Path)
    render.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        document = _load_document(args.document)
        if args.command == "validate":
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "valid": True,
                        "document_id": document["document_id"],
                        "format": document["format"],
                        "block_count": len(document["blocks"]),
                        "media_count": len(document["media"]),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        output_format = args.format or document["format"]
        rendered = render_document(document, output_format=output_format)
        if args.output:
            suffix = ".md" if output_format == "markdown" else ".html"
            path = write_text_safely(
                args.output,
                rendered,
                overwrite=args.overwrite,
                extensions={suffix},
            )
            print(json.dumps({"schema_version": 1, "output": str(path)}, indent=2))
        else:
            print(rendered, end="")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Tistory document stopped safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
