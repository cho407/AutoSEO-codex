#!/usr/bin/env python3
"""Deterministic blog layout presets; no browser, content rewrite or publication."""
from __future__ import annotations

import argparse
import copy
import html
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

from file_safety import _resolve_output_path, read_text_limited, write_text_safely

FORMAT_ROLES = {"body", "intro", "summary", "caption", "source", "detail"}
BOOLEAN_STYLES = {"bold", "italic", "underline", "strikethrough", "superscript", "subscript"}


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads((Path(__file__).resolve().parent.parent / "data/blog-format-presets.json").read_text(encoding="utf-8"))


def validate_preset(value) -> str:
    if not isinstance(value, str) or value not in catalog()["presets"]:
        raise ValueError("unsupported layout_preset")
    return value


def validate_role(block) -> None:
    if "format_role" in block:
        role = block["format_role"]
        if block.get("type") != "paragraph" or not isinstance(role, str) or role not in FORMAT_ROLES:
            raise ValueError("format_role requires a supported paragraph role")


def validate_style(value) -> dict:
    """Safe Tistory inline styles, never arbitrary CSS. Preserve explicit values."""
    if not isinstance(value, dict) or set(value) - (BOOLEAN_STYLES | {"font", "size", "color", "alignment", "line_spacing"}):
        raise ValueError("unsupported block style")
    for key, item in value.items():
        if key in BOOLEAN_STYLES and type(item) is not bool:
            raise ValueError(f"style.{key} must be boolean")
        if key in {"size", "line_spacing"}:
            try:
                number = float(item)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"style.{key} must be finite") from exc
            lower, upper = (10, 72) if key == "size" else (1, 3)
            if isinstance(item, bool) or not math.isfinite(number) or not lower <= number <= upper:
                raise ValueError(f"style.{key} is outside the supported range")
        if key == "alignment" and item not in ("left", "center", "right", "justify"):
            raise ValueError("unsupported style.alignment")
        if key == "color" and (not isinstance(item, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", item)):
            raise ValueError("style.color must use #RRGGBB")
        if key == "font" and (not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9가-힣 _,\-]{1,80}", item)):
            raise ValueError("unsupported style.font")
    if value.get("superscript") and value.get("subscript"):
        raise ValueError("superscript and subscript conflict")
    return copy.deepcopy(value)


def block_role(block) -> str:
    if block["type"] == "heading":
        return f"heading{block.get('level', 2)}"
    if block["type"] == "paragraph":
        return block.get("format_role", "body")
    return block["type"]


def effective_style(block, preset=None) -> dict:
    """Resolve only at compile/render time so switching presets is not sticky."""
    explicit = copy.deepcopy(block.get("style", {}))
    if preset is None or validate_preset(preset) == "none":
        return explicit
    role = block_role(block)
    definitions = catalog()
    profile = definitions["presets"][preset]
    style = copy.deepcopy(definitions["styles"].get(role, {}))
    if role.startswith("heading"):
        style["alignment"] = profile["heading_alignment"]
    elif role in {"source", "detail", "ordered-list", "unordered-list", "table", "code"}:
        style["alignment"] = "left"
    elif role == "caption":
        style["alignment"] = "center"
    elif role in definitions["styles"]:
        style["alignment"] = profile["body_alignment"]
    return {**style, **explicit}


def html_attributes(block, preset=None) -> str:
    style = validate_style(effective_style(block, preset))
    css = []
    for field, name, suffix in (("alignment", "text-align", ""), ("size", "font-size", "px"),
                                ("line_spacing", "line-height", ""), ("color", "color", ""),
                                ("font", "font-family", "")):
        if field in style:
            val = f"{float(style[field]):g}" if field in {"size", "line_spacing"} else style[field]
            css.append(f"{name}:{val}{suffix}")
    for field, name, enabled, disabled in (("bold", "font-weight", "700", "400"), ("italic", "font-style", "italic", "normal")):
        if field in style:
            css.append(f"{name}:{enabled if style[field] else disabled}")
    if "underline" in style or "strikethrough" in style:
        decoration = " ".join(name for field, name in (("underline", "underline"), ("strikethrough", "line-through")) if style.get(field))
        css.append(f"text-decoration:{decoration or 'none'}")
    if "superscript" in style or "subscript" in style:
        css.append("vertical-align:" + ("super" if style.get("superscript") else "sub" if style.get("subscript") else "baseline"))
    if preset and preset != "none":
        role = block_role(block)
        spacing = catalog()["html_spacing"]
        key = "heading" if role.startswith("heading") else role if role in spacing else "body"
        css.append(spacing[key])  # trusted shipped rules, never caller-supplied CSS
    return f' style="{html.escape(";".join(css), quote=True)}"' if css else ""


def requires_html(document) -> bool:
    return (document.get("layout_preset") not in (None, "none")
            or any(block.get("style") for block in document["blocks"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("presets")
    apply = commands.add_parser("apply")
    apply.add_argument("platform", choices=("naver", "tistory"))
    apply.add_argument("document", type=Path)
    apply.add_argument("--preset", default=catalog()["default_preset"], choices=tuple(catalog()["presets"]))
    apply.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "presets":
            print(json.dumps({"default_preset": catalog()["default_preset"], "presets": catalog()["presets"]}, ensure_ascii=False))
            return 0
        raw = json.loads(read_text_limited(args.document, extensions={".json"}))
        if not isinstance(raw, dict):
            raise ValueError("document must be an object")
        if args.platform == "naver":
            from naver_document import validate_document
        else:
            from tistory_document import validate_document
        value = validate_document({**raw, "layout_preset": args.preset})
        output = _resolve_output_path(args.output, extensions={".json"})
        if output.exists():
            raise ValueError("output exists; choose a new document path")
        write_text_safely(output, json.dumps(value, ensure_ascii=False, indent=2), extensions={".json"})
        print(json.dumps({"status": "prepared", "layout_preset": args.preset, "output": str(output),
                          "format": value.get("format", "native-editor"), "external_writes": False}, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "stopped", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
