#!/usr/bin/env python3
"""Guarded Tistory Markdown/HTML editor automation with local image privacy."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from file_safety import read_text_limited, resolve_input_file, write_text_atomically
from privacy_mosaic import (
    MosaicDependencyError,
    analyze_image,
    apply_plan,
    derived_output_path,
)
from tistory_document import (
    build_operations,
    document_hash,
    validate_document,
    validate_media_url,
    validate_schedule,
)
from url_safety import make_safe_playwright_route_handler

SCHEMA_VERSION = 1
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FEATURE_CATALOG_PATH = PLUGIN_ROOT / "data" / "tistory-editor-features.json"
ALLOWED_LOGIN_HOSTS = {
    "tistory.com",
    "www.tistory.com",
    "accounts.kakao.com",
    "logins.daum.net",
}
AUTOMATIC_HANDLERS = {
    "select-mode",
    "fill-title",
    "fill-body",
    "upload-image",
    "set-tags",
    "set-publish-option",
    "save-draft",
    "guarded-publish",
}


class EditorError(RuntimeError):
    pass


class EditorUIChanged(EditorError):
    pass


class StaleElementReference(EditorError):
    pass


class AmbiguousElement(EditorUIChanged):
    pass


class ApprovalRequired(EditorError):
    pass


class UploadResultUnknown(EditorError):
    pass


class PublishResultUnknown(EditorError):
    pass


class FeatureCatalog:
    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Tistory editor feature catalog schema_version must be 1")
        values = payload.get("features")
        if not isinstance(values, list) or not values:
            raise ValueError("Tistory editor feature catalog is empty")
        self.catalog_version = str(payload.get("catalog_version") or "")
        self.features: dict[str, dict[str, Any]] = {}
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("each Tistory editor feature requires an id")
            identifier = item["id"]
            if identifier in self.features:
                raise ValueError(f"duplicate Tistory editor feature: {identifier}")
            if item.get("status") not in {"automatic", "guided", "unavailable"}:
                raise ValueError(f"invalid Tistory feature status: {identifier}")
            if item.get("status") == "automatic" and item.get("handler") not in AUTOMATIC_HANDLERS:
                raise ValueError(f"automatic Tistory feature has no handler: {identifier}")
            if not isinstance(item.get("locator"), dict):
                raise ValueError(f"Tistory feature has no locator contract: {identifier}")
            self.features[identifier] = copy.deepcopy(item)

    @classmethod
    def load(cls, path: Path = FEATURE_CATALOG_PATH) -> "FeatureCatalog":
        value = json.loads(read_text_limited(path, extensions={".json"}))
        if not isinstance(value, dict):
            raise ValueError("Tistory editor feature catalog must be an object")
        return cls(value)

    def feature(self, identifier: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self.features[identifier])
        except KeyError as exc:
            raise ValueError(f"unknown Tistory editor feature: {identifier}") from exc


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
    broad = {Path(value.anchor).resolve()}
    try:
        broad.add(Path.home().resolve())
    except RuntimeError:
        pass
    if value in broad:
        raise ValueError("Tistory editor data must use a dedicated subdirectory")
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
    return base.expanduser().resolve(strict=False) / "tistory-editor-profile"


def profile_directory(data_dir: str | os.PathLike[str] | None = None) -> Path:
    return _dedicated_directory(_profile_path(data_dir))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CheckpointStore:
    """Persist operation hashes and uploaded URLs, never title, body, or source paths."""

    def __init__(self, data_dir: str | os.PathLike[str] | None = None) -> None:
        base = Path(data_dir) if data_dir is not None else _default_data_dir()
        self.directory = _dedicated_directory(base / "tistory-editor-checkpoints")

    def path_for(self, document_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", document_id):
            raise ValueError("unsafe Tistory checkpoint document id")
        return self.directory / f"{document_id}.json"

    @staticmethod
    def _new(document: dict[str, Any]) -> dict[str, Any]:
        media_ids = [item["id"] for item in document["media"]]
        return {
            "schema_version": SCHEMA_VERSION,
            "document_id": document["document_id"],
            "source_hash": document_hash(document),
            "completed_operation_ids": [],
            "media_states": {identifier: "pending" for identifier in media_ids},
            "media_urls": {},
            "draft_url": None,
            "publish_state": "not-attempted",
            "published_url": None,
            "diagnostic_files": [],
            "last_error_type": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def load_or_create(self, document: object) -> dict[str, Any]:
        value = validate_document(document)
        expected_hash = document_hash(value)
        path = self.path_for(value["document_id"])
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
            raise ValueError("no resumable Tistory checkpoint exists for this document")
        checkpoint = json.loads(read_text_limited(path, extensions={".json"}))
        if (
            not isinstance(checkpoint, dict)
            or checkpoint.get("source_hash") != document_hash(value)
        ):
            raise ValueError("Tistory checkpoint source hash does not match the document")
        return checkpoint

    def save(self, checkpoint: dict[str, Any]) -> None:
        allowed = {
            "schema_version",
            "document_id",
            "source_hash",
            "completed_operation_ids",
            "media_states",
            "media_urls",
            "draft_url",
            "publish_state",
            "published_url",
            "diagnostic_files",
            "last_error_type",
            "updated_at",
        }
        if set(checkpoint) - allowed:
            raise ValueError("Tistory checkpoint contains unsupported content-bearing fields")
        value = copy.deepcopy(checkpoint)
        states = value.get("media_states")
        urls = value.get("media_urls")
        if not isinstance(states, dict) or not isinstance(urls, dict):
            raise ValueError("Tistory checkpoint media state is malformed")
        if any(state not in {"pending", "attempting", "uploaded", "unknown"} for state in states.values()):
            raise ValueError("Tistory checkpoint contains an invalid media state")
        for identifier, url in urls.items():
            if states.get(identifier) != "uploaded":
                raise ValueError("uploaded media URL has no matching uploaded state")
            validate_media_url(url)
        value["updated_at"] = datetime.now(timezone.utc).isoformat()
        path = write_text_atomically(
            self.path_for(str(value["document_id"])),
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            extensions={".json"},
        )
        try:
            path.chmod(0o600)
        except OSError:
            pass


class TistoryEditorAutomation:
    def __init__(self, store: CheckpointStore) -> None:
        self.store = store

    def apply(
        self,
        document: object,
        driver: Any,
        *,
        prepared_media: dict[str, Path],
    ) -> dict[str, Any]:
        value = validate_document(document)
        if value["publish_settings"]["mode"] != "draft":
            raise ValueError("compose and resume require publish_settings.mode=draft")
        expected_ids = {item["id"] for item in value["media"]}
        if set(prepared_media) != expected_ids:
            raise ValueError("prepared media IDs do not match TistoryDocument media")
        checkpoint = self.store.load_or_create(value)
        for media in value["media"]:
            identifier = media["id"]
            state = checkpoint["media_states"].get(identifier, "pending")
            if state in {"attempting", "unknown"}:
                raise UploadResultUnknown(
                    f"media {identifier} has an unclear prior upload; reconcile it manually before retrying"
                )
            if state == "uploaded":
                validate_media_url(checkpoint["media_urls"][identifier])
                continue
            checkpoint["media_states"][identifier] = "attempting"
            self.store.save(checkpoint)
            try:
                path = resolve_input_file(prepared_media[identifier])
                uploaded_url = driver.upload_media(
                    media, path, document_format=value["format"]
                )
                checkpoint["media_urls"][identifier] = validate_media_url(uploaded_url)
                checkpoint["media_states"][identifier] = "uploaded"
                checkpoint["last_error_type"] = None
                self.store.save(checkpoint)
            except Exception as exc:
                checkpoint["media_states"][identifier] = "unknown"
                checkpoint["last_error_type"] = type(exc).__name__
                diagnostic = driver.capture_diagnostic(type(exc).__name__)
                if diagnostic and diagnostic not in checkpoint["diagnostic_files"]:
                    checkpoint["diagnostic_files"].append(diagnostic)
                self.store.save(checkpoint)
                if isinstance(exc, UploadResultUnknown):
                    raise
                raise UploadResultUnknown(
                    f"media {identifier} upload result is unclear; automatic retry is disabled"
                ) from exc

        completed = set(checkpoint.get("completed_operation_ids", []))
        for operation in build_operations(value, checkpoint["media_urls"]):
            operation_id = operation["operation_id"]
            if operation_id in completed:
                try:
                    if driver.verify(operation):
                        continue
                except Exception:
                    pass
            try:
                try:
                    driver.execute(operation)
                except StaleElementReference:
                    if not driver.verify(operation):
                        driver.execute(operation)
                if not driver.verify(operation):
                    raise EditorUIChanged(
                        f"postcondition failed for {operation['feature_id']}"
                    )
            except Exception as exc:
                checkpoint["last_error_type"] = type(exc).__name__
                diagnostic = driver.capture_diagnostic(type(exc).__name__)
                if diagnostic and diagnostic not in checkpoint["diagnostic_files"]:
                    checkpoint["diagnostic_files"].append(diagnostic)
                self.store.save(checkpoint)
                raise
            completed.add(operation_id)
            checkpoint["completed_operation_ids"] = sorted(completed)
            checkpoint["last_error_type"] = None
            self.store.save(checkpoint)
        return checkpoint


def build_privacy_preflight(document: object) -> dict[str, dict[str, Any]]:
    value = validate_document(document)
    result: dict[str, dict[str, Any]] = {}
    for media in value["media"]:
        source = Path(media["path"])
        privacy = media["privacy"]
        no_processing = (
            privacy["mode"] == "none"
            and not privacy["mosaic_face_ids"]
            and not privacy["regions"]
            and not privacy["strip_metadata"]
        )
        if no_processing:
            result[media["id"]] = {
                "source_sha256": _sha256_file(source),
                "plan": None,
                "summary": {
                    "detected_face_count": None,
                    "main_face_id": None,
                    "kept_face_count": None,
                    "mosaic_face_count": 0,
                    "custom_region_count": 0,
                    "review_required": False,
                    "review_reason": "privacy-disabled-by-document",
                },
            }
            continue
        analysis = analyze_image(source, policy=privacy)
        result[media["id"]] = analysis
    return result


def draft_preview(
    document: object,
    *,
    privacy_preflight: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    value = validate_document(document)
    expected = {item["id"] for item in value["media"]}
    if set(privacy_preflight) != expected:
        raise ValueError("privacy preflight does not match TistoryDocument media")
    privacy: dict[str, dict[str, Any]] = {}
    token_privacy: dict[str, dict[str, Any]] = {}
    for identifier, item in privacy_preflight.items():
        summary = copy.deepcopy(item.get("summary") or {})
        privacy[identifier] = summary
        token_privacy[identifier] = {
            "source_sha256": item.get("source_sha256"),
            "summary": summary,
        }
    material = json.dumps(
        {
            "action": "compose-and-save-tistory-draft",
            "document_hash": document_hash(value),
            "privacy": token_privacy,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": 1,
        "approval_required": True,
        "action": "compose-and-save-tistory-draft",
        "document_id": value["document_id"],
        "title": value["title"],
        "format": value["format"],
        "block_count": len(value["blocks"]),
        "media_count": len(value["media"]),
        "tags": value["tags"],
        "publish_settings": value["publish_settings"],
        "privacy": privacy,
        "approval_token": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
    }


def prepare_media(
    document: object,
    privacy_preflight: dict[str, dict[str, Any]],
    *,
    data_dir: Path,
) -> dict[str, Path]:
    value = validate_document(document)
    prepared: dict[str, Path] = {}
    for media in value["media"]:
        identifier = media["id"]
        source = Path(media["path"])
        preflight = privacy_preflight.get(identifier)
        if not isinstance(preflight, dict):
            raise ValueError(f"privacy preflight is missing for media: {identifier}")
        if _sha256_file(source) != preflight.get("source_sha256"):
            raise ValueError(
                f"media changed after privacy approval preview: {identifier}"
            )
        plan = preflight.get("plan")
        if plan is None:
            prepared[identifier] = source
            continue
        destination = derived_output_path(source, plan, data_dir=data_dir)
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                raise ValueError("privacy derivative path is unsafe")
        apply_plan(source, destination, plan, overwrite=destination.exists())
        prepared[identifier] = destination
    return prepared


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
        candidate = scheduled_at or settings.get("scheduled_at")
        if not candidate:
            raise ValueError("scheduled_at is required for schedule")
        settings["scheduled_at"] = validate_schedule(candidate)
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
    material = json.dumps(
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
    return {
        "schema_version": 1,
        "approval_required": True,
        "action": action,
        "document_id": value["document_id"],
        "title": value["title"],
        "category": settings["category"],
        "visibility": settings["visibility"],
        "comments_allowed": settings["comments_allowed"],
        "tags": value["tags"],
        "scheduled_at": settings["scheduled_at"],
        "approval_token": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
    }


def _is_tistory_host(host: str) -> bool:
    value = host.casefold().rstrip(".")
    return value == "tistory.com" or value.endswith(".tistory.com")


def _is_published_tistory_url(value: str) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    return (
        parsed.scheme == "https"
        and host not in {"tistory.com", "www.tistory.com"}
        and host.endswith(".tistory.com")
        and parsed.username is None
        and parsed.password is None
        and "/manage/" not in parsed.path.casefold()
        and parsed.path not in {"", "/"}
    )


def _is_scheduled_result_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and _is_tistory_host(parsed.hostname or "")
        and parsed.username is None
        and parsed.password is None
        and "/manage/post" in parsed.path.casefold()
    )


def _validated_action_result(action: str, result: object) -> str | None:
    if not isinstance(result, dict) or not isinstance(result.get("url"), str):
        return None
    url = result["url"]
    if action == "publish":
        return url if _is_published_tistory_url(url) else None
    if action == "schedule" and result.get("scheduled") is True:
        if _is_published_tistory_url(url) or _is_scheduled_result_url(url):
            return url
    return None


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
        raise ApprovalRequired("the exact per-document Tistory approval token is required")
    if os.environ.get("AUTOSEO_TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError("Tistory publish actions are disabled in automated tests")
    if checkpoint.get("source_hash") != document_hash(value):
        raise ValueError("Tistory checkpoint source hash does not match the document")
    if checkpoint.get("publish_state") in {"attempting", "unknown", "published", "scheduled"}:
        raise PublishResultUnknown(
            "a prior Tistory publish result exists or is unclear; reconcile it manually before retrying"
        )
    media_urls = checkpoint.get("media_urls") or {}
    required = {item["operation_id"] for item in build_operations(value, media_urls)}
    if not required.issubset(set(checkpoint.get("completed_operation_ids", []))):
        raise ValueError("the Tistory draft has incomplete editor operations; resume it first")

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
            "Tistory publish result is unclear; automatic retry is disabled"
        ) from exc
    result_url = _validated_action_result(action, result)
    if result_url is None:
        checkpoint["publish_state"] = "unknown"
        if store:
            store.save(checkpoint)
        raise PublishResultUnknown(
            "Tistory publish result is unclear; automatic retry is disabled"
        )
    checkpoint["publish_state"] = "scheduled" if action == "schedule" else "published"
    checkpoint["published_url"] = result_url
    if store:
        store.save(checkpoint)
    return checkpoint


class LocatorResolver:
    """Resolve accessible role/name, Korean label, shortcut, then DOM fallback."""

    def __init__(self, page: Any, catalog: FeatureCatalog) -> None:
        self.page = page
        self.catalog = catalog

    @staticmethod
    def _count(locator: Any) -> int:
        try:
            return int(locator.count())
        except Exception as exc:
            message = str(exc).casefold()
            if "stale" in message or "detached" in message:
                raise StaleElementReference("Tistory editor element became stale") from exc
            raise

    def _unique(self, locator: Any, description: str) -> Any | None:
        count = self._count(locator)
        if count > 1:
            raise AmbiguousElement(f"multiple Tistory controls matched {description}")
        return locator if count == 1 else None

    def locate(self, feature_id: str, *, allow_shortcut: bool = False) -> tuple[str, Any]:
        feature = self.catalog.feature(feature_id)
        locator = feature["locator"]
        role = locator.get("role")
        for name in locator.get("names") or ([locator.get("name")] if locator.get("name") else []):
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
        raise EditorUIChanged(f"no unique Tistory control found for {feature_id}")

    def click(self, feature_id: str) -> str:
        strategy, target = self.locate(feature_id, allow_shortcut=True)
        try:
            if strategy == "shortcut":
                self.page.keyboard.press(target)
            else:
                target.click()
        except Exception as exc:
            message = str(exc).casefold()
            if "stale" in message or "detached" in message:
                raise StaleElementReference("Tistory editor element became stale") from exc
            raise EditorUIChanged(f"Tistory control failed for {feature_id}") from exc
        return strategy

    def probe(self, feature_id: str) -> dict[str, Any]:
        try:
            strategy, _ = self.locate(feature_id)
            return {"available": True, "strategy": strategy}
        except AmbiguousElement:
            return {"available": False, "strategy": None, "reason": "ambiguous"}
        except EditorUIChanged:
            return {"available": False, "strategy": None, "reason": "not-found"}


class PlaywrightTistoryDriver:
    """Real Tistory adapter; source mode is selected once and writes are verified."""

    def __init__(self, page: Any, *, catalog: FeatureCatalog, data_dir: Path) -> None:
        self.page = page
        self.catalog = catalog
        self.resolver = LocatorResolver(page, catalog)
        self.data_dir = data_dir
        self._current_format: str | None = None
        self._postconditions: dict[str, bool] = {}

    @property
    def _select_all(self) -> str:
        return "Meta+A" if sys.platform == "darwin" else "Control+A"

    def _switch_mode(self, target: str) -> None:
        if target not in {"basic", "markdown", "html"}:
            raise ValueError("unsupported Tistory editor mode")
        if self._current_format == target:
            return
        self.resolver.click("editor-mode")
        self.resolver.click(f"mode-{target}")
        self._current_format = target
        self.page.wait_for_timeout(150)

    def _source_editor(self) -> tuple[str, Any]:
        code_mirror = self.page.locator(".CodeMirror")
        if code_mirror.count() == 1:
            return "codemirror5", code_mirror
        cm6 = self.page.locator(".cm-content[contenteditable='true']")
        if cm6.count() == 1:
            return "codemirror6", cm6
        textareas = self.page.locator(
            "textarea[aria-label*='본문'], textarea[name='content'], textarea#editor-textarea"
        )
        if textareas.count() == 1:
            return "textarea", textareas
        raise EditorUIChanged("Tistory Markdown/HTML source editor is missing or ambiguous")

    def _set_source(self, value: str) -> None:
        kind, editor = self._source_editor()
        try:
            if kind == "codemirror5":
                editor.evaluate(
                    "(node, text) => { node.CodeMirror.setValue(text); node.CodeMirror.save(); node.CodeMirror.refresh(); }",
                    value,
                )
            elif kind == "textarea":
                editor.fill(value)
            else:
                editor.click()
                self.page.keyboard.press(self._select_all)
                self.page.keyboard.insert_text(value)
        except Exception as exc:
            raise EditorUIChanged("Tistory source editor rejected the document body") from exc

    def _source_value(self) -> str:
        kind, editor = self._source_editor()
        try:
            if kind == "codemirror5":
                return str(editor.evaluate("node => node.CodeMirror.getValue()"))
            if kind == "textarea":
                return str(editor.input_value())
            return str(editor.inner_text())
        except Exception as exc:
            raise EditorUIChanged("Tistory source editor value could not be verified") from exc

    def _basic_body(self) -> Any:
        candidates = self.page.locator(
            ".ProseMirror[contenteditable='true'], .tt_article_useless_p_margin[contenteditable='true'], "
            "#editor [contenteditable='true']"
        )
        count = candidates.count()
        if count != 1:
            raise EditorUIChanged("Tistory basic editor body is missing or ambiguous")
        return candidates

    def _clear_basic_body(self) -> None:
        body = self._basic_body()
        body.click()
        self.page.keyboard.press(self._select_all)
        self.page.keyboard.press("Backspace")

    def _body_image_urls(self, body: Any) -> list[str]:
        images = body.locator("img[src]")
        urls: list[str] = []
        for index in range(images.count()):
            candidate = images.nth(index).get_attribute("src")
            if not candidate:
                continue
            try:
                value = validate_media_url(candidate)
            except ValueError:
                continue
            if value not in urls:
                urls.append(value)
        return urls

    def _trigger_image_upload(self, path: Path) -> None:
        fallback = self.catalog.feature("image-upload")["locator"].get("file_input")
        if fallback:
            inputs = self.page.locator(fallback)
            if inputs.count() == 1:
                inputs.set_input_files(str(path))
                return
            if inputs.count() > 1:
                raise AmbiguousElement("multiple Tistory image file inputs matched")
        try:
            with self.page.expect_file_chooser(timeout=5_000) as chooser_info:
                self.resolver.click("image-upload")
            chooser_info.value.set_files(str(path))
        except Exception as exc:
            raise EditorUIChanged("Tistory image upload control did not open once") from exc

    def upload_media(self, media: dict[str, Any], path: Path, *, document_format: str) -> str:
        del document_format
        self._switch_mode("basic")
        self._clear_basic_body()
        body = self._basic_body()
        before = set(self._body_image_urls(body))
        self._trigger_image_upload(path)
        deadline = time.monotonic() + 60
        observed: list[str] = []
        while time.monotonic() < deadline:
            observed = [
                url
                for url in self._body_image_urls(body)
                if url not in before
            ]
            if len(observed) == 1:
                break
            if len(observed) > 1:
                raise UploadResultUnknown(
                    f"upload inserted multiple candidate URLs for media {media['id']}"
                )
            self.page.wait_for_timeout(250)
        if len(observed) != 1:
            raise UploadResultUnknown(
                f"uploaded URL was not observable for media {media['id']}"
            )
        self._clear_basic_body()
        return validate_media_url(observed[0])

    def execute(self, operation: dict[str, Any]) -> None:
        feature_id = operation["feature_id"]
        payload = operation["payload"]
        try:
            if feature_id == "editor-mode":
                self._switch_mode(payload["format"])
            elif feature_id == "title":
                _, locator = self.resolver.locate("title")
                locator.fill(payload["text"])
            elif feature_id == "body-source":
                if self._current_format != payload["format"]:
                    raise EditorUIChanged("Tistory source mode changed unexpectedly")
                self._set_source(payload["text"])
            elif feature_id == "tags":
                if payload["tags"]:
                    _, locator = self.resolver.locate("tags")
                    for tag in payload["tags"]:
                        locator.fill(tag)
                        self.page.keyboard.press("Enter")
            elif feature_id == "draft-save":
                self.resolver.click("draft-save")
                self.page.wait_for_timeout(250)
            else:
                raise EditorUIChanged(f"unsupported Tistory operation: {feature_id}")
        except StaleElementReference:
            raise
        except EditorError:
            raise
        except Exception as exc:
            message = str(exc).casefold()
            if "stale" in message or "detached" in message:
                raise StaleElementReference("Tistory editor element became stale") from exc
            raise EditorUIChanged(f"Tistory operation failed for {feature_id}") from exc
        self._postconditions[operation["operation_id"]] = True

    def verify(self, operation: dict[str, Any]) -> bool:
        feature_id = operation["feature_id"]
        payload = operation["payload"]
        try:
            if feature_id == "editor-mode":
                expected_label = {
                    "basic": "기본모드",
                    "markdown": "마크다운",
                    "html": "HTML",
                }[payload["format"]]
                return (
                    self._current_format == payload["format"]
                    and self.page.get_by_role(
                        "button", name=expected_label, exact=True
                    ).count()
                    == 1
                )
            if feature_id == "title":
                _, locator = self.resolver.locate("title")
                return locator.input_value() == payload["text"]
            if feature_id == "body-source":
                expected = payload["text"].replace("\r\n", "\n").strip()
                actual = self._source_value().replace("\r\n", "\n").strip()
                return hashlib.sha256(actual.encode()).digest() == hashlib.sha256(
                    expected.encode()
                ).digest()
            if feature_id == "tags":
                return all(
                    self.page.get_by_text(tag, exact=True).count() >= 1
                    for tag in payload["tags"]
                )
            if feature_id == "draft-save":
                return any(
                    self.page.get_by_text(message, exact=False).count() >= 1
                    for message in (
                        "임시저장 완료",
                        "임시 저장되었습니다",
                        "저장되었습니다",
                    )
                )
        except Exception:
            return False
        return self._postconditions.get(operation["operation_id"], False)

    def capture_diagnostic(self, reason: str) -> str:
        directory = _dedicated_directory(self.data_dir / "tistory-editor-diagnostics")
        path = directory / f"{int(time.time())}-{reason}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
            path.chmod(0o600)
            return str(path)
        except Exception:
            return ""

    def _set_option(self, feature_id: str, value: Any) -> None:
        _, locator = self.resolver.locate(feature_id)
        try:
            tag_name = locator.evaluate("node => node.tagName.toLowerCase()")
            if tag_name == "select":
                locator.select_option(label=str(value))
            elif isinstance(value, bool):
                checked = bool(locator.is_checked())
                if checked != value:
                    locator.click()
            else:
                locator.click()
                option = self.page.get_by_text(str(value), exact=True)
                if option.count() != 1:
                    raise AmbiguousElement(
                        f"Tistory option is missing or ambiguous for {feature_id}"
                    )
                option.click()
        except EditorError:
            raise
        except Exception as exc:
            raise EditorUIChanged(f"Tistory setting failed for {feature_id}") from exc

    def apply_publish_settings(self, settings: dict[str, Any]) -> None:
        self.resolver.click("publish-dialog")
        if settings.get("category"):
            self._set_option("category", settings["category"])
        self._set_option("visibility", settings["visibility"])
        self._set_option("comments-allowed", settings["comments_allowed"])
        if settings["mode"] == "schedule":
            self.resolver.click("schedule-option")
            parsed = datetime.fromisoformat(settings["scheduled_at"].replace("Z", "+00:00"))
            combined = self.page.locator("input[type='datetime-local']")
            if combined.count() == 1:
                combined.fill(parsed.strftime("%Y-%m-%dT%H:%M"))
                return
            date_fields = self.page.locator("input[type='date']")
            time_fields = self.page.locator("input[type='time']")
            if date_fields.count() != 1 or time_fields.count() != 1:
                raise AmbiguousElement(
                    "Tistory schedule date/time inputs are missing or ambiguous"
                )
            date_fields.fill(parsed.strftime("%Y-%m-%d"))
            time_fields.fill(parsed.strftime("%H:%M"))

    def click_publish(self, action: str) -> None:
        self.resolver.click("schedule-publish" if action == "schedule" else "publish")

    def verify_publish(self, action: str) -> dict[str, Any] | None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        url = str(self.page.url)
        if _is_published_tistory_url(url):
            return {"url": url, "action": action, "scheduled": action == "schedule"}
        if action == "schedule" and _is_scheduled_result_url(url):
            scheduled = any(
                self.page.get_by_text(message, exact=False).count() >= 1
                for message in ("예약되었습니다", "예약 발행", "예약 완료")
            )
            if scheduled:
                return {"url": url, "action": action, "scheduled": True}
        candidates = self.page.locator("a[href*='.tistory.com/']")
        observed: list[str] = []
        for index in range(candidates.count()):
            value = candidates.nth(index).get_attribute("href")
            if value and _is_published_tistory_url(value) and value not in observed:
                observed.append(value)
        return (
            {
                "url": observed[0],
                "action": action,
                "scheduled": action == "schedule",
            }
            if len(observed) == 1
            else None
        )


def validate_editor_url(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if (
        parsed.scheme != "https"
        or not _is_tistory_host(host)
        or parsed.username is not None
        or parsed.password is not None
        or "/manage/" not in path
        or not any(marker in path for marker in ("newpost", "/post/"))
    ):
        raise ValueError("editor URL must be an HTTPS Tistory manage/newpost or manage/post URL")
    return value


def _verified_draft_url(value: str) -> str | None:
    try:
        validated = validate_editor_url(value)
    except ValueError:
        return None
    parsed = urlsplit(validated)
    query = parse_qs(parsed.query)
    path = parsed.path.casefold()
    if "/manage/post/" in path or any(key.casefold() in {"id", "postid"} for key in query):
        return validated
    return None


def _allowed_browser_host(host: str) -> bool:
    value = host.casefold().rstrip(".")
    return value in ALLOWED_LOGIN_HOSTS or value.endswith(".tistory.com")


class TistoryBrowserSession:
    """Headed persistent browser; Kakao login, 2FA, and CAPTCHA remain manual."""

    def __init__(self, *, data_dir: Path, editor_url: str) -> None:
        self.data_dir = _dedicated_directory(data_dir)
        self.editor_url = validate_editor_url(editor_url)
        self.playwright = None
        self.context = None
        self.page = None

    def __enter__(self) -> "TistoryBrowserSession":
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
        if not _allowed_browser_host(host):
            raise EditorUIChanged("browser left the allowlisted Tistory/Kakao hosts")

    def wait_for_editor(self, timeout_seconds: int = 600) -> Any:
        deadline = time.monotonic() + timeout_seconds
        announced = False
        while time.monotonic() < deadline:
            self._assert_allowed_page()
            host = (urlsplit(str(self.page.url)).hostname or "").casefold()
            if _is_tistory_host(host):
                title = self.page.locator(
                    "textarea[placeholder*='제목'], input[placeholder*='제목'], textarea[name='title']"
                )
                editable = self.page.locator(
                    ".CodeMirror, .cm-content[contenteditable='true'], .ProseMirror[contenteditable='true']"
                )
                if title.count() >= 1 and editable.count() >= 1:
                    return self.page
            if not announced:
                print(
                    "Complete Kakao/Tistory login, two-factor authentication, and any CAPTCHA "
                    "in the visible browser. AutoSEO will not enter or export them.",
                    file=sys.stderr,
                )
                announced = True
            self.page.wait_for_timeout(500)
        raise EditorUIChanged("Tistory editor was not ready before the login timeout")

    def keep_open_until_closed(self) -> None:
        print("Tistory draft is ready. Close the browser window to finish.", file=sys.stderr)
        try:
            while self.context.pages:
                live = [page for page in self.context.pages if not page.is_closed()]
                if not live:
                    return
                try:
                    live[0].wait_for_timeout(500)
                except Exception:
                    if live[0].is_closed():
                        return
                    raise
        except KeyboardInterrupt:
            pass


def learn_compatibility_map(
    page: Any, catalog: FeatureCatalog, *, editor_url: str
) -> dict[str, Any]:
    resolver = LocatorResolver(page, catalog)
    return {
        "schema_version": 1,
        "catalog_version": catalog.catalog_version,
        "editor_origin": f"{urlsplit(editor_url).scheme}://{urlsplit(editor_url).hostname}",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "features": {
            identifier: resolver.probe(identifier) for identifier in catalog.features
        },
        "note": "Local Tistory UI compatibility map only; no page text, cookies, or account data.",
    }


def _compatibility_path(data_dir: Path) -> Path:
    return _dedicated_directory(data_dir) / "tistory-editor-compatibility.json"


def _load_document(path: Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    return validate_document(value)


def _data_path(raw: str | None, *, create: bool = True) -> Path:
    value = _validated_dedicated_path(
        Path(raw).expanduser() if raw else _default_data_dir()
    )
    return _dedicated_directory(value) if create else value


def _compose(
    document: dict[str, Any],
    *,
    preflight: dict[str, dict[str, Any]],
    data_dir: Path,
    editor_url: str,
    close_after: bool,
) -> dict[str, Any]:
    prepared = prepare_media(document, preflight, data_dir=data_dir)
    store = CheckpointStore(data_dir)
    catalog = FeatureCatalog.load()
    with TistoryBrowserSession(data_dir=data_dir, editor_url=editor_url) as browser:
        page = browser.wait_for_editor()
        driver = PlaywrightTistoryDriver(page, catalog=catalog, data_dir=data_dir)
        checkpoint = TistoryEditorAutomation(store).apply(
            document, driver, prepared_media=prepared
        )
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
    learn.add_argument("--editor-url", required=True)
    learn.add_argument("--close-after", action="store_true")
    compose = sub.add_parser("compose")
    compose.add_argument("document", type=Path)
    compose.add_argument("--editor-url", required=True)
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
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            data_dir = _data_path(args.data_dir, create=False)
            catalog = FeatureCatalog.load()
            dependencies = {}
            for name in ("playwright", "PIL", "cv2"):
                try:
                    __import__(name)
                    dependencies[name] = True
                except ImportError:
                    dependencies[name] = False
            profile = _profile_path(data_dir)
            profile_exists = profile.is_dir() and not profile.is_symlink()
            permissions = oct(stat.S_IMODE(profile.stat().st_mode)) if profile_exists else None
            secure = not profile_exists or permissions == "0o700"
            result = {
                "schema_version": 1,
                "dependencies": dependencies,
                "catalog_version": catalog.catalog_version,
                "feature_count": len(catalog.features),
                "profile_directory": str(profile),
                "profile_exists": profile_exists,
                "profile_permissions": permissions,
                "editor_ready": dependencies["playwright"] and secure,
                "privacy_ready": dependencies["PIL"] and dependencies["cv2"],
                "ready": dependencies["playwright"] and secure,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 3

        data_dir = _data_path(args.data_dir)
        if args.command == "learn":
            catalog = FeatureCatalog.load()
            with TistoryBrowserSession(
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
            preflight = build_privacy_preflight(document)
            preview = draft_preview(document, privacy_preflight=preflight)
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
                        "resume requires a verified Tistory manage/post draft URL"
                    )
            result = _compose(
                document,
                preflight=preflight,
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
            raise ValueError("checkpoint has no verified Tistory draft URL; compose first")
        with TistoryBrowserSession(data_dir=data_dir, editor_url=draft_url) as browser:
            page = browser.wait_for_editor()
            driver = PlaywrightTistoryDriver(
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
    except (
        EditorError,
        MosaicDependencyError,
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"Tistory editor stopped safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
