from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/autoseo/scripts"))

import naver_document as naver_document_module  # noqa: E402
import naver_editor  # noqa: E402
import tistory_editor  # noqa: E402
from test_naver_editor import _document as naver_document  # noqa: E402
from test_tistory_editor import _document as tistory_document  # noqa: E402


@pytest.mark.parametrize("module,factory", [(naver_editor, naver_document), (tistory_editor, tistory_document)])
def test_changed_source_cannot_erase_publication_history(tmp_path, module, factory) -> None:
    document = factory(tmp_path) if module is tistory_editor else factory()
    store = module.CheckpointStore(tmp_path)
    checkpoint = store.load_or_create(document)
    checkpoint["publish_state"] = "unknown"
    store.save(checkpoint)
    before = store.path_for(document["document_id"]).read_bytes()
    changed = copy.deepcopy(document)
    changed["title"] += " 개정"
    with pytest.raises(ValueError, match="hash|source"):
        store.load_or_create(changed)
    assert store.path_for(document["document_id"]).read_bytes() == before


@pytest.mark.parametrize("module,factory", [(naver_editor, naver_document), (tistory_editor, tistory_document)])
def test_corrupt_checkpoint_is_preserved_not_reset(tmp_path, module, factory) -> None:
    document = factory(tmp_path) if module is tistory_editor else factory()
    store = module.CheckpointStore(tmp_path)
    path = store.path_for(document["document_id"])
    path.write_text('{"publish_state":', encoding="utf-8")
    with pytest.raises(ValueError):
        store.load_or_create(document)
    assert path.read_text() == '{"publish_state":'


def test_pending_naver_insert_is_reconciled_before_retry(tmp_path) -> None:
    document = naver_document()
    store = naver_editor.CheckpointStore(tmp_path)
    operations = naver_editor.build_operations(document)
    driver = StatefulDriver()
    driver.interrupt_after = operations[1]["operation_id"]
    with pytest.raises(naver_editor.StaleElementReference):
        naver_editor.EditorAutomation(store).apply(document, driver)
    # The insertion happened, but its postcondition was temporarily unavailable.
    driver.interrupt_after = None
    driver.unreadable = False
    naver_editor.EditorAutomation(store).apply(document, driver)
    assert driver.calls.count(operations[1]["operation_id"]) == 1


class StatefulDriver:
    def __init__(self):
        self.calls = []
        self.applied = set()
        self.interrupt_after = None
        self.unreadable = False

    def execute(self, operation):
        identifier = operation["operation_id"]
        self.calls.append(identifier)
        self.applied.add(identifier)
        if identifier == self.interrupt_after:
            self.unreadable = True
            raise naver_editor.StaleElementReference("detached after inserting")

    def verify(self, operation):
        if self.unreadable:
            raise naver_editor.StaleElementReference("render still in progress")
        return operation["operation_id"] in self.applied

    def guide(self, operation):
        self.execute(operation)
        return True

    def capture_diagnostic(self, _):
        return ""


def test_completed_but_user_changed_content_is_not_overwritten(tmp_path) -> None:
    document = naver_document()
    driver = StatefulDriver()
    store = naver_editor.CheckpointStore(tmp_path)
    naver_editor.EditorAutomation(store).apply(document, driver)
    driver.applied.remove(naver_editor.build_operations(document)[0]["operation_id"])
    calls = driver.calls[:]
    with pytest.raises((ValueError, naver_editor.EditorUIChanged), match="changed|reconcile"):
        naver_editor.EditorAutomation(store).apply(document, driver)
    assert driver.calls == calls


@pytest.mark.parametrize("module,factory", [(naver_editor, naver_document), (tistory_editor, tistory_document)])
def test_schedule_tokens_normalize_absolute_time_and_bind_target(tmp_path, module, factory) -> None:
    document = factory(tmp_path) if module is tistory_editor else factory()
    target = "https://example.tistory.com/manage/post/123" if module is tistory_editor else "https://blog.naver.com/PostWriteForm.naver?blogId=example&logNo=123"
    options = {"action": "schedule", "target_url": target}
    instant = (datetime.now(timezone.utc) + timedelta(days=2)).replace(second=0, microsecond=0)
    local = instant.astimezone(timezone(timedelta(hours=9))).isoformat()
    utc = module.approval_preview(document, scheduled_at=instant.isoformat(), **options)
    korea = module.approval_preview(document, scheduled_at=local, **options)
    assert utc["approval_token"] == korea["approval_token"]
    assert utc["scheduled_at_local"] == local
    options["target_url"] = target.replace("example", "different")
    other = module.approval_preview(document, scheduled_at=instant.isoformat(), **options)
    assert other["approval_token"] != utc["approval_token"]


def test_checkpoint_keeps_only_hashes_for_remote_save(tmp_path) -> None:
    document = naver_document()
    driver = StatefulDriver()
    store = naver_editor.CheckpointStore(tmp_path)
    checkpoint = naver_editor.EditorAutomation(store).apply(document, driver)
    assert checkpoint["save_state"] == "acknowledged"
    assert checkpoint["saved_source_hash"] == naver_editor.document_hash(document)
    saved = json.loads(store.path_for(document["document_id"]).read_text())
    assert document["title"] not in json.dumps(saved, ensure_ascii=False)


def test_changed_naver_attachment_invalidates_existing_approval(tmp_path) -> None:
    document = naver_document()
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"first-file")
    document["blocks"].append({"id": "photo", "type": "photo", "path": str(photo)})
    before = naver_editor.approval_preview(document, action="publish")["approval_token"]
    photo.write_bytes(b"different-file")
    assert naver_editor.approval_preview(document, action="publish")["approval_token"] != before


@pytest.mark.parametrize("field", ["path", "paths", "replace_path"])
def test_text_block_cannot_introduce_attachment_reads(tmp_path, monkeypatch, field):
    document = naver_document()
    file = tmp_path / "unrelated.txt"
    file.write_text("unrelated local content")
    document["blocks"][0][field] = [str(file)] if field == "paths" else str(file)
    monkeypatch.setattr(naver_document_module.os, "open", lambda *a, **k: pytest.fail("unexpected file read"))
    with pytest.raises(ValueError, match="unsupported attachment fields"):
        naver_document_module.document_hash(document)


@pytest.mark.parametrize("replacement", ["oversized", "fifo"])
def test_attachment_hash_rechecks_opened_file_after_validation(tmp_path, monkeypatch, replacement):
    if replacement == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("FIFO requires POSIX")
    document = naver_document()
    file = tmp_path / "photo.jpg"
    file.write_bytes(b"original")
    document["blocks"].append({"id": "photo", "type": "photo", "path": str(file)})
    monkeypatch.setattr(naver_document_module, "MAX_IMAGE_BYTES", 16)
    original_open = os.open

    def replace_before_open(path, flags):
        if replacement == "fifo":
            file.unlink()
            os.mkfifo(file)
        else:
            file.write_bytes(b"x" * 17)
        return original_open(path, flags)

    monkeypatch.setattr(naver_document_module.os, "open", replace_before_open)
    with pytest.raises(ValueError, match="bounded regular file"):
        naver_document_module.document_hash(document)


@pytest.mark.parametrize("platform", ["naver", "tistory"])
@pytest.mark.parametrize("changed", [False, True])
def test_login_wait_preserves_the_approved_attachment_bytes(tmp_path, monkeypatch, platform, changed):
    module = naver_editor if platform == "naver" else tistory_editor
    if platform == "naver":
        document = naver_document()
        source = tmp_path / "photo.jpg"
        source.write_bytes(b"approved")
        document["blocks"].append({"id": "photo", "type": "photo", "path": str(source)})
        editor_url = "https://blog.naver.com/PostWriteForm.naver"
        extra = {}
        token = module._draft_preview(document, target_url=editor_url)["approval_token"]
        browser_name, driver_name, automation = "NaverBrowserSession", "PlaywrightNaverDriver", module.EditorAutomation
    else:
        document = tistory_document(tmp_path)
        document["media"][0]["privacy"] = {"mode": "none", "strip_metadata": False}
        source = Path(document["media"][0]["path"])
        editor_url = "https://fixture.tistory.com/manage/newpost"
        preflight = module.build_privacy_preflight(document)
        extra = {"preflight": preflight}
        token = module.draft_preview(document, privacy_preflight=preflight, target_url=editor_url)["approval_token"]
        browser_name, driver_name, automation = "TistoryBrowserSession", "PlaywrightTistoryDriver", module.TistoryEditorAutomation
    document = module.validate_document(document)
    calls = []

    class Browser:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def wait_for_editor(self):
            if changed:
                source.write_bytes(b"unapproved bytes during login")
            return SimpleNamespace(url=editor_url)

    def apply(self, value, driver, **kwargs):
        calls.append("account-write")
        return self.store.load_or_create(value)

    monkeypatch.setattr(module, browser_name, Browser)
    monkeypatch.setattr(module, driver_name, lambda *a, **k: None)
    monkeypatch.setattr(automation, "apply", apply)
    kwargs = dict(data_dir=tmp_path / "data", editor_url=editor_url, close_after=True, approval_token=token, **extra)
    if changed:
        with pytest.raises(module.ApprovalRequired, match="source changed"):
            module._compose(document, **kwargs)
        assert calls == []
    else:
        module._compose(document, **kwargs)
        assert calls == ["account-write"]


def test_tistory_rejects_derivative_changed_during_login(tmp_path, monkeypatch):
    document = tistory_document(tmp_path)
    document["media"][0]["privacy"] = {"mode": "none", "strip_metadata": False}
    preflight = tistory_editor.build_privacy_preflight(document)
    editor_url = "https://fixture.tistory.com/manage/newpost"
    token = tistory_editor.draft_preview(document, privacy_preflight=preflight, target_url=editor_url)["approval_token"]
    prepared = tmp_path / "prepared.jpg"
    prepared.write_bytes(b"approved derivative")
    monkeypatch.setattr(tistory_editor, "prepare_media", lambda *a, **k: {"hero": prepared})

    class Browser:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def wait_for_editor(self):
            prepared.write_bytes(b"changed derivative")
            return SimpleNamespace(url=editor_url)

    monkeypatch.setattr(tistory_editor, "TistoryBrowserSession", Browser)
    monkeypatch.setattr(tistory_editor, "PlaywrightTistoryDriver", lambda *a, **k: pytest.fail("must stop before account write"))
    with pytest.raises(tistory_editor.ApprovalRequired, match="prepared media changed"):
        tistory_editor._compose(document, preflight=preflight, approval_token=token,
                                data_dir=tmp_path / "data", editor_url=editor_url, close_after=True)


def test_naver_draft_plan_never_contains_publication_settings_or_submit_controls() -> None:
    features = {item["feature_id"] for item in naver_editor.build_operations(naver_document())}
    assert not features & {"publish", "schedule-publish", "publish-dialog", "visibility", "category"}


def _saved_checkpoint_and_reader():
    from editor_safety import CHECKPOINT_DEFAULTS

    url = "https://fixture.tistory.com/manage/post/42"
    checkpoint = {**CHECKPOINT_DEFAULTS, "document_id": "sample", "publish_state": "not-attempted",
                  "draft_url": url, "source_hash": "source", "saved_source_hash": "source",
                  "save_state": "acknowledged", "saved_surface_hash": "content",
                  "surface_version": 2, "saved_session_id": "editor-session"}
    driver = SimpleNamespace(page=SimpleNamespace(url=url), surface_version=2,
                             session_id="editor-session", snapshot_hash=lambda: "content")
    return checkpoint, driver


@pytest.mark.parametrize("change", [
    {"draft_url": "https://other.tistory.com/manage/post/42"},
    {"draft_url": "https://fixture.tistory.com/manage/post/43"},
    {"surface_version": None},
    {"publish_state": "unknown"},
    {"pending_operation_id": "unfinished-save"},
    {"save_state": "saving"},
    {"saved_source_hash": "different-source"},
    {"saved_surface_hash": "different-content"},
])
def test_publication_requires_exact_identity_and_completed_compatible_save(change):
    from editor_safety import prepare_publication

    checkpoint, driver = _saved_checkpoint_and_reader()
    checkpoint.update(change)
    with pytest.raises(ValueError):
        prepare_publication(driver, {"media": []}, checkpoint, {})


def test_publication_accepts_current_session_save_acknowledgement():
    from editor_safety import prepare_publication

    checkpoint, driver = _saved_checkpoint_and_reader()
    prepare_publication(driver, {"media": []}, checkpoint, {})
    assert driver._publication["identity"] == ("tistory:fixture.tistory.com", "42")

    checkpoint["save_state"] = "readback-confirmed"  # legacy checkpoints remain publishable
    prepare_publication(driver, {"media": []}, checkpoint, {})

    driver.snapshot_hash = lambda: "changed-content"
    with pytest.raises(ValueError, match="fingerprint"):
        prepare_publication(driver, {"media": []}, checkpoint, {})


@pytest.mark.parametrize("module", [naver_editor, tistory_editor])
def test_verify_draft_command_is_removed(module):
    parser = module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["verify-draft", "document.json"])


@pytest.mark.parametrize("module", [naver_editor, tistory_editor])
@pytest.mark.parametrize("supplied_token", [None, "stale-token"])
def test_compose_request_continues_without_second_approval(tmp_path, monkeypatch, module, supplied_token):
    document = naver_document() if module is naver_editor else tistory_document(tmp_path, with_media=False)
    path = tmp_path / "document.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    calls = []
    monkeypatch.setattr(module, "_compose", lambda *args, **kwargs: calls.append(kwargs) or {"save_state": "acknowledged"})
    args = ["--data-dir", str(tmp_path / "data"), "compose", str(path)]
    if module is tistory_editor:
        args += ["--editor-url", "https://fixture.tistory.com/manage/newpost"]
    if supplied_token is not None:
        args += ["--approval-token", supplied_token]
    assert module.main(args) == (0 if supplied_token is None else 4)
    assert len(calls) == (1 if supplied_token is None else 0)
