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

import editor_compatibility
from blog_image import require_image_reviews
from editor_protocol import capabilities, compact_result, document_plan, operation_decision
from editor_safety import (
    CHECKPOINT_DEFAULTS,
    FreshSaveReceipt,
    attachment_stamps,
    bind_surface,
    browser_session_id,
    digest,
    draft_identity,
    local_schedule,
    locked_document,
    locked_profile_enter,
    locked_profile_exit,
    locked_publication,
    mark_operation_pending,
    prepare_publication,
    publication_result,
    record_operation,
    validate_checkpoint,
)
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
            fast_path = locator.get("fast_path")
            if fast_path is not None:
                if (
                    not isinstance(fast_path, dict)
                    or fast_path.get("strategy") not in {
                        "role-name",
                        "korean-label",
                        "dom-fallback",
                    }
                    or not isinstance(fast_path.get("frame_index"), int)
                    or fast_path["frame_index"] < 0
                    or fast_path.get("scope") not in {"document", "toolbar", "dialog"}
                ):
                    raise ValueError(f"invalid fast locator contract: {identifier}")
                if fast_path["strategy"] == "dom-fallback" and not locator.get("dom_fallback"):
                    raise ValueError(f"fast DOM locator has no catalog selector: {identifier}")
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
            **CHECKPOINT_DEFAULTS,
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
        if path.exists() or path.is_symlink():
            return copy.deepcopy(self.load_existing(value))
        checkpoint = self._new(value)
        self.save(checkpoint)
        return checkpoint

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
        return validate_checkpoint(checkpoint, value["document_id"], document_hash(value))

    def save(self, checkpoint: dict[str, Any]) -> None:
        allowed = {
            *CHECKPOINT_DEFAULTS,
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

    @locked_document
    def apply(self, document: object, driver: Any) -> dict[str, Any]:
        value = validate_document(document)
        require_image_reviews(value)
        checkpoint = self.store.load_or_create(value)
        source_stamps = attachment_stamps(value)
        operations = build_operations(value)
        if hasattr(driver, "prepare_operations"):
            driver.prepare_operations(operations)
        bind_surface(checkpoint, driver)
        completed = set(checkpoint.get("completed_operation_ids", []))
        for operation in operations:
            if attachment_stamps(value) != source_stamps:
                raise ValueError("source attachment changed since approval; request a new document preview")
            operation_id = operation["operation_id"]
            try:
                decision = operation_decision(checkpoint, operation, driver)
                if decision == "skip":
                    continue
                if decision not in {"execute", "guide", "record"}:
                    raise EditorUIChanged("content changed or operation uncertain; manual reconciliation required; reconcile before retrying")
                mark_operation_pending(checkpoint, operation, driver)
                if operation["feature_id"] == "draft-save" and document_hash(value) != checkpoint["source_hash"]:
                    raise ValueError("source attachment hash changed before saving")
                if operation["feature_id"] == "draft-save" and hasattr(driver, "verify_document"):
                    if not driver.verify_document(value):
                        raise EditorUIChanged("final document differs from the approved content; reconcile before saving")
                self.store.save(checkpoint)
                if decision == "record":
                    pass
                elif decision == "guide":
                    if not driver.guide(operation):
                        raise GuidedChoiceRequired(
                            f"guided choice is incomplete for {operation['feature_id']}"
                        )
                else:
                    try:
                        driver.execute(operation)
                    except StaleElementReference:
                        if not driver.verify(operation):
                            # Only replacement operations are safe to repeat.
                            if operation["feature_id"] != "title":
                                raise
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
            record_operation(checkpoint, operation, driver)
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
        settings["scheduled_at"] = local_schedule(validate_schedule(scheduled_at))
    else:
        settings["scheduled_at"] = None
    return value, settings


def approval_preview(
    document: object,
    *,
    action: str,
    scheduled_at: str | None = None,
    target_url: str | None = None,
    saved_surface_hash: str | None = None,
) -> dict[str, Any]:
    value, settings = _publish_settings(
        document, action=action, scheduled_at=scheduled_at
    )
    token_material = json.dumps(
        {
            "action": action,
            "document_hash": document_hash(value),
            "target_url": target_url,
            "saved_surface_hash": saved_surface_hash,
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
        "scheduled_at_local": local_schedule(settings["scheduled_at"]),
        "platform_timezone": "Asia/Seoul",
        "target_url": target_url,
        "saved_surface_hash": saved_surface_hash,
        "approval_token": approval_token,
    }


@locked_publication
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
    preview = approval_preview(value, action=action, scheduled_at=scheduled_at,
                               target_url=checkpoint.get("draft_url"),
                               saved_surface_hash=checkpoint.get("saved_surface_hash"))
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

    if store is None:
        raise ValueError("durable checkpoint storage is required for publication")
    prepare_publication(driver, value, checkpoint, settings)
    # Settings are verified before the irreversible attempt starts.
    driver.apply_publish_settings(settings)
    checkpoint["publish_state"] = "attempting"
    if store:
        store.save(checkpoint)
    try:
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
    """Resolve role/name, locale-ranked labels, shortcut, then DOM fallback."""

    def __init__(self, page: Any, catalog: FeatureCatalog) -> None:
        self.page = page
        self.catalog = catalog
        self.compatibility = None
        self.last_resolution = {}
        self.ambiguous_error = AmbiguousElement
        self.ui_error = EditorUIChanged

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
        return editor_compatibility.locate(self, feature_id, allow_shortcut=allow_shortcut)


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
            return {"available": True, **self.last_resolution, "strategy": strategy}
        except AmbiguousElement:
            return {"available": False, "strategy": None, "reason": "ambiguous"}
        except EditorUIChanged:
            feature = self.catalog.feature(feature_id)
            if feature["locator"].get("shortcut"):
                return {"available": True, "strategy": "shortcut-unverified"}
            return {"available": False, "strategy": None, "reason": "not-found"}


class PlaywrightNaverDriver:
    """Real SmartEditor adapter; every action has a checked postcondition."""

    surface_version = 2

    def __init__(
        self,
        page: Any,
        *,
        catalog: FeatureCatalog,
        data_dir: Path,
    ) -> None:
        self.page = page
        self.session_id = browser_session_id(page)
        self.catalog = catalog
        self.resolver = LocatorResolver(page, catalog)
        self.data_dir = data_dir
        self.resolver.compatibility = editor_compatibility.load_map(
            data_dir / "naver-editor-compatibility.json", page, catalog
        )
        self._save_receipt = FreshSaveReceipt(page)
        self._postconditions: dict[str, bool] = {}
        self._guided_open: set[str] = set()

    def _body_locator(self) -> Any:
        if editor_compatibility.editor_body(self.page, "naver") is None:
            raise EditorUIChanged("visible Naver document body is unavailable")
        _, locator = self.resolver.locate("paragraph")
        if not locator.evaluate("node => !!node.closest('.se-main-container')"):
            raise EditorUIChanged("paragraph control is outside the identified document")
        return locator

    def prepare_operations(self, operations: list[dict]) -> None:
        counts = {}
        self._expected_components = {}
        for operation in operations:
            feature = operation["feature_id"]
            selector = COMPONENT_SELECTORS.get(feature)
            if selector:
                counts[selector] = counts.get(selector, 0) + len(operation["payload"].get("paths") or [None])
                self._expected_components[operation["operation_id"]] = (selector, counts[selector])

    def _component_count(self, feature_id: str) -> int | None:
        selector = COMPONENT_SELECTORS.get(feature_id)
        return int(self.page.locator(selector).count()) if selector else None

    def _click_text_aliases(self, aliases: list[str] | tuple[str, ...], description: str) -> str:
        """Click one exact visible option, ranked for the current UI locale."""
        for label in editor_compatibility.ordered_aliases(self.page, aliases):
            option = self.page.get_by_text(label, exact=True)
            count = option.count()
            if count > 1:
                raise AmbiguousElement(f"{description} is not unique: {label}")
            if count == 1:
                option.click()
                return label
        raise EditorUIChanged(
            f"{description} was not found for ui_language={editor_compatibility.ui_language(self.page)}"
        )

    def _apply_style(self, style: dict[str, Any], *, reset_booleans: bool = True) -> dict:
        restore = {}
        boolean_features = {
            "bold": "bold",
            "italic": "italic",
            "underline": "underline",
            "strikethrough": "strikethrough",
            "superscript": "superscript",
            "subscript": "subscript",
        }
        # One fresh read, not a cached selection state. Menu/selection changes
        # invalidate formatting immediately, so never reuse values across blocks.
        states = editor_compatibility.format_toggle_states(self.page, self.catalog, boolean_features.values())
        for field, feature_id in boolean_features.items():
            if field not in style and not reset_booleans:
                continue
            try:
                if states is not None:
                    current = states[feature_id]
                else:
                    _, control = self.resolver.locate(feature_id)
                    current = control.get_attribute("aria-pressed")
            except EditorUIChanged:
                if not style.get(field):
                    continue
                raise
            if current not in {"true", "false"}:
                raise EditorUIChanged(f"format toggle state is unmeasured: {field}")
            enabled = current == "true"
            restore[field] = enabled
            if bool(style.get(field, False)) != enabled:
                _, control = self.resolver.locate(feature_id)
                if control.get_attribute("aria-pressed") != current:
                    raise EditorUIChanged(f"format selection changed: {field}")
                control.click()
                if control.get_attribute("aria-pressed") != str(bool(style.get(field, False))).lower():
                    raise EditorUIChanged(f"format toggle did not change: {field}")
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
            _, control = self.resolver.locate(feature_id)
            previous = control.get_attribute("data-value") or control.get_attribute("aria-valuetext")
            if previous is None:
                raise EditorUIChanged(f"current {field} is unknown; use guided formatting")
            restore[field] = previous
            if str(value) == previous:
                continue
            self.resolver.click(feature_id)
            aliases = ({
                "left": ["왼쪽", "Left", "Align left"],
                "center": ["가운데", "Center", "Align center"],
                "right": ["오른쪽", "Right", "Align right"],
                "justify": ["양쪽", "Justify", "Align justify"],
            }.get(str(value), [str(value)]) if field == "alignment" else [str(value)])
            self._click_text_aliases(aliases, f"format option {field}={value}")
        return restore

    def _insert_text_block(self, operation: dict[str, Any]) -> None:
        payload = operation["payload"]
        feature_id = operation["feature_id"]
        if feature_id in {"heading", "quote"}:
            self.resolver.click(feature_id)
        body = self._body_locator()
        body.click()
        # Cmd+End scrolls without reliably moving the caret on macOS. Position
        # the selection at the last paragraph, without changing editor HTML.
        body.evaluate("""node => {
            node.focus();
            const lines = [...node.querySelectorAll('p,h1,h2,h3,h4,blockquote')]
                .filter(n => !n.querySelector('p,h1,h2,h3,h4,blockquote'));
            const end = lines.at(-1) || node;
            const range = document.createRange(); range.selectNodeContents(end); range.collapse(false);
            const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }""")
        self.page.keyboard.insert_text(payload["text"])
        block = body.get_by_text(payload["text"], exact=True)
        if block.count() != 1:
            raise AmbiguousElement("inserted text block is not uniquely identifiable")
        block.evaluate("""node => {
            const range = document.createRange(); range.selectNodeContents(node);
            const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }""")
        restore = self._apply_style(payload.get("style", {}))
        body.evaluate("() => window.getSelection().collapseToEnd()")
        self.page.keyboard.press("Enter")
        self._apply_style(restore, reset_booleans=False)

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
        self._named_textbox(("URL", "Link URL", "링크 주소", "주소")).fill(payload["url"])
        self._confirm_dialog()
        links = self.page.get_by_role("link", name=payload["text"], exact=True)
        self._postconditions[operation["operation_id"]] = links.count() == 1

    def _named_textbox(self, names: tuple[str, ...]) -> Any:
        scope = editor_compatibility.dialog_scope(self.page)
        for name in editor_compatibility.ordered_aliases(self.page, names):
            candidate = scope.get_by_role("textbox", name=name, exact=True)
            count = candidate.count()
            if count > 1:
                raise AmbiguousElement(f"multiple textboxes matched {name}")
            if count == 1:
                return candidate
        raise EditorUIChanged(f"required textbox was not found: {', '.join(names)}")

    def _confirm_dialog(self) -> None:
        scope = editor_compatibility.dialog_scope(self.page)
        for name in editor_compatibility.ordered_aliases(self.page, ("확인", "Confirm", "OK")):
            confirm = scope.get_by_role("button", name=name, exact=True)
            count = confirm.count()
            if count > 1:
                raise AmbiguousElement("component confirmation is ambiguous")
            if count == 1:
                confirm.click()
                return
        raise EditorUIChanged("component confirmation was not found")

    def _configure_component(self, feature_id: str, payload: dict[str, Any]) -> None:
        if feature_id == "external-link":
            self._named_textbox(("URL", "Link URL", "링크 주소", "주소")).fill(payload["url"])
            self._confirm_dialog()
        elif feature_id == "equation":
            self._named_textbox(("수식", "수식 입력", "Equation", "Equation input")).fill(payload["expression"])
            self._confirm_dialog()
        elif feature_id == "schedule-component":
            self._named_textbox(("시작", "시작 일시", "Start", "Start date and time")).fill(payload["start"])
            if payload.get("end"):
                self._named_textbox(("종료", "종료 일시", "End", "End date and time")).fill(payload["end"])
            if payload.get("text"):
                self._named_textbox(("일정 제목", "제목", "Event title", "Title")).fill(payload["text"])
            self._confirm_dialog()
        elif feature_id == "table":
            rows = payload["rows"]
            columns = max((len(row) for row in rows), default=1)
            scope = editor_compatibility.dialog_scope(self.page)
            row_control = None
            column_control = None
            for name in editor_compatibility.ordered_aliases(self.page, ("행", "Rows", "Number of rows")):
                candidate = scope.get_by_role("spinbutton", name=name, exact=True)
                if candidate.count() > 1:
                    raise AmbiguousElement("table row control is ambiguous")
                if candidate.count() == 1:
                    row_control = candidate
                    break
            for name in editor_compatibility.ordered_aliases(self.page, ("열", "Columns", "Number of columns")):
                candidate = scope.get_by_role("spinbutton", name=name, exact=True)
                if candidate.count() > 1:
                    raise AmbiguousElement("table column control is ambiguous")
                if candidate.count() == 1:
                    column_control = candidate
                    break
            if row_control is None or column_control is None:
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
            if bool(control.is_checked()) != value:
                raise EditorUIChanged(f"publish option did not match: {feature_id}")
            return
        control.click()
        if value is None:
            return
        aliases = [str(value)]
        if feature_id == "visibility":
            aliases = {
                "public": ["전체공개", "Public", "Public post"],
                "private": ["비공개", "Private", "Private post"],
                "neighbors": ["이웃공개", "Neighbors", "Visible to neighbors"],
                "mutual-neighbors": ["서로이웃공개", "Mutual neighbors"],
            }.get(str(value), aliases)
        elif feature_id == "ccl" and value == "none":
            aliases = ["사용 안 함", "None", "Disabled"]
        self._click_text_aliases(aliases, f"publish option {feature_id}")
        selected = control.get_attribute("data-value") or control.get_attribute("aria-valuetext")
        if selected not in {str(value), *aliases}:
            raise EditorUIChanged(f"publish option state is not verifiable: {feature_id}")

    def execute(self, operation: dict[str, Any]) -> None:
        feature_id = operation["feature_id"]
        feature = self.catalog.feature(feature_id)
        handler = feature["handler"]
        before = self._component_count(feature_id)
        if handler == "fill-title":
            _, locator = self.resolver.locate(feature_id)
            editor_compatibility.fill_unicode_exact(
                self.page, locator, operation["payload"]["text"]
            )
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
            self._save_receipt.begin()
            self.resolver.click(feature_id)
            if not self._save_receipt.confirm():
                raise EditorUIChanged("new draft save acknowledgement was not observed")
        elif handler == "apply-format":
            self.resolver.click(feature_id)
        elif handler == "guarded-publish":
            raise ApprovalRequired("publish controls require the guarded publish path")
        else:
            raise EditorUIChanged(f"unsupported editor handler: {handler}")
        after = self._component_count(feature_id)
        if before is not None and after is not None:
            self._postconditions[operation["operation_id"]] = after > before

    def verify(self, operation: dict[str, Any]) -> bool:
        feature_id = operation["feature_id"]
        payload = operation["payload"]
        if feature_id == "title":
            try:
                _, locator = self.resolver.locate("title")
                tag = locator.evaluate("node => node.tagName.toLowerCase()")
                actual = locator.input_value() if tag in {"input", "textarea"} else locator.inner_text()
                return actual == payload["text"]
            except Exception:
                return False
        if feature_id in {"paragraph", "heading", "quote", "special-character"}:
            try:
                matches = [frame.get_by_text(payload["text"], exact=True) for frame in self.page.frames]
                matches = [item for item in matches if item.count()]
                if len(matches) != 1 or matches[0].count() != 1:
                    return False
                return matches[0].evaluate("""(node, expected) => {
                    const s = getComputedStyle(node), p = getComputedStyle(node.closest('p') || node);
                    const bold = s.fontWeight === 'bold' || parseInt(s.fontWeight) >= 600;
                    if (bold !== !!expected.bold || (s.fontStyle === 'italic') !== !!expected.italic) return false;
                    if (s.textDecorationLine.includes('underline') !== !!expected.underline) return false;
                    if (s.textDecorationLine.includes('line-through') !== !!expected.strikethrough) return false;
                    const align = p.textAlign === 'start' && p.direction === 'ltr' ? 'left' : p.textAlign;
                    if (expected.alignment && align !== expected.alignment) return false;
                    if (expected.size && parseFloat(s.fontSize) !== Number(expected.size)) return false;
                    if (expected.font && !s.fontFamily.includes(expected.font)) return false;
                    if (expected.color) {
                        const color = document.createElement('span'); color.style.color = expected.color;
                        document.body.append(color); const actual = getComputedStyle(color).color; color.remove();
                        if (s.color !== actual) return false;
                    }
                    if (expected.line_spacing && Math.abs(parseFloat(p.lineHeight) / parseFloat(p.fontSize) - Number(expected.line_spacing)) > .05) return false;
                    if ((s.verticalAlign === 'super') !== !!expected.superscript || (s.verticalAlign === 'sub') !== !!expected.subscript) return false;
                    return true;
                }""", payload.get("style", {}))
            except Exception:
                return False
        if feature_id in {"photo", "group-photo", "video", "file", "multi-attach"}:
            try:
                expected = self._expected_components.get(operation["operation_id"])
                if not expected:
                    return False
                components = self.page.locator(expected[0])
                return components.count() >= expected[1] and components.evaluate_all("""nodes => nodes.every(n =>
                    [...n.querySelectorAll('img, video, a')].some(media =>
                        media.tagName === 'IMG' ? media.complete && media.naturalWidth > 0 : !!(media.src || media.href)))""")
            except Exception:
                return False
        if feature_id == "link":
            try:
                links = self.page.get_by_role("link", name=payload["text"], exact=True)
                return links.count() == 1 and links.get_attribute("href") == payload["url"]
            except Exception:
                return False
        if feature_id == "draft-save":
            return self._save_receipt.acknowledged
        if feature_id == "tags":
            return all(self.page.get_by_text(tag, exact=True).count() == 1 for tag in payload["tags"])
        if feature_id in COMPONENT_SELECTORS:
            expected = getattr(self, "_expected_components", {}).get(operation["operation_id"])
            return bool(expected and self.page.locator(expected[0]).count() >= expected[1])
        return self._postconditions.get(operation["operation_id"], False)

    def guide(self, operation: dict[str, Any]) -> bool:
        feature_id = operation["feature_id"]
        before = self._component_count(feature_id)
        if operation["operation_id"] not in self._guided_open:
            if self.page.get_by_role("dialog").count() == 0:
                self.resolver.click(feature_id)
            self._guided_open.add(operation["operation_id"])
        if not sys.stdin.isatty():
            raise GuidedChoiceRequired(
                f"{feature_id} requires a visible user choice in SmartEditor ONE"
            )
        print(
            json.dumps(
                {
                    "guided_feature": feature_id,
                    "operation_id": operation["operation_id"],
                    "instruction": "Choose the intended visible candidate or review the component; then enter done. Leave other blocks unchanged.",
                },
                ensure_ascii=False,
            )
        )
        confirmed = input().strip().casefold() == "done"
        after = self._component_count(feature_id)
        verified = confirmed and (
            before is not None and after is not None and after > before
        )
        self._postconditions[operation["operation_id"]] = verified
        if verified:
            self._guided_open.discard(operation["operation_id"])
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

    def snapshot_hash(self) -> str:
        _, title = self.resolver.locate("title")
        try:
            title_value = title.input_value()
        except Exception:
            title_value = title.inner_text()
        body = editor_compatibility.editor_body(self.page, "naver")
        if body is None:
            raise EditorUIChanged("document body is missing or ambiguous for checkpoint verification")
        tags = self.page.locator("#tags, .tag_list, .list_tag")
        return digest({"version": self.surface_version, "title": title_value,
                       "body": editor_compatibility.rich_body_snapshot(body[1]),
                       "tags": tags.all_text_contents()})

    def has_existing_content(self) -> bool:
        _, title = self.resolver.locate("title")
        try:
            title_value = title.input_value()
        except Exception:
            title_value = title.inner_text()
        if title_value.strip():
            return True
        for frame in self.page.frames:
            root = frame.locator(".se-main-container")
            if root.count() and (root.inner_text().strip() or root.locator("img, video, table, iframe").count()):
                return True
        return False

    def verify_document(self, document: dict) -> bool:
        expected = [block["text"].strip() for block in document["blocks"] if block.get("text")]
        observed = []
        for frame in self.page.frames:
            observed.extend(frame.locator(".se-main-container").evaluate_all("""roots => roots.flatMap(root =>
                [...root.querySelectorAll('p,h1,h2,h3,h4,blockquote')].filter(n => !n.querySelector('p,h1,h2,h3,h4,blockquote'))
                .map(n => n.textContent.trim()).filter(Boolean))"""))
        # Advanced components need their own postconditions; do not accept extra prose.
        return expected == observed

    def apply_publish_settings(self, settings: dict[str, Any]) -> None:
        dialogs = self.page.get_by_role("dialog")
        if dialogs.count() == 0:
            # This opens configuration only. The final submit has a different contract.
            self.resolver.click("publish-dialog")
        if self.page.get_by_role("dialog").count() != 1:
            raise AmbiguousElement("publish settings dialog is missing or ambiguous")
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
            if feature_id == "category" and value is None:
                continue
            self._set_option(
                {
                    "operation_id": f"publish-setting-{index}",
                    "feature_id": feature_id,
                    "payload": {"value": value},
                }
            )
        if settings["mode"] == "schedule":
            self.resolver.click("schedule-option")
            field = self._named_textbox(("예약 시간", "Schedule time", "Scheduled time"))
            local = datetime.fromisoformat(local_schedule(settings["scheduled_at"]))
            formatted = local.strftime("%Y-%m-%dT%H:%M")
            field.fill(formatted)
            if field.input_value() != formatted:
                raise EditorUIChanged("schedule time did not match the approved local time")

    def click_publish(self, action: str) -> None:
        if os.environ.get("AUTOSEO_TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ:
            raise RuntimeError("publish controls are disabled in automated tests")
        self.resolver.click("schedule-publish" if action == "schedule" else "publish")

    def verify_publish(self, action: str) -> dict[str, Any] | None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
            return publication_result(self, action)
        except Exception:
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


def _validate_cdp_endpoint(value: str | None) -> str | None:
    """Allow attachment only to an explicitly local Chrome debugging endpoint."""
    if value is None:
        return None
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "http"
        or host not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("CDP endpoint must be a credential-free loopback HTTP URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("CDP endpoint has an invalid port") from exc
    if port is None or not 1 <= port <= 65535:
        raise ValueError("CDP endpoint must include a valid port")
    if parsed.path not in {"", "/"}:
        raise ValueError("CDP endpoint must not include a path")
    return value.rstrip("/")


def _verified_draft_url(value: str) -> str | None:
    identity = draft_identity(value)
    if identity and identity[0].startswith("naver:") and identity[1]:
        return value
    return None


class NaverBrowserSession:
    """Headed browser session; login, 2FA, and CAPTCHA stay user-controlled.

    A loopback CDP endpoint attaches to an already open, dedicated Chrome
    profile.  AutoSEO neither navigates another tab nor owns/closes that browser.
    Without CDP, the existing dedicated persistent Playwright profile is used.
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        editor_url: str = DEFAULT_EDITOR_URL,
        cdp_endpoint: str | None = None,
        browser_channel: str | None = None,
    ) -> None:
        self.data_dir = _dedicated_directory(data_dir)
        self.editor_url = _validate_editor_url(editor_url)
        self.cdp_endpoint = _validate_cdp_endpoint(cdp_endpoint)
        if browser_channel not in {None, "chrome"}:
            raise ValueError("Naver browser channel must be chrome when specified")
        if self.cdp_endpoint and browser_channel:
            raise ValueError("browser channel is not used when attaching over CDP")
        self.browser_channel = browser_channel
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.attached = False

    @staticmethod
    def _editor_page_candidates(browser: Any, editor_url: str) -> list[Any]:
        # A supplied blog/draft URL must never fall back to another open draft.
        # Only the generic writer entry point permits selecting a sole editor.
        generic_target = editor_url.rstrip("/") == DEFAULT_EDITOR_URL
        pages = []
        for context in browser.contexts:
            for page in context.pages:
                if page.is_closed():
                    continue
                page_url = str(page.url)
                try:
                    _validate_editor_url(page_url)
                except ValueError:
                    continue
                candidate = urlsplit(page_url)
                path = candidate.path.casefold().rstrip("/")
                if (
                    page_url == editor_url
                    or generic_target and (
                        path.endswith("/postwrite")
                        or path.endswith("/postwriteform.naver")
                    )
                ):
                    pages.append(page)
        exact = [page for page in pages if str(page.url) == editor_url]
        return exact or pages

    @locked_profile_enter
    def __enter__(self) -> "NaverBrowserSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is unavailable; install the AutoSEO standard profile"
            ) from exc
        self.playwright = sync_playwright().start()
        try:
            if self.cdp_endpoint:
                self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_endpoint)
                candidates = self._editor_page_candidates(self.browser, self.editor_url)
                if len(candidates) != 1:
                    raise EditorUIChanged(
                        "CDP attachment requires one open Naver editor tab matching the requested URL"
                    )
                self.page = candidates[0]
                self.context = self.page.context
                self.attached = True
            else:
                launch_options: dict[str, Any] = {
                    "headless": False,
                    "accept_downloads": False,
                }
                if self.browser_channel:
                    launch_options["channel"] = self.browser_channel
                self.context = self.playwright.chromium.launch_persistent_context(
                    str(profile_directory(self.data_dir)),
                    **launch_options,
                )
                self.context.route("**/*", make_safe_playwright_route_handler())
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                self.page.goto(self.editor_url, wait_until="domcontentloaded")
            self._assert_allowed_page()
            return self
        except BaseException:
            try:
                if self.context is not None and not self.attached:
                    self.context.close()
            finally:
                self.playwright.stop()
                self.playwright = None
            raise

    @locked_profile_exit
    def __exit__(self, *_: object) -> None:
        try:
            if self.context is not None and not self.attached:
                self.context.close()
        finally:
            if self.playwright is not None:
                self.playwright.stop()

    def _assert_allowed_page(self) -> None:
        host = (urlsplit(str(self.page.url)).hostname or "").casefold()
        if host not in ALLOWED_NAVER_HOSTS:
            raise EditorUIChanged("browser left the allowlisted Naver login/editor hosts")

    def wait_for_editor(self, timeout_seconds: int = 600) -> Any:
        deadline = time.monotonic() + timeout_seconds
        announced = False
        resolver = LocatorResolver(self.page, FeatureCatalog.load())
        while time.monotonic() < deadline:
            self._assert_allowed_page()
            host = (urlsplit(str(self.page.url)).hostname or "").casefold()
            if host in {"blog.naver.com", "m.blog.naver.com"}:
                if editor_compatibility.editor_ready(self.page, "naver", resolver):
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
        if self.attached:
            print(
                "The externally owned Chrome editor remains open; AutoSEO disconnected without closing it.",
                file=sys.stderr,
            )
            return
        print("The editor remains open for review. Close the browser window to finish.", file=sys.stderr)
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
    return editor_compatibility.build_map(page, catalog, LocatorResolver(page, catalog), editor_url)


def revise_title(
    page: Any,
    catalog: FeatureCatalog,
    *,
    data_dir: Path,
    expected_current_title: str,
    new_title: str,
) -> dict[str, Any]:
    """Replace only the title in an already-open draft and acknowledge one save.

    The expected current title binds the command to the visible draft.  A body
    fingerprint is held in memory before and after the edit so a selector drift
    cannot silently replace article content.  Neither title nor body is written
    to the compatibility map or checkpoint storage.
    """
    expected = str(expected_current_title)
    replacement = str(new_title)
    if not expected.strip() or len(expected) > 200:
        raise ValueError("expected current title must contain between 1 and 200 characters")
    if not replacement.strip() or len(replacement) > 200:
        raise ValueError("new title must contain between 1 and 200 characters")

    driver = PlaywrightNaverDriver(page, catalog=catalog, data_dir=data_dir)
    _, title = driver.resolver.locate("title")
    current = editor_compatibility._read_locator_text(title)
    if current != expected:
        raise EditorUIChanged("visible title does not match the expected current title")
    body = editor_compatibility.editor_body(page, "naver")
    if body is None:
        raise EditorUIChanged("visible Naver document body is unavailable")
    before_body = digest(editor_compatibility.rich_body_snapshot(body[1]))
    title_strategy = copy.deepcopy(driver.resolver.last_resolution)

    if current == replacement:
        return {
            "schema_version": 1,
            "action": "revise-title",
            "changed": False,
            "save_state": "not-needed",
            "draft_url": str(page.url),
            "title_hash": digest(replacement),
            "title_locator": title_strategy,
        }

    editor_compatibility.fill_unicode_exact(page, title, replacement)
    if editor_compatibility._read_locator_text(title) != replacement:
        raise EditorUIChanged("new title was not preserved exactly")
    after_body = digest(editor_compatibility.rich_body_snapshot(body[1]))
    if after_body != before_body:
        try:
            editor_compatibility.fill_unicode_exact(page, title, current)
        finally:
            raise EditorUIChanged("title edit changed the article body; title was restored")

    receipt = FreshSaveReceipt(page)
    receipt.begin()
    driver.resolver.click("draft-save")
    save_strategy = copy.deepcopy(driver.resolver.last_resolution)
    if not receipt.confirm():
        raise EditorUIChanged("new draft save acknowledgement was not observed")
    return {
        "schema_version": 1,
        "action": "revise-title",
        "changed": True,
        "save_state": "acknowledged",
        "draft_url": str(page.url),
        "title_hash": digest(replacement),
        "body_hash": before_body,
        "title_locator": title_strategy,
        "save_locator": save_strategy,
    }


def _compatibility_path(data_dir: Path) -> Path:
    return _dedicated_directory(data_dir) / "naver-editor-compatibility.json"


def _load_document(path: Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if not isinstance(value, dict):
        raise ValueError("NaverDocument input must be a JSON object")
    return validate_document(value)


def _draft_preview(document: dict[str, Any], *, target_url: str | None = None) -> dict[str, Any]:
    document = validate_document(document)
    attachment_count = int(document["background"]["type"] == "image")
    for block in document["blocks"]:
        attachment_count += int("path" in block)
        attachment_count += len(block.get("paths", []))
        attachment_count += int("replace_path" in block)
    token_material = json.dumps(
        {
            "action": "compose-and-save-draft",
            "document_hash": document_hash(document),
            "target_url": target_url,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": 1,
        "approval_required": True,
        "action": "compose-and-save-draft",
        "target_url": target_url,
        "document_id": document["document_id"],
        "title": document["title"],
        "block_count": len(document["blocks"]),
        "attachment_count": attachment_count,
        "tags": document["tags"],
        "publish_settings": document["publish_settings"],
        "editor_options": document["editor_options"],
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
    approval_token: str,
    data_dir: Path,
    editor_url: str,
    close_after: bool,
    cdp_endpoint: str | None = None,
    browser_channel: str | None = None,
) -> dict[str, Any]:
    if document["publish_settings"]["mode"] != "draft":
        raise ValueError("compose and resume require publish_settings.mode=draft")
    require_image_reviews(document)
    store = CheckpointStore(data_dir)
    catalog = FeatureCatalog.load()
    with NaverBrowserSession(
        data_dir=data_dir,
        editor_url=editor_url,
        cdp_endpoint=cdp_endpoint,
        browser_channel=browser_channel,
    ) as browser:
        page = browser.wait_for_editor()
        if _draft_preview(document, target_url=editor_url)["approval_token"] != approval_token:
            raise ApprovalRequired("source changed since approval; request a new document preview")
        driver = PlaywrightNaverDriver(
            page, catalog=catalog, data_dir=data_dir
        )
        try:
            started = time.perf_counter()
            checkpoint = EditorAutomation(store).apply(document, driver)
            elapsed_ms = (time.perf_counter() - started) * 1000
        except Exception:
            if not close_after:
                browser.keep_open_until_closed()
            raise
        checkpoint["draft_url"] = _verified_draft_url(str(page.url))
        store.save(checkpoint)
        result = compact_result(checkpoint, platform="naver", elapsed_ms=elapsed_ms)
        print(json.dumps({"event": "draft-saved", **result}, ensure_ascii=False, separators=(",", ":")),
              file=sys.stderr, flush=True)
        if not close_after:
            browser.keep_open_until_closed()
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="override AUTOSEO_DATA_DIR for this command")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("capabilities")
    plan = sub.add_parser("plan")
    plan.add_argument("document", type=Path)
    def add_browser_options(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--cdp-endpoint",
            default=os.environ.get("AUTOSEO_NAVER_CDP_ENDPOINT"),
            help="attach to one already-open Naver editor tab in dedicated Chrome",
        )
        command.add_argument(
            "--browser-channel",
            choices=["chrome"],
            default=os.environ.get("AUTOSEO_NAVER_BROWSER_CHANNEL"),
            help="launch the regular Google Chrome binary with AutoSEO's dedicated profile",
        )

    learn = sub.add_parser("learn")
    learn.add_argument("--editor-url", default=DEFAULT_EDITOR_URL)
    learn.add_argument("--close-after", action="store_true")
    add_browser_options(learn)
    compose = sub.add_parser("compose")
    compose.add_argument("document", type=Path)
    compose.add_argument("--editor-url", default=DEFAULT_EDITOR_URL)
    compose.add_argument("--approval-token")
    compose.add_argument("--close-after", action="store_true")
    add_browser_options(compose)
    resume = sub.add_parser("resume")
    resume.add_argument("document", type=Path)
    resume.add_argument("--draft-url")
    resume.add_argument("--approval-token")
    resume.add_argument("--close-after", action="store_true")
    add_browser_options(resume)
    revise = sub.add_parser("revise-title")
    revise.add_argument("--expected-current-title", required=True)
    revise.add_argument("--title", required=True)
    revise.add_argument("--editor-url", default=DEFAULT_EDITOR_URL)
    revise.add_argument("--close-after", action="store_true")
    add_browser_options(revise)
    publish = sub.add_parser("publish")
    publish.add_argument("document", type=Path)
    publish.add_argument("--approval-token")
    publish.add_argument("--close-after", action="store_true")
    add_browser_options(publish)
    schedule = sub.add_parser("schedule")
    schedule.add_argument("document", type=Path)
    schedule.add_argument("--at", required=True)
    schedule.add_argument("--approval-token")
    schedule.add_argument("--close-after", action="store_true")
    add_browser_options(schedule)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "capabilities":
            print(json.dumps(capabilities(FeatureCatalog.load()), ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.command == "plan":
            print(json.dumps(document_plan(_load_document(args.document), platform="naver"), ensure_ascii=False, separators=(",", ":")))
            return 0
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
                data_dir=data_dir,
                editor_url=args.editor_url,
                cdp_endpoint=args.cdp_endpoint,
                browser_channel=args.browser_channel,
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

        if args.command == "revise-title":
            catalog = FeatureCatalog.load()
            with NaverBrowserSession(
                data_dir=data_dir,
                editor_url=args.editor_url,
                cdp_endpoint=args.cdp_endpoint,
                browser_channel=args.browser_channel,
            ) as browser:
                page = browser.wait_for_editor()
                result = revise_title(
                    page,
                    catalog,
                    data_dir=data_dir,
                    expected_current_title=args.expected_current_title,
                    new_title=args.title,
                )
                if not args.close_after:
                    browser.keep_open_until_closed()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        document = _load_document(args.document)
        if args.command in {"compose", "resume"}:
            editor_url = args.editor_url if args.command == "compose" else None
            if args.command == "resume":
                existing = CheckpointStore(data_dir).load_existing(document)
                candidate = args.draft_url or existing.get("draft_url")
                editor_url = _verified_draft_url(str(candidate or ""))
                if editor_url is None:
                    raise ValueError(
                        "resume requires a verified Naver draft URL with a draft identifier"
                    )
            preview = _draft_preview(document, target_url=str(editor_url))
            # An explicit compose/resume command authorizes its own draft save.
            # Keep the document-bound token as an internal integrity check; a
            # supplied stale token still fails before opening the account write.
            if args.approval_token not in {None, preview["approval_token"]}:
                print(json.dumps(preview, ensure_ascii=False, indent=2))
                return 4
            result = _compose(
                document,
                approval_token=preview["approval_token"],
                data_dir=data_dir,
                editor_url=str(editor_url),
                close_after=args.close_after,
                cdp_endpoint=args.cdp_endpoint,
                browser_channel=args.browser_channel,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        action = "schedule" if args.command == "schedule" else "publish"
        scheduled_at = args.at if action == "schedule" else None
        store = CheckpointStore(data_dir)
        checkpoint = store.load_existing(document)
        preview = approval_preview(
            document, action=action, scheduled_at=scheduled_at,
            target_url=checkpoint.get("draft_url"),
            saved_surface_hash=checkpoint.get("saved_surface_hash"),
        )
        if args.approval_token != preview["approval_token"]:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 4
        store = CheckpointStore(data_dir)
        checkpoint = store.load_existing(document)
        draft_url = _verified_draft_url(str(checkpoint.get("draft_url") or ""))
        if draft_url is None:
            raise ValueError("checkpoint has no verified draft URL; compose or resume first")
        with NaverBrowserSession(
            data_dir=data_dir,
            editor_url=draft_url,
            cdp_endpoint=args.cdp_endpoint,
            browser_channel=args.browser_channel,
        ) as browser:
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
