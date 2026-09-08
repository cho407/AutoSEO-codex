"""Local browser smoke tests only; never call a real publication action."""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

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


@pytest.mark.parametrize("platform,body", [
    ("naver", '<iframe srcdoc="<div class=se-main-container><div contenteditable=true role=textbox aria-label=본문><p><br></p></div></div>"></iframe>'),
    ("tistory", '<iframe srcdoc="<body id=tinymce contenteditable=true style=min-height:80px></body>"></iframe>'),
    ("tistory", '<textarea aria-label="본문" name="content"></textarea>'),
])
def test_session_entry_accepts_the_same_visible_body_as_driver(page, platform, body):
    url = _fixture_url(platform)
    page.route("**/*", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body='<textarea aria-label="제목" placeholder="제목"></textarea>' + body))
    page.goto(url)
    assert page.get_by_role("textbox", name="제목", exact=True).is_visible()
    module = naver_editor if platform == "naver" else tistory_editor
    session = object.__new__(module.NaverBrowserSession if platform == "naver" else module.TistoryBrowserSession)
    session.page = page
    assert session.wait_for_editor(timeout_seconds=1) is page


def test_title_only_hidden_and_ambiguous_editors_are_not_ready(page):
    page.set_content('<textarea aria-label="제목"></textarea><div class="ProseMirror" contenteditable="true" hidden></div>')
    assert editor_compatibility.editor_body(page, "tistory") is None
    page.set_content('<div class="ProseMirror" contenteditable="true" style="min-height:40px"></div>' * 2)
    with pytest.raises(ValueError, match="ambiguous"):
        editor_compatibility.editor_body(page, "tistory")


@pytest.mark.parametrize("kind,markup", [
    ("codemirror5", '<div class="CodeMirror"><div class="CodeMirror-code" contenteditable="true">sample</div></div>'),
    ("codemirror6", '<div class="cm-editor"><div class="cm-content" contenteditable="true">sample</div></div>'),
])
def test_codemirror_is_not_also_counted_as_a_basic_editor(page, tmp_path, kind, markup):
    page.set_content('<textarea aria-label="제목"></textarea><div id="editor">' + markup + '</div>')
    driver = tistory_editor.PlaywrightTistoryDriver(page, catalog=tistory_editor.FeatureCatalog.load(), data_dir=tmp_path)
    assert driver._source_editor()[0] == kind
    assert editor_compatibility.editor_body(page, "tistory")[0] == kind
    assert editor_compatibility.editor_body(page, "tistory", kind="basic") is None
    assert editor_compatibility.editor_ready(page, "tistory", driver.resolver)
    page.locator("#editor").evaluate("node => node.insertAdjacentHTML('beforeend', '<div class=ProseMirror contenteditable=true>second editor</div>')")
    with pytest.raises(ValueError, match="ambiguous"):
        editor_compatibility.editor_body(page, "tistory")


@pytest.mark.parametrize("platform", ["naver", "tistory"])
def test_new_compose_preserves_a_title_even_when_the_body_is_empty(page, tmp_path, platform):
    page.goto((ROOT / f"tests/fixtures/{platform}_editor.html").as_uri())
    page.get_by_role("textbox", name="제목", exact=True).fill("사용자가 작성 중인 제목")
    module = naver_editor if platform == "naver" else tistory_editor
    driver_type = module.PlaywrightNaverDriver if platform == "naver" else module.PlaywrightTistoryDriver
    driver = driver_type(page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
    document = _document() if platform == "naver" else _tistory_document(tmp_path, with_media=False)
    store = module.CheckpointStore(tmp_path)
    automation = module.EditorAutomation(store) if platform == "naver" else module.TistoryEditorAutomation(store)
    with pytest.raises(ValueError, match="already contains content"):
        automation.apply(document, driver, **({} if platform == "naver" else {"prepared_media": {}}))
    assert page.get_by_role("textbox", name="제목", exact=True).input_value() == "사용자가 작성 중인 제목"


def _fixture_url(platform):
    if platform == "naver":
        return "https://blog.naver.com/PostWriteForm.naver?blogId=autoseo-fixture&logNo=42&fixture_persist=1"
    return "https://autoseo-fixture.tistory.com/manage/post/42?fixture_persist=1"


def _persisted_page(browser, platform, server):
    context = browser.new_context()
    url = _fixture_url(platform)

    def serve(route):
        path = urlsplit(route.request.url).path
        if path == "/autoseo-fixture-store":
            if route.request.method == "POST":
                server["saved"] = route.request.post_data_json
                server["saves"] = server.get("saves", 0) + 1
            route.fulfill(body=json.dumps(server.get("saved")), content_type="application/json")
        elif path.endswith("draft_persistence.js"):
            route.fulfill(path=str(ROOT / "tests/fixtures/draft_persistence.js"), content_type="text/javascript")
        elif route.request.url == url:
            route.fulfill(path=str(ROOT / f"tests/fixtures/{platform}_editor.html"), content_type="text/html")
        else:
            route.abort()  # Fixture tests never reach a live blog or CDN.

    context.route("**/*", serve)
    page = context.new_page()
    page.goto(url)
    page.wait_for_function("window.fixtureLoaded === true")
    return context, page


@pytest.mark.parametrize("platform", ["tistory", "naver"])
def test_draft_survives_new_session_and_resume_does_not_save_or_insert_again(browser, tmp_path, platform):
    from PIL import Image

    server = {}
    context, page = _persisted_page(browser, platform, server)
    module = naver_editor if platform == "naver" else tistory_editor
    document = _document() if platform == "naver" else _tistory_document(tmp_path, with_media=True)
    photo = tmp_path / "synthetic.png"
    Image.new("RGB", (8, 8), color="blue").save(photo)
    if platform == "naver":
        document["blocks"] = [document["blocks"][0], {"id": "plain", "type": "paragraph", "text": "다음 문단입니다."},
                              {"id": "image", "type": "photo", "path": str(photo)}]
    else:
        document["media"][0]["path"] = str(photo)
    document = module.validate_document(document)
    store = module.CheckpointStore(tmp_path)
    automation = module.EditorAutomation(store) if platform == "naver" else module.TistoryEditorAutomation(store)
    driver_type = module.PlaywrightNaverDriver if platform == "naver" else module.PlaywrightTistoryDriver
    driver = driver_type(page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
    options = {} if platform == "naver" else {"prepared_media": {"hero": photo}}
    saved = automation.apply(document, driver, **options)
    assert saved["save_state"] == "acknowledged"
    assert automation.verify_draft(document, driver)["verification_state"] == "unavailable"
    context.close()

    reopened_context, reopened_page = _persisted_page(browser, platform, server)
    try:
        reopened_driver = driver_type(reopened_page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
        result = automation.verify_draft(document, reopened_driver)
        assert result["verification_state"] == "verified"
        verified = store.load_existing(document)
        assert verified["saved_session_id"] != verified["verified_session_id"]
        saves = server["saves"]
        automation.apply(document, reopened_driver, **options)
        assert server["saves"] == saves
        assert reopened_page.evaluate("window.publishClicks || 0") == 0
        assert document["title"] not in store.path_for(document["document_id"]).read_text()
        # Identical text with a lost inline format must invalidate the readback.
        if platform == "naver":
            reopened_page.locator(".se-main-container b").first.evaluate("node => node.replaceWith(...node.childNodes)")
        else:
            original_mode = reopened_page.locator("#mode-button").inner_text()
            reopened_page.locator("#mode-button").evaluate("node => node.textContent = 'HTML'")
            assert automation.verify_draft(document, reopened_driver)["verification_state"] == "mismatch"
            reopened_page.locator("#mode-button").evaluate("(node, text) => node.textContent = text", original_mode)
            reopened_page.locator("#source-body").fill("사용자가 직접 바꾼 내용")
        result = automation.verify_draft(document, reopened_driver)
        assert result["verification_state"] == "mismatch"
        assert store.load_existing(document)["verified_surface_hash"] is None
        with pytest.raises((ValueError, module.EditorUIChanged)):
            automation.apply(document, reopened_driver, **options)
        assert server["saves"] == saves
    finally:
        reopened_context.close()


def test_style_only_change_affects_naver_fingerprint(page, tmp_path):
    page.locator(".se-main-container").evaluate("node => node.innerHTML = '<div contenteditable=true><p><b>같은 내용</b></p></div>'")
    driver = naver_editor.PlaywrightNaverDriver(page, catalog=naver_editor.FeatureCatalog.load(), data_dir=tmp_path)
    bold_hash = driver.snapshot_hash()
    page.locator("b").evaluate("node => node.replaceWith(...node.childNodes)")
    assert driver.snapshot_hash() != bold_hash


@pytest.mark.parametrize("tag,decoration", [("u", None), ("s", None), ("span", "underline")])
def test_ancestor_text_decoration_loss_changes_the_fingerprint(page, tmp_path, tag, decoration):
    style = f' style="text-decoration: {decoration}"' if decoration else ""
    markup = f'<div contenteditable=true><p><{tag} class="decoration"{style}><span>같은 내용</span></{tag}></p></div>'
    page.locator(".se-main-container").evaluate("(node, markup) => node.innerHTML = markup", markup)
    driver = naver_editor.PlaywrightNaverDriver(page, catalog=naver_editor.FeatureCatalog.load(), data_dir=tmp_path)
    decorated_hash = driver.snapshot_hash()
    page.locator(".decoration").evaluate("node => node.replaceWith(...node.childNodes)")
    assert driver.snapshot_hash() != decorated_hash


def test_markdown_indentation_is_preserved_in_the_fingerprint(page, tmp_path):
    page.goto((ROOT / "tests/fixtures/tistory_editor.html").as_uri())
    page.evaluate("""() => {
        document.querySelector('#mode-button').textContent = '마크다운';
        document.querySelector('#source-body').hidden = false;
        document.querySelector('#basic-body').hidden = true;
    }""")
    driver = tistory_editor.PlaywrightTistoryDriver(page, catalog=tistory_editor.FeatureCatalog.load(), data_dir=tmp_path)
    page.locator("#source-body").fill("sample\n")
    paragraph_hash = driver.snapshot_hash()
    page.locator("#source-body").fill("    sample\n")
    assert driver.snapshot_hash() != paragraph_hash


def test_legacy_or_unidentified_checkpoint_cannot_claim_reopened_verification(page, tmp_path):
    from editor_safety import verify_reopened_draft

    driver = naver_editor.PlaywrightNaverDriver(page, catalog=naver_editor.FeatureCatalog.load(), data_dir=tmp_path)
    checkpoint = naver_editor.CheckpointStore._new(naver_editor.validate_document(_document()))
    checkpoint.update(save_state="acknowledged", saved_surface_hash=driver.snapshot_hash(), saved_source_hash=checkpoint["source_hash"])
    result = verify_reopened_draft(deepcopy(checkpoint), driver)
    assert result["verification_state"] == "unavailable"


@pytest.mark.parametrize("platform", ["naver", "tistory"])
@pytest.mark.parametrize("after_save", [False, True])
def test_crash_at_save_is_reconciled_from_new_session_without_resaving(browser, tmp_path, platform, after_save):
    class ProcessStopped(BaseException):
        pass

    module = naver_editor if platform == "naver" else tistory_editor
    document = _document() if platform == "naver" else _tistory_document(tmp_path, with_media=False)
    if platform == "naver":
        document["blocks"] = [document["blocks"][0]]
    store = module.CheckpointStore(tmp_path)
    automation = module.EditorAutomation(store) if platform == "naver" else module.TistoryEditorAutomation(store)
    driver_type = module.PlaywrightNaverDriver if platform == "naver" else module.PlaywrightTistoryDriver
    server = {}
    context, page = _persisted_page(browser, platform, server)
    driver = driver_type(page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
    execute = driver.execute

    def crash(operation):
        if operation["feature_id"] != "draft-save" or after_save:
            execute(operation)
        if operation["feature_id"] == "draft-save":
            raise ProcessStopped()

    driver.execute = crash
    options = {} if platform == "naver" else {"prepared_media": {}}
    with pytest.raises(ProcessStopped):
        automation.apply(document, driver, **options)
    context.close()
    reopened_context, reopened_page = _persisted_page(browser, platform, server)
    try:
        reader = driver_type(reopened_page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
        result = automation.verify_draft(document, reader)
        if after_save:
            assert result["verification_state"] == "verified"
            assert store.load_existing(document)["save_state"] == "readback-confirmed"
            automation.apply(document, reader, **options)
        else:
            assert result["verification_state"] != "verified"
        assert server.get("saves", 0) == int(after_save)
        assert reopened_page.evaluate("window.publishClicks || 0") == 0
    finally:
        reopened_context.close()
