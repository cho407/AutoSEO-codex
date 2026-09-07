"""Local browser smoke tests only; never call a real publication action."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/autoseo/scripts"))

import editor_compatibility  # noqa: E402
import naver_editor  # noqa: E402
import tistory_editor  # noqa: E402
from editor_safety import FreshSaveReceipt, exclusive_lock  # noqa: E402
from test_naver_editor import _document  # noqa: E402
from test_tistory_editor import _document as _tistory_document  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if os.environ.get("AUTOSEO_REQUIRE_BROWSER_TESTS") == "1":
            pytest.fail("required browser runtime is missing")
        pytest.skip("optional browser runtime is missing")
    with sync_playwright() as runtime:
        try:
            launched = runtime.chromium.launch(headless=True)
        except Exception as exc:
            if os.environ.get("AUTOSEO_REQUIRE_BROWSER_TESTS") == "1":
                pytest.fail(f"required browser could not launch: {type(exc).__name__}")
            pytest.skip("browser unavailable in this environment")
        yield launched
        launched.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    page.goto((ROOT / "tests/fixtures/naver_editor.html").as_uri())
    yield page
    page.close()


def test_new_naver_save_and_plain_format_after_bold(page, tmp_path):
    document = _document()
    document["blocks"] = [document["blocks"][0], {
        "id": "plain", "type": "paragraph", "text": "다음 문단은 굵지 않은 일반 문장입니다."
    }]
    driver = naver_editor.PlaywrightNaverDriver(page, catalog=naver_editor.FeatureCatalog.load(), data_dir=tmp_path)
    result = naver_editor.EditorAutomation(naver_editor.CheckpointStore(tmp_path)).apply(document, driver)
    assert result["save_state"] == "acknowledged"
    assert result["saved_surface_hash"]
    assert page.evaluate("window.publishClicks") == 0
    assert page.get_by_text(document["blocks"][1]["text"], exact=True).evaluate("node => getComputedStyle(node).fontWeight") == "400"


def test_old_save_toast_is_not_a_new_save_receipt(page):
    receipt = FreshSaveReceipt(page)
    receipt.begin()
    assert receipt.confirm(timeout=50) is False
    receipt.begin()
    page.get_by_role("button", name="임시저장", exact=True).click()
    assert receipt.confirm() is True


def test_recreated_old_toast_is_not_a_fresh_acknowledgement(page):
    receipt = FreshSaveReceipt(page)
    receipt.begin()
    page.locator("#status").evaluate("node => node.replaceWith(node.cloneNode(true))")
    assert receipt.confirm(timeout=50) is False


def test_learn_map_is_consumed_and_expired_maps_are_rejected(page, tmp_path):
    catalog = naver_editor.FeatureCatalog.load()
    learned = naver_editor.learn_compatibility_map(page, catalog, editor_url=page.url)
    assert learned["features"]["bold"]["scope"] == "toolbar"
    assert learned["features"]["paragraph"]["frame_index"] == 0
    path = tmp_path / "naver-editor-compatibility.json"
    path.write_text(json.dumps(learned), encoding="utf-8")
    driver = naver_editor.PlaywrightNaverDriver(page, catalog=catalog, data_dir=tmp_path)
    assert driver.resolver.compatibility is not None
    learned["observed_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    path.write_text(json.dumps(learned), encoding="utf-8")
    assert editor_compatibility.load_map(path, page, catalog) is None


def test_frames_dialog_scope_and_ambiguous_controls(page):
    page.set_content('<button>확인</button><div role="dialog"><button>확인</button></div>')
    catalog = naver_editor.FeatureCatalog.load()
    catalog.features["dialog-confirm"] = {"id": "dialog-confirm", "locator": {"role": "button", "name": "확인"}}
    resolver = naver_editor.LocatorResolver(page, catalog)
    _, target = resolver.locate("dialog-confirm")
    assert target.evaluate("node => !!node.closest('[role=dialog]')")
    page.set_content('<iframe srcdoc="<div class=se-main-container><textarea aria-label=본문></textarea></div>"></iframe>')
    page.frame_locator("iframe").get_by_role("textbox", name="본문").wait_for()
    assert resolver.locate("paragraph")[1].count() == 1
    page.frames[1].evaluate("document.querySelector('textarea').after(document.querySelector('textarea').cloneNode())")
    with pytest.raises(naver_editor.AmbiguousElement):
        resolver.locate("paragraph")


def test_tistory_tinymce_body_is_found_without_clearing_user_content(page, tmp_path):
    page.set_content('<iframe srcdoc="<body id=tinymce contenteditable=true>사용자가 작성한 글</body>"></iframe>')
    page.frame_locator("iframe").locator("#tinymce").wait_for()
    driver = tistory_editor.PlaywrightTistoryDriver(page, catalog=tistory_editor.FeatureCatalog.load(), data_dir=tmp_path)
    assert driver._basic_body().inner_text() == "사용자가 작성한 글"


def test_tistory_resume_after_title_recovers_current_mode_without_rewriting(page, tmp_path):
    page.goto((ROOT / "tests/fixtures/tistory_editor.html").as_uri())
    document = tistory_editor.validate_document(_tistory_document(tmp_path, with_media=False))
    operations = tistory_editor.build_operations(document, {})
    store = tistory_editor.CheckpointStore(tmp_path)
    driver = tistory_editor.PlaywrightTistoryDriver(page, catalog=tistory_editor.FeatureCatalog.load(), data_dir=tmp_path)
    original = driver.execute

    def interrupt(operation):
        if operation["feature_id"] == "body-source":
            raise tistory_editor.EditorUIChanged("interrupted before body input")
        original(operation)

    driver.execute = interrupt
    with pytest.raises(tistory_editor.EditorUIChanged):
        tistory_editor.TistoryEditorAutomation(store).apply(document, driver, prepared_media={})
    recovered = tistory_editor.PlaywrightTistoryDriver(page, catalog=tistory_editor.FeatureCatalog.load(), data_dir=tmp_path)
    result = tistory_editor.TistoryEditorAutomation(store).apply(document, recovered, prepared_media={})
    assert len(result["completed_operation_ids"]) == len(operations)
    assert result["save_state"] == "acknowledged"
    assert page.locator('#source-body').input_value().count(document["blocks"][0]["text"]) == 1


@pytest.mark.parametrize("module", [naver_editor, tistory_editor])
def test_home_or_old_link_is_not_publication_success(page, tmp_path, module):
    driver_class = module.PlaywrightNaverDriver if module is naver_editor else module.PlaywrightTistoryDriver
    driver = driver_class(page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
    page.set_content('<a href="https://example.tistory.com/42">기존 글</a>')
    assert driver.verify_publish("publish") is None
    with pytest.raises(RuntimeError, match="disabled"):
        driver.click_publish("publish")


def test_document_and_profile_lock_conflicts_are_rejected(tmp_path):
    path = tmp_path / "run.lock"
    with exclusive_lock(path):
        with pytest.raises(RuntimeError, match="another editor run"):
            with exclusive_lock(path):
                pytest.fail("overlapping editor run started")
    with exclusive_lock(path):
        pass
