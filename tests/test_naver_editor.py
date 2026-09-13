from __future__ import annotations

import json
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

import naver_document  # noqa: E402
import naver_editor  # noqa: E402


def _document() -> dict:
    return {
        "schema_version": 1,
        "document_id": "draft-001",
        "title": "검색 사용자를 위한 정확한 안내",
        "background": {"type": "none"},
        "blocks": [
            {
                "id": "intro",
                "type": "paragraph",
                "text": "핵심 답변과 근거를 먼저 설명합니다.",
                "style": {"bold": True, "alignment": "left"},
            },
            {"id": "evidence", "type": "heading", "level": 2, "text": "근거"},
            {"id": "rule", "type": "divider"},
        ],
        "tags": ["검색", "콘텐츠"],
        "publish_settings": {
            "mode": "draft",
            "category": "정보",
            "visibility": "public",
            "search_allowed": True,
            "comments_allowed": True,
            "sympathy_allowed": True,
            "ccl": "none",
            "share_allowed": True,
            "scheduled_at": None,
        },
    }


class MockEditorDriver:
    def __init__(
        self,
        *,
        stale_once: str | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.attempts: list[str] = []
        self.stale_once = stale_once
        self.fail_on = fail_on
        self.publish_clicks = 0

    def execute(self, operation: dict) -> None:
        operation_id = operation["operation_id"]
        self.attempts.append(operation_id)
        if self.stale_once == operation_id:
            self.stale_once = None
            raise naver_editor.StaleElementReference("old locator")
        if self.fail_on == operation_id:
            raise naver_editor.EditorUIChanged("mock UI changed")
        self.calls.append(operation_id)

    @staticmethod
    def verify(_: dict) -> bool:
        return True

    @staticmethod
    def guide(_: dict) -> bool:
        return True

    @staticmethod
    def capture_diagnostic(_: str) -> str:
        return "diagnostics/failure.png"

    def apply_publish_settings(self, _: dict) -> None:
        pass

    def click_publish(self, _: str) -> None:
        self.publish_clicks += 1

    @staticmethod
    def verify_publish(_: str) -> dict | None:
        return {"url": "https://blog.naver.com/example/1"}


class FakeLocator:
    def __init__(self, count: int) -> None:
        self._count = count
        self.clicks = 0

    def count(self) -> int:
        return self._count

    def click(self) -> None:
        self.clicks += 1


class FakeKeyboard:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def press(self, value: str) -> None:
        self.calls.append(f"shortcut:{value}")


class FakePage:
    def __init__(
        self,
        *,
        role_count: int = 0,
        label_count: int = 0,
        fallback_count: int = 0,
    ) -> None:
        self.role_count = role_count
        self.label_count = label_count
        self.fallback_count = fallback_count
        self.calls: list[str] = []
        self.keyboard = FakeKeyboard(self.calls)

    def get_by_role(self, role: str, *, name: str, exact: bool) -> FakeLocator:
        self.calls.append(f"role:{role}:{name}:{exact}")
        return FakeLocator(self.role_count)

    def get_by_text(self, value: str, *, exact: bool) -> FakeLocator:
        self.calls.append(f"label:{value}:{exact}")
        return FakeLocator(self.label_count)

    def locator(self, value: str) -> FakeLocator:
        self.calls.append(f"fallback:{value}")
        return FakeLocator(self.fallback_count)


def test_feature_catalog_is_complete_and_has_no_silent_omissions() -> None:
    catalog = naver_editor.FeatureCatalog.load()
    expected = {
        "title",
        "title-background",
        "paragraph",
        "heading",
        "quote",
        "divider",
        "font-family",
        "font-size",
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "text-color",
        "alignment",
        "line-spacing",
        "superscript",
        "subscript",
        "special-character",
        "link",
        "spellcheck",
        "photo",
        "photo-replace",
        "photo-properties",
        "photo-editor",
        "group-photo",
        "sticker",
        "video",
        "place",
        "multi-attach",
        "external-link",
        "file",
        "schedule-component",
        "table",
        "equation",
        "template",
        "library",
        "talktalk",
        "tags",
        "category",
        "visibility",
        "search-allowed",
        "comments-allowed",
        "sympathy-allowed",
        "ccl",
        "share-allowed",
        "draft-save",
        "publish",
        "schedule-publish",
    }
    assert set(catalog.features) == expected | {"publish-dialog", "schedule-option"}
    assert {item["status"] for item in catalog.features.values()} <= {
        "automatic",
        "guided",
        "unavailable",
    }
    assert all(
        item["handler"] in naver_editor.AUTOMATIC_HANDLERS
        for item in catalog.features.values()
        if item["status"] == "automatic"
    )


def test_document_validation_and_attachment_limits(tmp_path: Path) -> None:
    document = _document()
    assert naver_document.validate_document(document)["document_id"] == "draft-001"

    attachment = tmp_path / "photo.jpg"
    attachment.write_bytes(b"x" * 11)
    document["blocks"].append(
        {"id": "photo", "type": "photo", "path": str(attachment)}
    )
    with pytest.raises(ValueError, match="attachment limit"):
        naver_document.validate_document(document, max_attachment_bytes=10)


def test_explicit_multi_uploads_and_links_compile_without_guided_selection(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    document = _document()
    document["blocks"][0]["links"] = [
        {"text": "핵심 답변", "url": "https://example.com/evidence"}
    ]
    document["blocks"].append(
        {
            "id": "gallery",
            "type": "group-photo",
            "paths": [str(first), str(second)],
        }
    )

    operations = naver_document.build_operations(document)
    link = next(item for item in operations if item["feature_id"] == "link")
    gallery = next(
        item for item in operations if item["feature_id"] == "group-photo"
    )

    assert link["guided"] is False
    assert gallery["guided"] is False
    assert gallery["payload"]["paths"] == [str(first), str(second)]


def test_special_characters_are_direct_and_spellcheck_is_guided() -> None:
    document = _document()
    document["blocks"].append(
        {"id": "symbol", "type": "special-character", "text": "※"}
    )
    document["editor_options"] = {"spellcheck": True}

    operations = naver_document.build_operations(document)
    symbol = next(
        item for item in operations if item["feature_id"] == "special-character"
    )
    spellcheck = next(
        item for item in operations if item["feature_id"] == "spellcheck"
    )

    assert symbol["guided"] is False
    assert symbol["payload"]["text"] == "※"
    assert spellcheck["guided"] is True


def test_schedule_requires_future_timezone_aware_value() -> None:
    now = datetime(2026, 8, 28, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    valid = (now + timedelta(hours=2)).isoformat()
    assert naver_document.validate_schedule(valid, now=now) == valid
    with pytest.raises(ValueError, match="timezone"):
        naver_document.validate_schedule("2026-08-28T11:00:00", now=now)
    with pytest.raises(ValueError, match="future"):
        naver_document.validate_schedule((now - timedelta(minutes=1)).isoformat(), now=now)


def test_stale_element_is_resolved_once_and_operation_is_not_duplicated(
    tmp_path: Path,
) -> None:
    document = _document()
    operations = naver_document.build_operations(document)
    target = operations[0]["operation_id"]
    driver = MockEditorDriver(stale_once=target)
    driver.verify = lambda operation: operation["operation_id"] in driver.calls
    automation = naver_editor.EditorAutomation(
        naver_editor.CheckpointStore(tmp_path)
    )

    result = automation.apply(document, driver)

    assert driver.attempts.count(target) == 2
    assert driver.calls.count(target) == 1
    assert target in result["completed_operation_ids"]


def test_interrupted_run_resumes_without_reinserting_completed_blocks(
    tmp_path: Path,
) -> None:
    document = _document()
    operations = naver_document.build_operations(document)
    first_id = operations[0]["operation_id"]
    second_id = operations[1]["operation_id"]
    store = naver_editor.CheckpointStore(tmp_path)
    first_driver = MockEditorDriver(fail_on=second_id)

    with pytest.raises(naver_editor.EditorUIChanged):
        naver_editor.EditorAutomation(store).apply(document, first_driver)

    checkpoint_text = store.path_for("draft-001").read_text(encoding="utf-8")
    assert first_id in checkpoint_text
    assert document["title"] not in checkpoint_text
    assert document["blocks"][0]["text"] not in checkpoint_text

    second_driver = MockEditorDriver()
    result = naver_editor.EditorAutomation(store).apply(document, second_driver)
    assert first_id not in second_driver.calls
    assert len(result["completed_operation_ids"]) == len(operations)


def test_ui_change_stops_and_records_diagnostic_without_guessing(tmp_path: Path) -> None:
    document = _document()
    operation = naver_document.build_operations(document)[0]
    driver = MockEditorDriver(fail_on=operation["operation_id"])
    store = naver_editor.CheckpointStore(tmp_path)

    with pytest.raises(naver_editor.EditorUIChanged):
        naver_editor.EditorAutomation(store).apply(document, driver)

    checkpoint = json.loads(store.path_for("draft-001").read_text(encoding="utf-8"))
    assert checkpoint["diagnostic_files"] == ["diagnostics/failure.png"]
    assert checkpoint["completed_operation_ids"] == []


def test_profile_and_checkpoint_permissions_are_user_only(tmp_path: Path) -> None:
    profile = naver_editor.profile_directory(tmp_path)
    store = naver_editor.CheckpointStore(tmp_path)
    store.load_or_create(_document())

    assert stat.S_IMODE(profile.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path_for("draft-001").stat().st_mode) == 0o600


def test_publish_requires_exact_approval_and_is_disabled_in_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document()
    store = naver_editor.CheckpointStore(tmp_path)
    checkpoint = store.load_or_create(document)
    driver = MockEditorDriver()
    preview = naver_editor.approval_preview(document, action="publish")

    with pytest.raises(naver_editor.ApprovalRequired):
        naver_editor.publish_or_schedule(
            document, checkpoint, driver, action="publish", approval_token="wrong"
        )
    assert driver.publish_clicks == 0

    monkeypatch.setenv("AUTOSEO_TESTING", "1")
    with pytest.raises(RuntimeError, match="disabled"):
        naver_editor.publish_or_schedule(
            document,
            checkpoint,
            driver,
            action="publish",
            approval_token=preview["approval_token"],
        )
    assert driver.publish_clicks == 0


def test_draft_approval_token_is_bound_to_exact_document() -> None:
    first = naver_editor._draft_preview(_document())
    changed = _document()
    changed["title"] = "다른 제목"
    second = naver_editor._draft_preview(
        naver_document.validate_document(changed)
    )

    assert first["approval_required"] is True
    assert first["approval_token"] != second["approval_token"]


def test_locator_order_stops_on_ambiguity_and_prefers_shortcut_over_dom() -> None:
    catalog = naver_editor.FeatureCatalog.load()
    ambiguous_page = FakePage(role_count=2, label_count=1, fallback_count=1)
    with pytest.raises(naver_editor.AmbiguousElement):
        naver_editor.LocatorResolver(ambiguous_page, catalog).locate("bold")
    assert len(ambiguous_page.calls) == 1
    assert ambiguous_page.calls[0].startswith("role:")

    shortcut_page = FakePage(role_count=0, label_count=0, fallback_count=1)
    shortcut_page.evaluate = lambda _: True  # Positively identified editor focus.
    strategy = naver_editor.LocatorResolver(shortcut_page, catalog).click("bold")
    assert strategy == "shortcut"
    assert shortcut_page.calls[-1] == "shortcut:Meta+B"
    assert not any(call.startswith("fallback:") for call in shortcut_page.calls)


def test_doctor_does_not_create_profile_or_data_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "doctor-data"
    result = naver_editor.main(["--data-dir", str(data_dir), "doctor"])
    payload = json.loads(capsys.readouterr().out)

    assert result in {0, 3}
    assert payload["profile_exists"] is False
    assert not data_dir.exists()


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:9222",
        "http://example.com:9222",
        "http://user:secret@127.0.0.1:9222",
        "http://127.0.0.1:9222/json",
        "http://127.0.0.1",
    ],
)
def test_cdp_endpoint_rejects_non_loopback_or_credentialed_values(value: str) -> None:
    with pytest.raises(ValueError, match="CDP endpoint"):
        naver_editor._validate_cdp_endpoint(value)


def test_cdp_endpoint_accepts_loopback_http_port() -> None:
    assert (
        naver_editor._validate_cdp_endpoint("http://127.0.0.1:9222/")
        == "http://127.0.0.1:9222"
    )


@pytest.mark.parametrize(
    ("target_url", "open_url", "matches"),
    [
        (naver_editor.DEFAULT_EDITOR_URL, "https://blog.naver.com/example/postwrite", True),
        (naver_editor.DEFAULT_EDITOR_URL, "http://blog.naver.com/example/postwrite", False),
        ("https://blog.naver.com/example/postwrite?logNo=1",
         "https://blog.naver.com/example/postwrite?logNo=1", True),
        ("https://blog.naver.com/example/postwrite?logNo=1",
         "https://blog.naver.com/example/postwrite?logNo=2", False),
        ("https://blog.naver.com/example/postwrite",
         "https://blog.naver.com/another/postwrite", False),
    ],
)
def test_cdp_attachment_keeps_explicit_draft_target(target_url, open_url, matches) -> None:
    page = SimpleNamespace(url=open_url, is_closed=lambda: False)
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[page])])
    found = naver_editor.NaverBrowserSession._editor_page_candidates(browser, target_url)
    assert found == ([page] if matches else [])


def test_attached_cdp_session_disconnects_without_closing_browser_context() -> None:
    class FakeContext:
        closed = False

        def close(self) -> None:
            self.closed = True

    class FakePlaywright:
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    session = object.__new__(naver_editor.NaverBrowserSession)
    session.attached = True
    session.context = FakeContext()
    session.playwright = FakePlaywright()

    naver_editor.NaverBrowserSession.__exit__.__wrapped__(session)

    assert session.context.closed is False
    assert session.playwright.stopped is True


def test_document_schema_and_checkpoint_ignore_rules_exist() -> None:
    schema = json.loads(
        (PLUGIN / "schema" / "naver-document.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["schema_version"]["const"] == 1
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for value in (
        "naver-editor-profile/",
        "naver-editor-checkpoints/",
        "naver-editor-diagnostics/",
        "naver-editor-compatibility.json",
    ):
        assert value in ignore

    example = json.loads(
        (PLUGIN / "examples" / "naver-document-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert naver_document.validate_document(example)["schema_version"] == 1


def test_human_compatibility_matrix_matches_machine_catalog() -> None:
    catalog = naver_editor.FeatureCatalog.load()
    text = (
        PLUGIN
        / "skills"
        / "autoseo-naver-editor"
        / "references"
        / "feature-compatibility.md"
    ).read_text(encoding="utf-8")
    automatic = text.split("## Automatic", 1)[1].split("## Guided", 1)[0]
    guided = text.split("## Guided", 1)[1].split("## Unavailable", 1)[0]
    pattern = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)

    assert set(pattern.findall(automatic)) == {
        identifier
        for identifier, feature in catalog.features.items()
        if feature["status"] == "automatic"
    }
    assert set(pattern.findall(guided)) == {
        identifier
        for identifier, feature in catalog.features.items()
        if feature["status"] == "guided"
    }
