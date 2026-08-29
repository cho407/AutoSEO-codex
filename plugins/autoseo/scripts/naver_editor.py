#!/usr/bin/env python3
"""Guarded Playwright automation for Naver Blog PC SmartEditor ONE."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from file_safety import read_text_limited, write_text_atomically
from naver_document import (
    build_operations,
    document_hash,
    validate_document,
    validate_schedule,
)
from url_safety import make_safe_playwright_route_handler, validate_url

SCHEMA_VERSION = 1
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FEATURE_CATALOG_PATH = PLUGIN_ROOT / "data" / "naver-editor-features.json"
DEFAULT_EDITOR_URL = "https://blog.naver.com/PostWriteForm.naver"
ALLOWED_NAVER_HOSTS = {"blog.naver.com", "m.blog.naver.com", "nid.naver.com"}
AUTOMATIC_HANDLERS = {
    "fill-title",
    "insert-text",
    "insert-component",
    "apply-format",
    "upload-file",
    "set-tags",
    "set-publish-option",
    "save-draft",
    "guarded-publish",
}
COMPONENT_SELECTORS = {
    "divider": ".se-section-horizontalLine",
    "photo": ".se-section-image",
    "group-photo": ".se-section-image",
    "sticker": ".se-section-sticker, .se-section-image",
    "video": ".se-section-video",
    "place": ".se-section-place",
    "multi-attach": ".se-section-file",
    "external-link": ".se-section-oglink",
    "file": ".se-section-file",
    "schedule-component": ".se-section-schedule",
    "table": ".se-section-table",
    "equation": ".se-section-equation",
    "talktalk": ".se-section-talktalk",
}


class EditorError(RuntimeError):
    pass


class EditorUIChanged(EditorError):
    pass


class StaleElementReference(EditorError):
    pass


class AmbiguousElement(EditorUIChanged):
    pass


class GuidedChoiceRequired(EditorError):
    pass


class ApprovalRequired(EditorError):
    pass


class PublishResultUnknown(EditorError):
    pass


class FeatureCatalog:
    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != 1:
            raise ValueError("Naver editor feature catalog schema_version must be 1")
        values = payload.get("features")
        if not isinstance(values, list) or not values:
            raise ValueError("Naver editor feature catalog is empty")
        self.catalog_version = str(payload.get("catalog_version") or "")
        self.features: dict[str, dict[str, Any]] = {}
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("each Naver editor feature requires an id")
            identifier = item["id"]
            if identifier in self.features:
                raise ValueError(f"duplicate Naver editor feature: {identifier}")
            if item.get("status") not in {"automatic", "guided", "unavailable"}:
                raise ValueError(f"invalid feature status: {identifier}")
            if item.get("status") == "automatic" and item.get("handler") not in AUTOMATIC_HANDLERS:
                raise ValueError(f"automatic feature has no handler: {identifier}")
            locator = item.get("locator")
            if not isinstance(locator, dict):
                raise ValueError(f"feature has no locator contract: {identifier}")
            self.features[identifier] = copy.deepcopy(item)

    @classmethod
    def load(cls, path: Path = FEATURE_CATALOG_PATH) -> "FeatureCatalog":
        value = json.loads(read_text_limited(path, extensions={".json"}))
        if not isinstance(value, dict):
            raise ValueError("Naver editor feature catalog must be an object")
        return cls(value)

    def feature(self, identifier: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self.features[identifier])
        except KeyError as exc:
            raise ValueError(f"unknown Naver editor feature: {identifier}") from exc


def _default_data_dir() -> Path:
    configured = os.environ.get("AUTOSEO_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "autoseo").resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return (base / "autoseo").resolve()
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "autoseo"
    ).resolve()


def _validated_dedicated_path(path: Path) -> Path:
    value = path.expanduser().resolve(strict=False)
    if value == Path(value.anchor).resolve() or value == Path.home().resolve():
        raise ValueError("Naver editor data must use a dedicated subdirectory")
    return value


def _dedicated_directory(path: Path) -> Path:
    value = _validated_dedicated_path(path)
    value.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        value.chmod(0o700)
    except OSError:
        pass
    return value


def _profile_path(data_dir: str | os.PathLike[str] | None = None) -> Path:
    base = Path(data_dir) if data_dir is not None else _default_data_dir()
    return base.expanduser().resolve(strict=False) / "naver-editor-profile"


def profile_directory(data_dir: str | os.PathLike[str] | None = None) -> Path:
    return _dedicated_directory(_profile_path(data_dir))


class CheckpointStore:
    """Persist hashes and completed IDs, never the document body or cookies."""

    def __init__(self, data_dir: str | os.PathLike[str] | None = None) -> None:
        base = Path(data_dir) if data_dir is not None else _default_data_dir()
        self.directory = _dedicated_directory(base / "naver-editor-checkpoints")

    def path_for(self, document_id: str) -> Path:
        if not document_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in document_id):
            raise ValueError("unsafe checkpoint document id")
        return self.directory / f"{document_id}.json"

    @staticmethod
    def _new(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "document_id": document["document_id"],
            "source_hash": document_hash(document),
            "completed_operation_ids": [],
            "draft_url": None,
            "publish_state": "not-attempted",
            "published_url": None,
            "diagnostic_files": [],
            "last_error_type": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def load_or_create(self, document: object) -> dict[str, Any]:
        value = validate_document(document)
        path = self.path_for(value["document_id"])
        expected_hash = document_hash(value)
        checkpoint: dict[str, Any] | None = None
        if path.is_file() and not path.is_symlink():
            try:
                loaded = json.loads(read_text_limited(path, extensions={".json"}))
                if isinstance(loaded, dict) and loaded.get("schema_version") == 1:
                    checkpoint = loaded
            except (OSError, ValueError, json.JSONDecodeError):
                checkpoint = None
        if checkpoint is None or checkpoint.get("source_hash") != expected_hash:
            checkpoint = self._new(value)
            self.save(checkpoint)
        return copy.deepcopy(checkpoint)

    def load_existing(self, document: object) -> dict[str, Any]:
        value = validate_document(document)
        path = self.path_for(value["document_id"])
        if not path.is_file() or path.is_symlink():
            raise ValueError("no resumable checkpoint exists for this document")
        checkpoint = json.loads(read_text_limited(path, extensions={".json"}))
        if (
            not isinstance(checkpoint, dict)
            or checkpoint.get("source_hash") != document_hash(value)
        ):
            raise ValueError("checkpoint source hash does not match the document")
        return checkpoint

    def save(self, checkpoint: dict[str, Any]) -> None:
        allowed = {
            "schema_version",
            "document_id",
            "source_hash",
            "completed_operation_ids",
            "draft_url",
            "publish_state",
            "published_url",
            "diagnostic_files",
            "last_error_type",
            "updated_at",
        }
        if set(checkpoint) - allowed:
            raise ValueError("checkpoint contains unsupported or content-bearing fields")
        checkpoint = copy.deepcopy(checkpoint)
        checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
        path = write_text_atomically(
            self.path_for(str(checkpoint["document_id"])),
            json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            extensions={".json"},
        )
        try:
            path.chmod(0o600)
        except OSError:
            pass


class EditorAutomation:
    def __init__(self, store: CheckpointStore) -> None:
        self.store = store

    def apply(self, document: object, driver: Any) -> dict[str, Any]:
        value = validate_document(document)
        checkpoint = self.store.load_or_create(value)
        completed = set(checkpoint.get("completed_operation_ids", []))
        for operation in build_operations(value):
            operation_id = operation["operation_id"]
            if operation_id in completed:
                continue
            try:
                if operation.get("guided"):
                    if not driver.guide(operation):
                        raise GuidedChoiceRequired(
                            f"guided choice is incomplete for {operation['feature_id']}"
                        )
                else:
                    try:
                        driver.execute(operation)
                    except StaleElementReference:
                        driver.execute(operation)
                if not driver.verify(operation):
                    raise EditorUIChanged(
                        f"postcondition failed for {operation['feature_id']}"
                    )
            except Exception as exc:
                diagnostic = driver.capture_diagnostic(type(exc).__name__)
                if diagnostic and diagnostic not in checkpoint["diagnostic_files"]:
                    checkpoint["diagnostic_files"].append(diagnostic)
                checkpoint["last_error_type"] = type(exc).__name__
                self.store.save(checkpoint)
                raise
            completed.add(operation_id)
            checkpoint["completed_operation_ids"] = sorted(completed)
            checkpoint["last_error_type"] = None
            self.store.save(checkpoint)
        return checkpoint


def _publish_settings(
    document: object,
    *,
    action: str,
    scheduled_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = validate_document(document)
    if action not in {"publish", "schedule"}:
        raise ValueError("action must be publish or schedule")
    settings = copy.deepcopy(value["publish_settings"])
    settings["mode"] = action
    if action == "schedule":
        if not scheduled_at:
            raise ValueError("scheduled_at is required for schedule")
        settings["scheduled_at"] = validate_schedule(scheduled_at)
    else:
        settings["scheduled_at"] = None
    return value, settings


def approval_preview(
    document: object,
    *,
    action: str,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    value, settings = _publish_settings(
        document, action=action, scheduled_at=scheduled_at
    )
    token_material = json.dumps(
        {
            "action": action,
            "document_hash": document_hash(value),
            "settings": settings,
            "tags": value["tags"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    approval_token = hashlib.sha256(token_material.encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": 1,
        "approval_required": True,
        "action": action,
        "document_id": value["document_id"],
        "title": value["title"],
        "category": settings["category"],
        "visibility": settings["visibility"],
        "search_allowed": settings["search_allowed"],
        "comments_allowed": settings["comments_allowed"],
        "sympathy_allowed": settings["sympathy_allowed"],
        "ccl": settings["ccl"],
        "share_allowed": settings["share_allowed"],
        "tags": value["tags"],
        "scheduled_at": settings["scheduled_at"],
        "approval_token": approval_token,
    }


def publish_or_schedule(
    document: object,
    checkpoint: dict[str, Any],
    driver: Any,
    *,
    action: str,
    approval_token: str,
    scheduled_at: str | None = None,
    store: CheckpointStore | None = None,
) -> dict[str, Any]:
    value, settings = _publish_settings(
        document, action=action, scheduled_at=scheduled_at
    )
    preview = approval_preview(value, action=action, scheduled_at=scheduled_at)
    if approval_token != preview["approval_token"]:
        raise ApprovalRequired("the exact per-document approval token is required")
    if os.environ.get("AUTOSEO_TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError("Naver publish actions are disabled in automated tests")
    if checkpoint.get("source_hash") != document_hash(value):
        raise ValueError("checkpoint source hash does not match the document")
    if checkpoint.get("publish_state") in {
        "attempting",
        "unknown",
        "published",
        "scheduled",
    }:
        raise PublishResultUnknown(
            "a prior publish result exists or is unclear; reconcile it manually before retrying"
        )
    required = {item["operation_id"] for item in build_operations(value)}
    if not required.issubset(set(checkpoint.get("completed_operation_ids", []))):
        raise ValueError("the draft has incomplete editor operations; resume it first")

    checkpoint["publish_state"] = "attempting"
    if store:
        store.save(checkpoint)
    try:
        driver.apply_publish_settings(settings)
        driver.click_publish(action)
        result = driver.verify_publish(action)
    except Exception as exc:
        checkpoint["publish_state"] = "unknown"
        diagnostic = driver.capture_diagnostic(type(exc).__name__)
        if diagnostic and diagnostic not in checkpoint["diagnostic_files"]:
            checkpoint["diagnostic_files"].append(diagnostic)
        if store:
            store.save(checkpoint)
        raise PublishResultUnknown(
            "publish result is unclear; automatic retry is disabled"
        ) from exc
    if not isinstance(result, dict) or not isinstance(result.get("url"), str):
        checkpoint["publish_state"] = "unknown"
        if store:
            store.save(checkpoint)
        raise PublishResultUnknown(
            "publish result is unclear; automatic retry is disabled"
        )
    result_host = (urlsplit(result["url"]).hostname or "").casefold()
    if not validate_url(result["url"]) or result_host not in {
        "blog.naver.com",
        "m.blog.naver.com",
    }:
        checkpoint["publish_state"] = "unknown"
        if store:
            store.save(checkpoint)
        raise PublishResultUnknown("published URL could not be verified as a Naver Blog URL")
    checkpoint["publish_state"] = "scheduled" if action == "schedule" else "published"
    checkpoint["published_url"] = result["url"]
    if store:
        store.save(checkpoint)
    return checkpoint


class LocatorResolver:
    """Resolve role/name, Korean label, shortcut, then versioned DOM fallback."""

    def __init__(self, page: Any, catalog: FeatureCatalog) -> None:
        self.page = page
        self.catalog = catalog

    @staticmethod
    def _count(locator: Any) -> int:
        try:
            return int(locator.count())
        except Exception as exc:
            if "stale" in str(exc).casefold() or "detached" in str(exc).casefold():
                raise StaleElementReference("editor element became stale") from exc
            raise

    def _unique(self, locator: Any, description: str) -> Any | None:
        count = self._count(locator)
        if count > 1:
            raise AmbiguousElement(f"multiple editor elements matched {description}")
        return locator if count == 1 else None

    def locate(self, feature_id: str, *, allow_shortcut: bool = False) -> tuple[str, Any]:
        feature = self.catalog.feature(feature_id)
        locator = feature["locator"]
        role = locator.get("role")
        name = locator.get("name")
        if role and name:
            candidate = self._unique(
                self.page.get_by_role(role, name=name, exact=True),
                f"role={role}, name={name}",
            )
            if candidate is not None:
                return "role-name", candidate
        for label in locator.get("labels") or []:
            candidate = self._unique(
                self.page.get_by_text(label, exact=True), f"Korean label={label}"
            )
            if candidate is not None:
                return "korean-label", candidate
        shortcut = locator.get("shortcut")
        if allow_shortcut and shortcut:
            return "shortcut", shortcut
        fallback = locator.get("dom_fallback")
        if fallback:
            candidate = self._unique(
                self.page.locator(fallback), f"DOM fallback={fallback}"
            )
            if candidate is not None:
                return "dom-fallback", candidate
        raise EditorUIChanged(f"no unique editor control found for {feature_id}")

    def click(self, feature_id: str) -> str:
        strategy, target = self.locate(feature_id, allow_shortcut=True)
        try:
            if strategy == "shortcut":
                self.page.keyboard.press(target)
            else:
                target.click()
        except Exception as exc:
            if "stale" in str(exc).casefold() or "detached" in str(exc).casefold():
                raise StaleElementReference("editor element became stale") from exc
            raise EditorUIChanged(f"editor control failed for {feature_id}") from exc
        return strategy

    def probe(self, feature_id: str) -> dict[str, Any]:
        try:
            strategy, _ = self.locate(feature_id, allow_shortcut=False)
            return {"available": True, "strategy": strategy}
        except AmbiguousElement:
            return {"available": False, "strategy": None, "reason": "ambiguous"}
        except EditorUIChanged:
            feature = self.catalog.feature(feature_id)
            if feature["locator"].get("shortcut"):
                return {"available": True, "strategy": "shortcut-unverified"}
            return {"available": False, "strategy": None, "reason": "not-found"}


class PlaywrightNaverDriver:
    """Real SmartEditor adapter; every action has a checked postcondition."""

    def __init__(
        self,
        page: Any,
        *,
        catalog: FeatureCatalog,
        data_dir: Path,
    ) -> None:
        self.page = page
        self.catalog = catalog
        self.resolver = LocatorResolver(page, catalog)
        self.data_dir = data_dir
        self._postconditions: dict[str, bool] = {}

    def _body_locator(self) -> Any:
        _, locator = self.resolver.locate("paragraph")
        return locator

    def _component_count(self, feature_id: str) -> int | None:
        selector = COMPONENT_SELECTORS.get(feature_id)
        return int(self.page.locator(selector).count()) if selector else None

    def _apply_style(self, style: dict[str, Any]) -> list[str]:
        toggled: list[str] = []
        boolean_features = {
            "bold": "bold",
            "italic": "italic",
            "underline": "underline",
            "strikethrough": "strikethrough",
            "superscript": "superscript",
            "subscript": "subscript",
        }
        for field, feature_id in boolean_features.items():
            if style.get(field):
                self.resolver.click(feature_id)
                toggled.append(feature_id)
        menu_features = {
            "font": "font-family",
            "size": "font-size",
            "color": "text-color",
            "alignment": "alignment",
            "line_spacing": "line-spacing",
        }
        for field, feature_id in menu_features.items():
            value = style.get(field)
            if value is None:
                continue
            self.resolver.click(feature_id)
            option = self.page.get_by_text(str(value), exact=True)
            if option.count() != 1:
                raise AmbiguousElement(f"format option is not unique: {field}={value}")
            option.click()
        return toggled

    def _insert_text_block(self, operation: dict[str, Any]) -> None:
        payload = operation["payload"]
        feature_id = operation["feature_id"]
        if feature_id in {"heading", "quote"}:
            self.resolver.click(feature_id)
        body = self._body_locator()
        body.click()
        toggled = self._apply_style(payload.get("style", {}))
        self.page.keyboard.insert_text(payload["text"])
        self.page.keyboard.press("Enter")
        for feature_id in reversed(toggled):
            self.resolver.click(feature_id)

    def _upload(self, operation: dict[str, Any]) -> None:
        self.resolver.click(operation["feature_id"])
        selectors = {
            "photo": "input[type='file'][accept*='image']",
            "group-photo": "input[type='file'][accept*='image']",
            "video": "input[type='file'][accept*='video']",
            "file": "input[type='file']:not([accept*='image']):not([accept*='video'])",
            "multi-attach": "input[type='file']",
        }
        inputs = self.page.locator(selectors[operation["feature_id"]])
        if inputs.count() == 0:
            inputs = self.page.locator("input[type='file']")
        if inputs.count() != 1:
            raise AmbiguousElement("file input is missing or ambiguous")
        payload = operation["payload"]
        files = payload.get("paths") or [payload.get("path")]
        inputs.set_input_files(files)

    def _apply_link(self, operation: dict[str, Any]) -> None:
        payload = operation["payload"]
        block = self.page.get_by_text(payload["block_text"], exact=True)
        if block.count() != 1:
            raise AmbiguousElement("link source block is missing or ambiguous")
        selected = block.evaluate(
            """
            (element, needle) => {
              const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
              const nodes = [];
              let combined = '';
              while (walker.nextNode()) {
                nodes.push({node: walker.currentNode, start: combined.length});
                combined += walker.currentNode.nodeValue || '';
              }
              const first = combined.indexOf(needle);
              if (first < 0 || combined.indexOf(needle, first + 1) >= 0) return false;
              const last = first + needle.length;
              const start = nodes.find(item => first >= item.start && first <= item.start + (item.node.nodeValue || '').length);
              const end = [...nodes].reverse().find(item => last >= item.start && last <= item.start + (item.node.nodeValue || '').length);
              if (!start || !end) return false;
              const range = document.createRange();
              range.setStart(start.node, first - start.start);
              range.setEnd(end.node, last - end.start);
              const selection = window.getSelection();
              selection.removeAllRanges();
              selection.addRange(range);
              return selection.toString() === needle;
            }
            """,
            payload["text"],
        )
        if not selected:
            raise EditorUIChanged("link source text could not be selected uniquely")
        self.resolver.click("link")
        self._named_textbox(("URL", "링크 주소", "주소")).fill(payload["url"])
        self._confirm_dialog()
        links = self.page.get_by_role("link", name=payload["text"], exact=True)
        self._postconditions[operation["operation_id"]] = links.count() == 1

    def _named_textbox(self, names: tuple[str, ...]) -> Any:
        for name in names:
            candidate = self.page.get_by_role("textbox", name=name, exact=True)
            count = candidate.count()
            if count > 1:
                raise AmbiguousElement(f"multiple textboxes matched {name}")
            if count == 1:
                return candidate
        raise EditorUIChanged(f"required textbox was not found: {', '.join(names)}")

    def _confirm_dialog(self) -> None:
        confirm = self.page.get_by_role("button", name="확인", exact=True)
        if confirm.count() != 1:
            raise AmbiguousElement("component confirmation is missing or ambiguous")
        confirm.click()

    def _configure_component(self, feature_id: str, payload: dict[str, Any]) -> None:
        if feature_id == "external-link":
            self._named_textbox(("URL", "링크 주소", "주소")).fill(payload["url"])
            self._confirm_dialog()
        elif feature_id == "equation":
            self._named_textbox(("수식", "수식 입력")).fill(payload["expression"])
            self._confirm_dialog()
        elif feature_id == "schedule-component":
            self._named_textbox(("시작", "시작 일시")).fill(payload["start"])
            if payload.get("end"):
                self._named_textbox(("종료", "종료 일시")).fill(payload["end"])
            if payload.get("text"):
                self._named_textbox(("일정 제목", "제목")).fill(payload["text"])
            self._confirm_dialog()
        elif feature_id == "table":
            rows = payload["rows"]
            columns = max((len(row) for row in rows), default=1)
            row_control = self.page.get_by_role("spinbutton", name="행", exact=True)
            column_control = self.page.get_by_role("spinbutton", name="열", exact=True)
            if row_control.count() != 1 or column_control.count() != 1:
                raise EditorUIChanged("table row and column controls were not found")
            row_control.fill(str(len(rows)))
            column_control.fill(str(columns))
            self._confirm_dialog()
            table = self.page.locator(COMPONENT_SELECTORS["table"]).last
            cells = table.locator("[contenteditable='true']")
            if cells.count() < sum(len(row) for row in rows):
                raise EditorUIChanged("created table cells do not match the document")
            index = 0
            for row in rows:
                for value in row:
                    cells.nth(index).fill(str(value))
                    index += 1

    def _set_option(self, operation: dict[str, Any]) -> None:
        feature_id = operation["feature_id"]
        value = operation["payload"].get("value")
        _, control = self.resolver.locate(feature_id)
        if isinstance(value, bool):
            checked = bool(control.is_checked())
            if checked != value:
                control.click()
            return
        control.click()
        if value is None:
            return
        option = self.page.get_by_text(str(value), exact=True)
        if option.count() != 1:
            raise AmbiguousElement(f"publish option is not unique: {feature_id}")
        option.click()

    def execute(self, operation: dict[str, Any]) -> None:
        feature_id = operation["feature_id"]
        feature = self.catalog.feature(feature_id)
        handler = feature["handler"]
        before = self._component_count(feature_id)
        if handler == "fill-title":
            _, locator = self.resolver.locate(feature_id)
            locator.fill(operation["payload"]["text"])
        elif handler == "insert-text":
            self._insert_text_block(operation)
        elif handler == "insert-component":
            if feature_id == "link":
                self._apply_link(operation)
            elif feature_id in {"heading", "quote"}:
                self._insert_text_block(operation)
            else:
                self.resolver.click(feature_id)
                if feature_id in {
                    "external-link",
                    "equation",
                    "schedule-component",
                    "table",
                }:
                    self._configure_component(feature_id, operation["payload"])
        elif handler == "upload-file":
            self._upload(operation)
        elif handler == "set-tags":
            _, locator = self.resolver.locate(feature_id)
            for tag in operation["payload"]["tags"]:
                locator.fill(tag)
                self.page.keyboard.press("Enter")
        elif handler == "set-publish-option":
            self._set_option(operation)
        elif handler == "save-draft":
            self.resolver.click(feature_id)
        elif handler == "apply-format":
            self.resolver.click(feature_id)
        elif handler == "guarded-publish":
            raise ApprovalRequired("publish controls require the guarded publish path")
        else:
            raise EditorUIChanged(f"unsupported editor handler: {handler}")
        after = self._component_count(feature_id)
        self._postconditions[operation["operation_id"]] = (
            before is None or after is None or after > before
        )

    def verify(self, operation: dict[str, Any]) -> bool:
        feature_id = operation["feature_id"]
        payload = operation["payload"]
        if feature_id == "title":
            try:
                _, locator = self.resolver.locate("title")
                return locator.input_value() == payload["text"]
            except Exception:
                return False
        if feature_id in {"paragraph", "heading", "quote"}:
            try:
                return self.page.get_by_text(payload["text"], exact=True).count() >= 1
            except Exception:
                return False
        if feature_id in {"photo", "group-photo", "video", "file", "multi-attach"}:
            paths = payload.get("paths") or [payload["path"]]
            try:
                return all(
                    self.page.get_by_text(Path(path).name, exact=False).count() >= 1
                    for path in paths
                )
            except Exception:
                return False
        if feature_id == "link":
            try:
                return (
                    self.page.get_by_role(
                        "link", name=payload["text"], exact=True
                    ).count()
                    == 1
                )
            except Exception:
                return False
        if feature_id == "draft-save":
            try:
                return self.page.get_by_text("임시저장 완료", exact=False).count() >= 1
            except Exception:
                return False
        return self._postconditions.get(operation["operation_id"], False)

    def guide(self, operation: dict[str, Any]) -> bool:
        feature_id = operation["feature_id"]
        before = self._component_count(feature_id)
        self.resolver.click(feature_id)
        if not sys.stdin.isatty():
            raise GuidedChoiceRequired(
                f"{feature_id} requires a visible user choice in SmartEditor ONE"
            )
        print(
            json.dumps(
                {
                    "guided_feature": feature_id,
                    "instruction": "Complete the visible choice, then enter done.",
                },
                ensure_ascii=False,
            )
        )
        confirmed = input().strip().casefold() == "done"
        after = self._component_count(feature_id)
        verified = confirmed and (
            before is None or after is None or after > before
        )
        self._postconditions[operation["operation_id"]] = verified
        return verified

    def capture_diagnostic(self, reason: str) -> str:
        directory = _dedicated_directory(self.data_dir / "naver-editor-diagnostics")
        name = f"{int(time.time())}-{reason}.png"
        path = directory / name
        try:
            self.page.screenshot(path=str(path), full_page=False)
            path.chmod(0o600)
            return str(path)
        except Exception:
            return ""

    def apply_publish_settings(self, settings: dict[str, Any]) -> None:
        operations = [
            ("category", settings.get("category")),
            ("visibility", settings["visibility"]),
            ("search-allowed", settings["search_allowed"]),
            ("comments-allowed", settings["comments_allowed"]),
            ("sympathy-allowed", settings["sympathy_allowed"]),
            ("ccl", settings["ccl"]),
            ("share-allowed", settings["share_allowed"]),
        ]
        for index, (feature_id, value) in enumerate(operations, 1):
            self._set_option(
                {
                    "operation_id": f"publish-setting-{index}",
                    "feature_id": feature_id,
                    "payload": {"value": value},
                }
            )
        if settings["mode"] == "schedule":
            self.resolver.click("schedule-publish")
            field = self.page.get_by_role("textbox", name="예약 시간", exact=True)
            if field.count() != 1:
                raise AmbiguousElement("schedule time input is missing or ambiguous")
            field.fill(settings["scheduled_at"])

    def click_publish(self, action: str) -> None:
        self.resolver.click("schedule-publish" if action == "schedule" else "publish")

    def verify_publish(self, action: str) -> dict[str, Any] | None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        url = str(self.page.url)
        host = (urlsplit(url).hostname or "").casefold()
        if host in {"blog.naver.com", "m.blog.naver.com"} and "PostWriteForm" not in url:
            return {"url": url, "action": action}
        return None


def _validate_editor_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "blog.naver.com"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("editor URL must be an HTTPS blog.naver.com URL")
    return value


def _verified_draft_url(value: str) -> str | None:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    query = parsed.query.casefold()
    if (
        parsed.scheme == "https"
        and host in {"blog.naver.com", "m.blog.naver.com"}
        and any(marker in query for marker in ("logno=", "draftno=", "documentid="))
    ):
        return value
    return None


class NaverBrowserSession:
    """Headed persistent browser; login, 2FA, and CAPTCHA stay user-controlled."""

    def __init__(
        self,
        *,
        data_dir: Path,
        editor_url: str = DEFAULT_EDITOR_URL,
    ) -> None:
        self.data_dir = _dedicated_directory(data_dir)
        self.editor_url = _validate_editor_url(editor_url)
        self.playwright = None
        self.context = None
        self.page = None

    def __enter__(self) -> "NaverBrowserSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is unavailable; install the AutoSEO standard profile"
            ) from exc
        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            str(profile_directory(self.data_dir)),
            headless=False,
            accept_downloads=False,
        )
        self.context.route("**/*", make_safe_playwright_route_handler())
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto(self.editor_url, wait_until="domcontentloaded")
        self._assert_allowed_page()
        return self

    def __exit__(self, *_: object) -> None:
        if self.context is not None:
            self.context.close()
        if self.playwright is not None:
            self.playwright.stop()

    def _assert_allowed_page(self) -> None:
        host = (urlsplit(str(self.page.url)).hostname or "").casefold()
        if host not in ALLOWED_NAVER_HOSTS:
            raise EditorUIChanged("browser left the allowlisted Naver login/editor hosts")

    def wait_for_editor(self, timeout_seconds: int = 600) -> Any:
        deadline = time.monotonic() + timeout_seconds
        announced = False
        while time.monotonic() < deadline:
            self._assert_allowed_page()
            host = (urlsplit(str(self.page.url)).hostname or "").casefold()
            if host in {"blog.naver.com", "m.blog.naver.com"}:
                editable = self.page.locator("[contenteditable='true']")
                if editable.count() > 0:
                    return self.page
            if not announced:
                print(
                    "Complete Naver login, two-factor authentication, and any CAPTCHA "
                    "in the visible browser. AutoSEO will not enter or export them.",
                    file=sys.stderr,
                )
                announced = True
            self.page.wait_for_timeout(500)
        raise EditorUIChanged("SmartEditor ONE was not ready before the login timeout")

    def keep_open_until_closed(self) -> None:
        print("Draft is ready. Close the browser window to finish.", file=sys.stderr)
        try:
            while self.context.pages:
                live_pages = [page for page in self.context.pages if not page.is_closed()]
                if not live_pages:
                    return
                try:
                    live_pages[0].wait_for_timeout(500)
                except Exception:
                    if live_pages[0].is_closed():
                        return
                    raise
        except KeyboardInterrupt:
            pass


def learn_compatibility_map(
    page: Any,
    catalog: FeatureCatalog,
    *,
    editor_url: str,
) -> dict[str, Any]:
    resolver = LocatorResolver(page, catalog)
    return {
        "schema_version": 1,
        "catalog_version": catalog.catalog_version,
        "editor_origin": f"{urlsplit(editor_url).scheme}://{urlsplit(editor_url).hostname}",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "features": {
            identifier: resolver.probe(identifier)
            for identifier in catalog.features
        },
        "note": "Local UI compatibility map only; no page text, cookies, or account data.",
    }


def _compatibility_path(data_dir: Path) -> Path:
    return _dedicated_directory(data_dir) / "naver-editor-compatibility.json"


def _load_document(path: Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if not isinstance(value, dict):
        raise ValueError("NaverDocument input must be a JSON object")
    return validate_document(value)


def _draft_preview(document: dict[str, Any]) -> dict[str, Any]:
    attachment_count = int(document["background"]["type"] == "image")
    for block in document["blocks"]:
        attachment_count += int("path" in block)
        attachment_count += len(block.get("paths", []))
        attachment_count += int("replace_path" in block)
    token_material = json.dumps(
        {
            "action": "compose-and-save-draft",
            "document_hash": document_hash(document),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": 1,
        "approval_required": True,
        "action": "compose-and-save-draft",
        "document_id": document["document_id"],
        "title": document["title"],
        "block_count": len(document["blocks"]),
        "attachment_count": attachment_count,
        "tags": document["tags"],
        "publish_settings": document["publish_settings"],
        "approval_token": hashlib.sha256(token_material.encode("utf-8")).hexdigest()[:24],
    }


def _data_path(raw: str | None, *, create: bool = True) -> Path:
    value = _validated_dedicated_path(
        Path(raw).expanduser() if raw else _default_data_dir()
    )
    return _dedicated_directory(value) if create else value


def _compose(
    document: dict[str, Any],
    *,
    data_dir: Path,
    editor_url: str,
    close_after: bool,
) -> dict[str, Any]:
    if document["publish_settings"]["mode"] != "draft":
        raise ValueError("compose and resume require publish_settings.mode=draft")
    store = CheckpointStore(data_dir)
    catalog = FeatureCatalog.load()
    with NaverBrowserSession(data_dir=data_dir, editor_url=editor_url) as browser:
        page = browser.wait_for_editor()
        driver = PlaywrightNaverDriver(
            page, catalog=catalog, data_dir=data_dir
        )
        checkpoint = EditorAutomation(store).apply(document, driver)
        checkpoint["draft_url"] = _verified_draft_url(str(page.url))
        store.save(checkpoint)
        if not close_after:
            browser.keep_open_until_closed()
        return checkpoint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="override AUTOSEO_DATA_DIR for this command")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    learn = sub.add_parser("learn")
    learn.add_argument("--editor-url", default=DEFAULT_EDITOR_URL)
    learn.add_argument("--close-after", action="store_true")
    compose = sub.add_parser("compose")
    compose.add_argument("document", type=Path)
    compose.add_argument("--editor-url", default=DEFAULT_EDITOR_URL)
    compose.add_argument("--approval-token")
    compose.add_argument("--close-after", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("document", type=Path)
    resume.add_argument("--draft-url")
    resume.add_argument("--approval-token")
    resume.add_argument("--close-after", action="store_true")
    publish = sub.add_parser("publish")
    publish.add_argument("document", type=Path)
    publish.add_argument("--approval-token")
    publish.add_argument("--close-after", action="store_true")
    schedule = sub.add_parser("schedule")
    schedule.add_argument("document", type=Path)
    schedule.add_argument("--at", required=True)
    schedule.add_argument("--approval-token")
    schedule.add_argument("--close-after", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            data_dir = _data_path(args.data_dir, create=False)
            catalog = FeatureCatalog.load()
            try:
                import playwright  # noqa: F401

                playwright_ready = True
            except ImportError:
                playwright_ready = False
            profile = _profile_path(data_dir)
            profile_exists = profile.is_dir() and not profile.is_symlink()
            profile_permissions = (
                oct(stat.S_IMODE(profile.stat().st_mode)) if profile_exists else None
            )
            profile_secure = not profile_exists or profile_permissions == "0o700"
            result = {
                "schema_version": 1,
                "playwright_ready": playwright_ready,
                "catalog_version": catalog.catalog_version,
                "feature_count": len(catalog.features),
                "profile_directory": str(profile),
                "profile_exists": profile_exists,
                "profile_permissions": profile_permissions,
                "ready": playwright_ready and profile_secure,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 3

        data_dir = _data_path(args.data_dir)

        if args.command == "learn":
            catalog = FeatureCatalog.load()
            with NaverBrowserSession(
                data_dir=data_dir, editor_url=args.editor_url
            ) as browser:
                page = browser.wait_for_editor()
                result = learn_compatibility_map(
                    page, catalog, editor_url=str(page.url)
                )
                path = write_text_atomically(
                    _compatibility_path(data_dir),
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    extensions={".json"},
                )
                path.chmod(0o600)
                if not args.close_after:
                    browser.keep_open_until_closed()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        document = _load_document(args.document)
        if args.command in {"compose", "resume"}:
            preview = _draft_preview(document)
            if args.approval_token != preview["approval_token"]:
                print(json.dumps(preview, ensure_ascii=False, indent=2))
                return 4
            editor_url = args.editor_url if args.command == "compose" else None
            if args.command == "resume":
                existing = CheckpointStore(data_dir).load_existing(document)
                candidate = args.draft_url or existing.get("draft_url")
                editor_url = _verified_draft_url(str(candidate or ""))
                if editor_url is None:
                    raise ValueError(
                        "resume requires a verified Naver draft URL with a draft identifier"
                    )
            result = _compose(
                document,
                data_dir=data_dir,
                editor_url=str(editor_url),
                close_after=args.close_after,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        action = "schedule" if args.command == "schedule" else "publish"
        scheduled_at = args.at if action == "schedule" else None
        preview = approval_preview(
            document, action=action, scheduled_at=scheduled_at
        )
        if args.approval_token != preview["approval_token"]:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 4
        store = CheckpointStore(data_dir)
        checkpoint = store.load_existing(document)
        draft_url = _verified_draft_url(str(checkpoint.get("draft_url") or ""))
        if draft_url is None:
            raise ValueError("checkpoint has no verified draft URL; compose or resume first")
        with NaverBrowserSession(data_dir=data_dir, editor_url=draft_url) as browser:
            page = browser.wait_for_editor()
            driver = PlaywrightNaverDriver(
                page, catalog=FeatureCatalog.load(), data_dir=data_dir
            )
            result = publish_or_schedule(
                document,
                checkpoint,
                driver,
                action=action,
                approval_token=args.approval_token,
                scheduled_at=scheduled_at,
                store=store,
            )
            if not args.close_after:
                browser.keep_open_until_closed()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (EditorError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Naver editor stopped safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
