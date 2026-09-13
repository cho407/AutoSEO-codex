"""Small shared safety primitives for local editor state and save receipts."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

KOREA_TIME = timezone(timedelta(hours=9), "Asia/Seoul")
CHECKPOINT_DEFAULTS = {
    "pending_operation_id": None, "save_state": "not-saved",
    "pending_feature_id": None, "pending_session_id": None,
    "saved_source_hash": None, "saved_surface_hash": None, "surface_hash": None,
    "target_url": None, "saved_at": None,
    "surface_version": None, "saved_session_id": None,
    # Kept only so checkpoints created by older releases remain readable. The
    # editor flow no longer performs a close-and-reopen draft verification.
    "verification_state": "not-verified", "verification_reason": None,
    "verified_at": None, "verified_surface_hash": None, "verified_session_id": None,
}


def browser_session_id(page) -> str:
    context = page.context
    if not getattr(context, "_autoseo_session_id", None):
        context._autoseo_session_id = uuid4().hex
    return context._autoseo_session_id


def invalidate_draft_verification(checkpoint: dict) -> None:
    for key in ("verification_state", "verification_reason", "verified_at", "verified_surface_hash", "verified_session_id"):
        checkpoint[key] = CHECKPOINT_DEFAULTS[key]


def mark_operation_pending(checkpoint: dict, operation: dict, driver) -> None:
    invalidate_draft_verification(checkpoint)
    checkpoint.update(pending_operation_id=operation["operation_id"],
                      pending_feature_id=operation["feature_id"],
                      pending_session_id=getattr(driver, "session_id", None),
                      save_state="saving" if operation["feature_id"] == "draft-save" else "dirty")


def local_schedule(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("schedule requires a timezone")
    if parsed.second or parsed.microsecond:
        raise ValueError("editor schedules have minute precision; specify zero seconds")
    return parsed.astimezone(KOREA_TIME).isoformat()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def attachment_stamps(document: dict) -> dict:
    """Cheap in-run change detection; approval and final-save hashes read bytes."""
    paths = [item["path"] for item in document.get("media", [])]
    if document.get("background", {}).get("path"):
        paths.append(document["background"]["path"])
    for block in document.get("blocks", []):
        paths.extend(block.get("paths", []))
        paths.extend(block[key] for key in ("path", "replace_path") if block.get(key))
    result = {}
    for path in paths:
        state = Path(path).stat()
        result[path] = (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns, state.st_ctime_ns)
    return result


@contextmanager
def exclusive_lock(path: Path):
    """OS-owned lock is released on a crash; never remove another run's lock."""
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    if path.is_symlink():
        raise ValueError("editor lock cannot be a symlink")
    descriptor = os.open(path, flags, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(descriptor)
        raise RuntimeError("another editor run holds this document/profile lock") from exc
    try:
        yield
    finally:
        os.close(descriptor)


def locked_document(method):
    @wraps(method)
    def wrapped(self, document, *args, **kwargs):
        if not isinstance(document, dict):
            raise ValueError("document must be an object")
        path = self.store.path_for(document.get("document_id", ""))
        with exclusive_lock(path.with_suffix(".lock")):
            return method(self, document, *args, **kwargs)
    return wrapped


def locked_publication(method):
    @wraps(method)
    def wrapped(document, checkpoint, driver, *, store=None, **kwargs):
        if store is None:
            return method(document, checkpoint, driver, store=store, **kwargs)
        with exclusive_lock(store.path_for(document["document_id"]).with_suffix(".lock")):
            fresh = store.load_existing(document)
            if {key: value for key, value in fresh.items() if key != "updated_at"} != {
                key: value for key, value in checkpoint.items() if key != "updated_at"
            }:
                raise ValueError("checkpoint changed since approval; request a new preview")
            return method(document, fresh, driver, store=store, **kwargs)
    return wrapped


def locked_profile_enter(method):
    @wraps(method)
    def wrapped(self):
        self._profile_lock = exclusive_lock(self.data_dir / f"{type(self).__name__}.lock")
        self._profile_lock.__enter__()
        try:
            return method(self)
        except BaseException:
            try:
                if self.context is not None:
                    self.context.close()
                if self.playwright is not None:
                    self.playwright.stop()
            finally:
                self._profile_lock.__exit__(None, None, None)
            raise
    return wrapped


def locked_profile_exit(method):
    @wraps(method)
    def wrapped(self, *args):
        try:
            return method(self, *args)
        finally:
            self._profile_lock.__exit__(None, None, None)
    return wrapped


def validate_checkpoint(checkpoint: object, document_id: str, source_hash: str) -> dict:
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != 1:
        raise ValueError("checkpoint is malformed; preserve it and reconcile manually")
    if checkpoint.get("document_id") != document_id or checkpoint.get("source_hash") != source_hash:
        raise ValueError("checkpoint source hash differs; use a new document ID for a revision")
    completed = checkpoint.get("completed_operation_ids")
    if not isinstance(completed, list) or any(not isinstance(item, str) for item in completed):
        raise ValueError("checkpoint operation history is malformed")
    if checkpoint.get("publish_state") not in {"not-attempted", "attempting", "unknown", "published", "scheduled"}:
        raise ValueError("checkpoint publish state is malformed")
    for key, value in CHECKPOINT_DEFAULTS.items():
        checkpoint.setdefault(key, value)
    if checkpoint["verification_state"] not in {"not-verified", "verified", "mismatch", "unavailable"}:
        raise ValueError("checkpoint verification state is malformed")
    return checkpoint


def draft_identity(url: str) -> tuple[str, str | None] | None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443}:
        return None
    query = {key.casefold(): value for key, value in parse_qs(parsed.query).items()}
    host = (parsed.hostname or "").casefold()
    if host in {"blog.naver.com", "m.blog.naver.com"}:
        blog_ids = query.get("blogid", [])
        parts = parsed.path.strip("/").split("/")
        blog = blog_ids[0] if len(blog_ids) == 1 else (parts[0] if len(parts) == 2 else None)
        if not blog or not all(char.isalnum() or char in "_-" for char in blog):
            return None
        ids = [value for key in ("logno", "draftno", "documentid") for value in query.get(key, [])]
        if len(parts) == 2 and parts[1].isdigit():
            ids.append(parts[1])
        if len(set(ids)) > 1:
            return None
        return f"naver:{blog}", ids[0] if ids else None
    if host.endswith(".tistory.com") and host not in {"www.tistory.com"}:
        parts = parsed.path.strip("/").split("/")
        ids = [value for key in ("postid", "id") for value in query.get(key, [])]
        if len(parts) == 3 and parts[:2] == ["manage", "post"] and parts[2].isdigit():
            ids.append(parts[2])
        elif len(parts) == 1 and parts[0].isdigit():
            ids.append(parts[0])
        if len(set(ids)) > 1:
            return None
        return f"tistory:{host}", ids[0] if ids else None
    return None


def bind_surface(checkpoint: dict, driver) -> None:
    if checkpoint["publish_state"] != "not-attempted":
        raise ValueError("prior publication exists or is unknown; reconcile before editing")
    if not hasattr(driver, "snapshot_hash"):
        return
    version = getattr(driver, "surface_version", None)
    if checkpoint.get("surface_hash") and checkpoint.get("surface_version") != version:
        raise ValueError("checkpoint fingerprint version changed; preserve and reconcile the original draft")
    checkpoint["surface_version"] = version
    if (not checkpoint.get("completed_operation_ids") and not checkpoint.get("pending_operation_id")
        and hasattr(driver, "has_existing_content") and driver.has_existing_content()):
        raise ValueError("editor already contains content; use its original checkpoint or reconcile manually")
    current = str(driver.page.url)
    expected = checkpoint.get("draft_url") or checkpoint.get("target_url")
    if expected and draft_identity(expected) != draft_identity(current):
        raise ValueError("target blog/draft changed; reconcile before editing")
    checkpoint["target_url"] = expected or current
    actual_hash = driver.snapshot_hash()
    if checkpoint.get("surface_hash") and actual_hash != checkpoint["surface_hash"]:
        if not checkpoint.get("pending_operation_id"):
            raise ValueError("editor content changed since checkpoint; reconcile without overwriting")
    if not checkpoint.get("surface_hash"):
        checkpoint["surface_hash"] = actual_hash


def record_operation(checkpoint: dict, operation: dict, driver) -> None:
    checkpoint["pending_operation_id"] = None
    checkpoint["pending_feature_id"] = None
    checkpoint["pending_session_id"] = None
    invalidate_draft_verification(checkpoint)
    if hasattr(driver, "snapshot_hash"):
        checkpoint["surface_hash"] = driver.snapshot_hash()
        current = str(driver.page.url)
        identity = draft_identity(current)
        if identity and identity[1]:
            checkpoint["draft_url"] = current
    if operation["feature_id"] == "draft-save":
        checkpoint["save_state"] = "acknowledged"
        checkpoint["saved_source_hash"] = checkpoint["source_hash"]
        checkpoint["saved_surface_hash"] = checkpoint.get("surface_hash")
        checkpoint["saved_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint["saved_session_id"] = getattr(driver, "session_id", None)


class FreshSaveReceipt:
    """Observe a new save message mutation, not a pre-existing success string."""
    def __init__(self, page):
        self.page = page
        self.acknowledged = False

    def begin(self):
        self.acknowledged = False
        self.page.evaluate("""() => {
            window.__autoseoSaveObserver?.disconnect();
            window.__autoseoSaveAck = false;
            const message = /임시저장 완료|임시 저장되었습니다|저장되었습니다|Draft saved|Saved as draft|Saved successfully/i;
            const hasSuccess = () => [...document.querySelectorAll(
                '[role=status], [role=alert], #status, .se-toast-message, .toast, .wrap_toast'
            )].some(node => !node.closest('[contenteditable=true]') && node.getClientRects().length
                && getComputedStyle(node).visibility !== 'hidden' && message.test(node.textContent || ''));
            let cleared = !hasSuccess();
            window.__autoseoSaveObserver = new MutationObserver(() => {
                const success = hasSuccess();
                if (!success) cleared = true;
                if (success && cleared) window.__autoseoSaveAck = true;
            });
            window.__autoseoSaveObserver.observe(document.body, {subtree: true, childList: true,
                characterData: true, attributes: true, attributeFilter: ['hidden','style','class','aria-busy']});
        }""")

    def confirm(self, timeout: int = 10000) -> bool:
        try:
            self.page.wait_for_function("window.__autoseoSaveAck === true", timeout=timeout)
            self.acknowledged = True
        except Exception:
            self.acknowledged = False
        finally:
            self.page.evaluate("window.__autoseoSaveObserver?.disconnect()")
        return self.acknowledged


def prepare_publication(driver, document: dict, checkpoint: dict, settings: dict) -> None:
    if checkpoint.get("publish_state") != "not-attempted":
        raise ValueError("prior publication exists or is unknown; reconcile before publication")
    if checkpoint.get("surface_version") != getattr(driver, "surface_version", None):
        raise ValueError("editor surface version changed; reconcile before publication")
    target = checkpoint.get("draft_url")
    identity = draft_identity(target or "")
    if not identity or not identity[1] or draft_identity(str(driver.page.url)) != identity:
        raise ValueError("exact blog and saved draft identity must match before publication")
    if (checkpoint.get("pending_operation_id")
        or checkpoint.get("save_state") not in {"acknowledged", "readback-confirmed"}
        or checkpoint.get("saved_source_hash") != checkpoint.get("source_hash")
        or not checkpoint.get("saved_surface_hash")
        or driver.snapshot_hash() != checkpoint["saved_surface_hash"]):
        raise ValueError("saved draft acknowledgement or content fingerprint is unavailable; reconcile and approve a new preview")
    media_urls = list(checkpoint.get("media_urls", {}).values())
    if "media" not in document:
        for frame in driver.page.frames:
            images = frame.locator(".se-main-container img[src]")
            media_urls.extend(images.nth(index).get_attribute("src") for index in range(images.count()))
    driver._publication = {"identity": identity, "document": document, "settings": settings,
                           "media_urls": media_urls}


def _public_post_matches(url: str, binding: dict) -> bool:
    """Read back a public post without the editor's login/cookies."""
    from bs4 import BeautifulSoup
    from fetch_page import fetch_page

    response = fetch_page(url)
    if response.get("error") or response.get("status_code") != 200:
        return False
    if draft_identity(response.get("url") or url) != binding["identity"]:
        return False
    soup = BeautifulSoup(response.get("content") or "", "html.parser")
    title = binding["document"]["title"]
    titles = [node.get_text(" ", strip=True) for node in soup.select("h1, .se-documentTitle")]
    titles.extend(node.get("content", "") for node in soup.select('meta[property="og:title"]'))
    if title not in titles:
        return False
    roots = soup.select("article, .se-main-container, .entry-content")
    roots = [node for node in roots if not any(parent in roots for parent in node.parents)]
    if len(roots) != 1:
        return False
    text = " ".join(roots[0].get_text(" ", strip=True).split())
    if any(" ".join(block["text"].split()) not in text
           for block in binding["document"]["blocks"] if block.get("text")):
        return False
    media = {node.get("src") for node in roots[0].select("img[src]")}
    return all(value in media for value in binding["media_urls"])


def publication_result(driver, action: str) -> dict | None:
    """Positive matching evidence only; home pages and old links never count."""
    binding = getattr(driver, "_publication", None)
    if not binding:
        return None
    url = str(driver.page.url)
    if draft_identity(url) != binding["identity"]:
        return None
    parsed = urlsplit(url)
    if action == "publish" and ("/manage/" in parsed.path or "write" in parsed.path.casefold()):
        return None
    settings = binding["settings"]
    if action == "publish" and settings["visibility"] == "public":
        if not _public_post_matches(url, binding):
            return None
        return {"url": url, "action": action, "identity": binding["identity"],
                "visibility": "public", "content_verified": True, "method": "anonymous-post-readback"}
    # A visible post-specific status is required. Unsupported UI stays unknown.
    status = driver.page.locator("[data-post-id][data-visibility]")
    if status.count() != 1:
        return None
    if status.get_attribute("data-post-id") != binding["identity"][1] or status.get_attribute("data-visibility") != settings["visibility"]:
        return None
    if action == "schedule":
        if status.get_attribute("data-status") != "scheduled":
            return None
        try:
            if local_schedule(status.get_attribute("data-scheduled-at")) != settings["scheduled_at"]:
                return None
        except (ValueError, AttributeError):
            return None
    content = driver.page.locator("article, .se-main-container, .entry-content")
    if content.count() != 1:
        return None
    text = " ".join(content.inner_text().split())
    expected = binding["document"]
    for block in expected["blocks"]:
        if block.get("text") and " ".join(block["text"].split()) not in text:
            return None
    if driver.page.get_by_text(expected["title"], exact=True).count() != 1:
        return None
    return {"url": url, "action": action, "scheduled": action == "schedule",
            "identity": binding["identity"], "visibility": settings["visibility"],
            "scheduled_at": settings.get("scheduled_at"), "content_verified": True}
