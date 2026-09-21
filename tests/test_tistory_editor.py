from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

import tistory_document  # noqa: E402
import tistory_editor  # noqa: E402


def _document(tmp_path: Path, *, with_media: bool = True) -> dict:
    media = []
    blocks: list[dict] = [
        {"id": "intro", "type": "paragraph", "text": "핵심 답변을 먼저 제공합니다."},
        {"id": "evidence", "type": "heading", "level": 2, "text": "확인 근거"},
        {
            "id": "list",
            "type": "unordered-list",
            "items": ["첫 번째 근거", "두 번째 근거"],
        },
    ]
    if with_media:
        image = tmp_path / "people.jpg"
        image.write_bytes(b"image-bytes")
        media.append(
            {
                "id": "hero",
                "path": str(image),
                "alt": "행사장에서 설명하는 발표자와 참석자",
                "caption": "현장 설명 모습",
            }
        )
        blocks.append({"id": "hero-block", "type": "image", "media_id": "hero"})
    return {
        "schema_version": 1,
        "document_id": "tistory-draft-001",
        "title": "검색 사용자를 위한 정확한 안내",
        "format": "auto",
        "blocks": blocks,
        "media": media,
        "tags": ["검색", "콘텐츠"],
        "publish_settings": {
            "mode": "draft",
            "category": "정보",
            "visibility": "public",
            "comments_allowed": True,
            "scheduled_at": None,
        },
    }


class MockTistoryDriver:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.uploads: list[str] = []
        self.calls: list[str] = []
        self.publish_clicks = 0

    def upload_media(self, media: dict, path: Path, *, document_format: str) -> str:
        self.uploads.append(media["id"])
        return f"https://blog.kakaocdn.net/dn/{media['id']}/{path.name}"

    def execute(self, operation: dict) -> None:
        operation_id = operation["operation_id"]
        if self.fail_on == operation_id:
            raise tistory_editor.EditorUIChanged("mock changed")
        self.calls.append(operation_id)

    @staticmethod
    def verify(_: dict) -> bool:
        return True

    @staticmethod
    def capture_diagnostic(_: str) -> str:
        return "tistory-editor-diagnostics/failure.png"

    @staticmethod
    def apply_publish_settings(_: dict) -> None:
        return None

    def click_publish(self, _: str) -> None:
        self.publish_clicks += 1

    @staticmethod
    def verify_publish(_: str) -> dict:
        return {"url": "https://example.tistory.com/42"}


def test_tistory_document_defaults_to_markdown_and_background_people_privacy(
    tmp_path: Path,
) -> None:
    document = tistory_document.validate_document(_document(tmp_path))

    assert document["format"] == "markdown"
    assert document["media"][0]["privacy"] == {
        "mode": "background-people",
        "keep_face_ids": [],
        "mosaic_face_ids": [],
        "main_face_id": None,
        "regions": [],
        "padding": 0.18,
        "block_size": 14,
        "strip_metadata": True,
    }


def test_markdown_and_html_renderers_use_uploaded_media_urls(tmp_path: Path) -> None:
    document = _document(tmp_path)
    media_urls = {"hero": "https://blog.kakaocdn.net/dn/hero/photo.jpg"}

    markdown = tistory_document.render_document(
        document, output_format="markdown", media_urls=media_urls
    )
    html = tistory_document.render_document(
        document, output_format="html", media_urls=media_urls
    )

    assert "## 확인 근거" in markdown
    assert "- 첫 번째 근거" in markdown
    assert "![행사장에서 설명하는 발표자와 참석자](https://blog.kakaocdn.net" in markdown
    assert "*현장 설명 모습*" in markdown
    assert "<h2>확인 근거</h2>" in html
    assert '<img src="https://blog.kakaocdn.net/dn/hero/photo.jpg"' in html
    assert "<figcaption>현장 설명 모습</figcaption>" in html


def test_renderers_escape_user_text_in_their_target_format(tmp_path: Path) -> None:
    document = _document(tmp_path, with_media=False)
    document["blocks"][0]["text"] = "<script>alert(1)</script> & 안내"

    html = tistory_document.render_document(document, output_format="html")
    markdown = tistory_document.render_document(document, output_format="markdown")

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; 안내" in html
    assert "<script>" not in markdown


def test_document_rejects_unknown_media_and_invalid_schedule(tmp_path: Path) -> None:
    document = _document(tmp_path, with_media=False)
    document["blocks"].append(
        {"id": "missing-image", "type": "image", "media_id": "missing"}
    )
    with pytest.raises(ValueError, match="unknown media"):
        tistory_document.validate_document(document)

    document = _document(tmp_path, with_media=False)
    document["publish_settings"]["mode"] = "schedule"
    document["publish_settings"]["scheduled_at"] = "2026-08-31T10:00:00"
    with pytest.raises(ValueError, match="timezone"):
        tistory_document.validate_document(document)


def test_editor_uploads_each_asset_once_and_resume_skips_completed_work(
    tmp_path: Path,
) -> None:
    document = tistory_document.validate_document(_document(tmp_path))
    prepared = {"hero": Path(document["media"][0]["path"])}
    store = tistory_editor.CheckpointStore(tmp_path)
    first_operations = tistory_document.build_operations(
        document,
        {"hero": "https://blog.kakaocdn.net/dn/hero/people.jpg"},
    )
    fail_on = first_operations[2]["operation_id"]
    first = MockTistoryDriver(fail_on=fail_on)

    with pytest.raises(tistory_editor.EditorUIChanged):
        tistory_editor.TistoryEditorAutomation(store).apply(
            document, first, prepared_media=prepared
        )

    second = MockTistoryDriver()
    result = tistory_editor.TistoryEditorAutomation(store).apply(
        document, second, prepared_media=prepared
    )

    assert first.uploads == ["hero"]
    assert second.uploads == []
    assert result["media_states"] == {"hero": "uploaded"}
    checkpoint_text = store.path_for(document["document_id"]).read_text(encoding="utf-8")
    assert document["title"] not in checkpoint_text
    assert document["blocks"][0]["text"] not in checkpoint_text
    assert document["media"][0]["path"] not in checkpoint_text


def test_resume_rechecks_page_state_before_skipping_checkpointed_operations(
    tmp_path: Path,
) -> None:
    document = tistory_document.validate_document(
        _document(tmp_path, with_media=False)
    )
    operations = tistory_document.build_operations(document, {})
    store = tistory_editor.CheckpointStore(tmp_path)
    checkpoint = store.load_or_create(document)
    checkpoint["completed_operation_ids"] = [operations[0]["operation_id"]]
    store.save(checkpoint)

    class FreshPageDriver(MockTistoryDriver):
        def verify(self, operation: dict) -> bool:
            return operation["operation_id"] in self.calls

    driver = FreshPageDriver()
    with pytest.raises(tistory_editor.EditorUIChanged, match="changed"):
        tistory_editor.TistoryEditorAutomation(store).apply(
            document, driver, prepared_media={}
        )
    assert driver.calls == []


def test_document_rejects_a_main_face_that_is_also_mosaicked(tmp_path: Path) -> None:
    document = _document(tmp_path)
    document["media"][0]["privacy"] = {
        "main_face_id": "face-1",
        "mosaic_face_ids": ["face-1"],
    }

    with pytest.raises(ValueError, match="main face cannot also be mosaicked"):
        tistory_document.validate_document(document)


def test_unclear_upload_is_never_retried_automatically(tmp_path: Path) -> None:
    document = tistory_document.validate_document(_document(tmp_path))
    prepared = {"hero": Path(document["media"][0]["path"])}
    store = tistory_editor.CheckpointStore(tmp_path)

    class FailingUploadDriver(MockTistoryDriver):
        def upload_media(self, media: dict, path: Path, *, document_format: str) -> str:
            self.uploads.append(media["id"])
            raise tistory_editor.UploadResultUnknown("upload result unclear")

    with pytest.raises(tistory_editor.UploadResultUnknown):
        tistory_editor.TistoryEditorAutomation(store).apply(
            document, FailingUploadDriver(), prepared_media=prepared
        )
    with pytest.raises(tistory_editor.UploadResultUnknown, match="reconcile"):
        tistory_editor.TistoryEditorAutomation(store).apply(
            document, MockTistoryDriver(), prepared_media=prepared
        )


def test_draft_preview_binds_document_and_image_privacy_plan(tmp_path: Path) -> None:
    document = tistory_document.validate_document(_document(tmp_path))
    plan = {
        "hero": {
            "source_sha256": "a" * 64,
            "summary": {
                "detected_face_count": 3,
                "main_face_id": "face-2",
                "mosaic_face_count": 2,
                "review_required": False,
            },
        }
    }

    first = tistory_editor.draft_preview(document, privacy_preflight=plan)
    changed = json.loads(json.dumps(plan))
    changed["hero"]["summary"]["mosaic_face_count"] = 3
    second = tistory_editor.draft_preview(document, privacy_preflight=changed)

    assert first["approval_required"] is True
    assert first["privacy"]["hero"]["mosaic_face_count"] == 2
    assert first["approval_token"] != second["approval_token"]


def test_publish_and_schedule_require_exact_per_post_approval(tmp_path: Path) -> None:
    document = tistory_document.validate_document(_document(tmp_path, with_media=False))
    store = tistory_editor.CheckpointStore(tmp_path)
    checkpoint = store.load_or_create(document)
    operations = tistory_document.build_operations(document, {})
    checkpoint["completed_operation_ids"] = [item["operation_id"] for item in operations]
    store.save(checkpoint)
    driver = MockTistoryDriver()
    preview = tistory_editor.approval_preview(document, action="publish")

    with pytest.raises(tistory_editor.ApprovalRequired):
        tistory_editor.publish_or_schedule(
            document,
            checkpoint,
            driver,
            action="publish",
            approval_token="wrong",
            store=store,
        )
    assert driver.publish_clicks == 0

    old_testing = os.environ.get("AUTOSEO_TESTING")
    os.environ["AUTOSEO_TESTING"] = "1"
    try:
        with pytest.raises(RuntimeError, match="disabled in automated tests"):
            tistory_editor.publish_or_schedule(
                document,
                checkpoint,
                driver,
                action="publish",
                approval_token=preview["approval_token"],
                store=store,
            )
    finally:
        if old_testing is None:
            os.environ.pop("AUTOSEO_TESTING", None)
        else:
            os.environ["AUTOSEO_TESTING"] = old_testing
    assert driver.publish_clicks == 0


def test_schedule_requires_a_future_timezone_aware_time(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    document = _document(tmp_path, with_media=False)
    document["publish_settings"]["mode"] = "schedule"
    document["publish_settings"]["scheduled_at"] = (now + timedelta(hours=1)).isoformat()
    assert tistory_document.validate_document(document)["publish_settings"][
        "scheduled_at"
    ]


def test_tistory_hosts_and_editor_paths_are_strictly_allowlisted() -> None:
    assert (
        tistory_editor.validate_editor_url(
            "https://example.tistory.com/manage/newpost/?type=post"
        )
        == "https://example.tistory.com/manage/newpost/?type=post"
    )
    for value in (
        "http://example.tistory.com/manage/newpost/",
        "https://tistory.com.evil.example/manage/newpost/",
        "https://example.tistory.com/not-an-editor",
        "https://user@example.tistory.com/manage/newpost/",
    ):
        with pytest.raises(ValueError):
            tistory_editor.validate_editor_url(value)


def test_publish_and_schedule_results_require_surface_specific_evidence() -> None:
    assert (
        tistory_editor._validated_action_result(
            "publish", {"url": "https://example.tistory.com/42"}
        )
        == "https://example.tistory.com/42"
    )
    assert (
        tistory_editor._validated_action_result(
            "schedule",
            {
                "url": "https://example.tistory.com/manage/posts/",
                "scheduled": True,
            },
        )
        == "https://example.tistory.com/manage/posts/"
    )
    for action, result in (
        ("publish", {"url": "https://www.tistory.com/"}),
        ("publish", {"url": "https://example.tistory.com/"}),
        ("schedule", {"url": "https://example.tistory.com/manage/posts/"}),
    ):
        assert tistory_editor._validated_action_result(action, result) is None


def test_profile_and_checkpoint_permissions_are_private(tmp_path: Path) -> None:
    profile = tistory_editor.profile_directory(tmp_path)
    store = tistory_editor.CheckpointStore(tmp_path)
    checkpoint = store.load_or_create(
        tistory_document.validate_document(_document(tmp_path, with_media=False))
    )
    store.save(checkpoint)

    assert stat.S_IMODE(profile.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path_for("tistory-draft-001").stat().st_mode) == 0o600


def test_doctor_is_read_only_and_separates_editor_from_privacy_readiness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "autoseo-data"

    result = tistory_editor.main(["--data-dir", str(data_dir), "doctor"])
    payload = json.loads(capsys.readouterr().out)

    assert result in {0, 3}
    assert payload["editor_ready"] == payload["dependencies"]["playwright"]
    assert payload["privacy_ready"] == (
        payload["dependencies"]["PIL"] and payload["dependencies"]["cv2"]
    )
    assert not data_dir.exists()


def test_feature_catalog_has_no_silent_omissions() -> None:
    catalog = tistory_editor.FeatureCatalog.load()
    assert set(catalog.features) == {
        "title",
        "editor-mode",
        "mode-basic",
        "mode-markdown",
        "mode-html",
        "body-source",
        "image-upload",
        "tags",
        "category",
        "visibility",
        "comments-allowed",
        "draft-save",
        "publish-dialog",
        "publish",
        "schedule-option",
        "schedule-publish",
    }
    assert all(
        item["status"] in {"automatic", "guided", "unavailable"}
        for item in catalog.features.values()
    )


def test_schema_and_bundled_example_are_valid() -> None:
    schema = json.loads(
        (PLUGIN / "schema" / "tistory-document.schema.json").read_text(
            encoding="utf-8"
        )
    )
    example = json.loads(
        (PLUGIN / "examples" / "tistory-document-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema["title"] == "TistoryDocument v1"
    assert tistory_document.validate_document(example)["schema_version"] == 1


@pytest.mark.parametrize("output_format", ["markdown", "html"])
def test_export_cli_preserves_requested_format_and_refuses_silent_overwrite(
    tmp_path: Path, output_format: str,
) -> None:
    example = PLUGIN / "examples" / "tistory-document-v1.json"
    source = json.loads(example.read_text(encoding="utf-8"))
    if output_format == "markdown":
        source.update(layout_preset="none", format="markdown")
    document = tmp_path / "document.json"
    document.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / ("article.md" if output_format == "markdown" else "article.html")
    command = [
        sys.executable,
        str(SCRIPTS / "tistory_document.py"),
        "render",
        str(document),
        "--format",
        output_format,
        "--output",
        str(output),
    ]

    first = subprocess.run(command, capture_output=True, text=True, check=False)
    second = subprocess.run(command, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stderr
    content = output.read_text(encoding="utf-8")
    if output_format == "markdown":
        assert "## 확인 근거" in content
    else:
        assert '<h2 style="' in content
        assert "text-align:center" in content
        assert "확인 근거</h2>" in content
    assert second.returncode == 2


def test_real_playwright_driver_composes_the_local_editor_fixture(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        playwright = sync_api.sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
    except Exception as exc:
        pytest.skip(f"local Chromium is unavailable: {type(exc).__name__}")
    try:
        page = browser.new_page()
        fixture = ROOT / "tests" / "fixtures" / "tistory_editor.html"
        page.goto(fixture.as_uri())
        image = tmp_path / "people.jpg"
        image.write_bytes(b"fixture-image")
        document = tistory_document.validate_document(_document(tmp_path))
        driver = tistory_editor.PlaywrightTistoryDriver(
            page,
            catalog=tistory_editor.FeatureCatalog.load(),
            data_dir=tmp_path,
        )

        uploaded = driver.upload_media(
            document["media"][0], image, document_format="markdown"
        )
        operations = tistory_document.build_operations(document, {"hero": uploaded})
        for operation in operations:
            driver.execute(operation)
            assert driver.verify(operation), operation["feature_id"]

        assert uploaded == "https://blog.kakaocdn.net/dn/local-fixture/uploaded.jpg"
        assert page.locator("textarea[aria-label='제목']").input_value() == document["title"]
        assert "## 확인 근거" in page.locator("#source-body").input_value()
        assert page.locator("#status").inner_text() == "임시저장 완료"
    finally:
        browser.close()
        playwright.stop()


def test_local_privacy_preflight_and_derivative_pipeline(tmp_path: Path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    pytest.importorskip("cv2")
    image = tmp_path / "people.png"
    image_module.new("RGB", (96, 64), color=(220, 230, 240)).save(image)
    document = _document(tmp_path)
    document["media"][0]["path"] = str(image)
    validated = tistory_document.validate_document(document)

    preflight = tistory_editor.build_privacy_preflight(validated)
    prepared = tistory_editor.prepare_media(
        validated, preflight, data_dir=tmp_path / "autoseo-data"
    )

    assert preflight["hero"]["summary"]["detected_face_count"] == 0
    assert prepared["hero"].is_file()
    assert prepared["hero"] != image
    assert prepared["hero"].parent.name == "privacy-images"
    assert image_module.open(prepared["hero"]).size == (96, 64)


def test_disabling_face_mosaic_still_strips_metadata_by_default(
    tmp_path: Path,
) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image = tmp_path / "metadata.jpg"
    exif = image_module.Exif()
    exif[315] = "Private Photographer"
    image_module.new("RGB", (32, 24), color=(20, 30, 40)).save(image, exif=exif)
    document = _document(tmp_path)
    document["media"][0]["path"] = str(image)
    document["media"][0]["privacy"] = {"mode": "none"}
    validated = tistory_document.validate_document(document)

    preflight = tistory_editor.build_privacy_preflight(validated)
    prepared = tistory_editor.prepare_media(
        validated, preflight, data_dir=tmp_path / "autoseo-data"
    )

    assert preflight["hero"]["plan"] is not None
    assert prepared["hero"] != image
    assert image_module.open(prepared["hero"]).getexif().get(315) is None


def test_original_media_is_used_only_when_all_privacy_processing_is_disabled(
    tmp_path: Path,
) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image = tmp_path / "original.jpg"
    image_module.new("RGB", (32, 24), color=(20, 30, 40)).save(image)
    document = _document(tmp_path)
    document["media"][0]["path"] = str(image)
    document["media"][0]["privacy"] = {
        "mode": "none",
        "strip_metadata": False,
    }
    validated = tistory_document.validate_document(document)

    preflight = tistory_editor.build_privacy_preflight(validated)
    prepared = tistory_editor.prepare_media(
        validated, preflight, data_dir=tmp_path / "autoseo-data"
    )

    assert preflight["hero"]["plan"] is None
    assert prepared["hero"] == image
