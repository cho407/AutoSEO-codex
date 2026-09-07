from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/autoseo/scripts"))

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


def test_naver_draft_plan_never_contains_publication_settings_or_submit_controls() -> None:
    features = {item["feature_id"] for item in naver_editor.build_operations(naver_document())}
    assert not features & {"publish", "schedule-publish", "publish-dialog", "visibility", "category"}
