"""Local browser smoke tests only; never call a real publication action."""
from __future__ import annotations

import json
import os
import sys
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


def test_live_korean_save_acknowledgement_is_recognized(page):
    page.set_content("<button id=save>저장</button><div role=status>준비</div>")
    page.locator("#save").evaluate("""node => node.onclick = () => {
        document.querySelector('[role=status]').textContent = '저장 중';
        setTimeout(() => document.querySelector('[role=status]').textContent =
            '임시저장이 완료되었습니다.', 20);
    }""")
    receipt = FreshSaveReceipt(page)
    receipt.begin()
    page.locator("#save").click()
    assert receipt.confirm() is True


@pytest.mark.parametrize("platform", ["naver", "tistory"])
def test_english_ui_composes_and_saves_korean_draft(page, tmp_path, platform):
    page.goto((ROOT / f"tests/fixtures/{platform}_editor.html").as_uri())
    page.evaluate("""() => {
        document.documentElement.lang = 'en';
        const names = {'제목':'Title', '본문':'Body', '태그':'Tags', '사진':'Photo',
            '굵게':'Bold', '기울임꼴':'Italic', '밑줄':'Underline', '취소선':'Strikethrough',
            '위 첨자':'Superscript', '아래 첨자':'Subscript', '정렬':'Alignment',
            '기본모드':'Basic mode', '마크다운':'Markdown', '임시저장':'Save draft',
            '왼쪽':'Left', '가운데':'Center', '오른쪽':'Right'};
        document.querySelectorAll('[aria-label]').forEach(node => {
            const value = names[node.getAttribute('aria-label')];
            if (value) node.setAttribute('aria-label', value);
        });
        document.querySelectorAll('button').forEach(node => {
            if (names[node.textContent]) node.textContent = names[node.textContent];
        });
        window.draftSaveClicks = 0;
        const save = document.querySelector('#save, #draft-save');
        save.addEventListener('click', () => {
            window.draftSaveClicks++;
            document.querySelector('#status').textContent = 'Saving';
            setTimeout(() => document.querySelector('#status').textContent = 'Draft saved', 60);
        });
    }""")
    module = naver_editor if platform == "naver" else tistory_editor
    driver_type = module.PlaywrightNaverDriver if platform == "naver" else module.PlaywrightTistoryDriver
    driver = driver_type(page, catalog=module.FeatureCatalog.load(), data_dir=tmp_path)
    document = _document() if platform == "naver" else _tistory_document(tmp_path, with_media=False)
    if platform == "naver":
        document["blocks"] = [document["blocks"][0]]
    store = module.CheckpointStore(tmp_path)
    automation = module.EditorAutomation(store) if platform == "naver" else module.TistoryEditorAutomation(store)
    result = automation.apply(document, driver, **({} if platform == "naver" else {"prepared_media": {}}))
    assert editor_compatibility.ui_language(page) == "en"
    assert page.get_by_role("textbox", name="Title", exact=True).input_value() == document["title"]
    assert result["save_state"] == "acknowledged"
    assert result["saved_surface_hash"]
    assert page.evaluate("window.draftSaveClicks") == 1
    assert driver.verify({"feature_id": "tags", "payload": {"tags": document["tags"]}})


@pytest.mark.parametrize("markup", [
    '<textarea aria-label="Title"></textarea>',
    '<div contenteditable="true" role="textbox" aria-label="Title"></div>',
])
def test_unicode_title_replacement_is_scoped_to_title(page, monkeypatch, markup):
    page.set_content(markup + '<div contenteditable="true" id="body">보존할 본문</div>')
    title = page.get_by_role("textbox", name="Title", exact=True)
    fill = title.fill
    monkeypatch.setattr(title, "fill", lambda _: fill("gksrmf whrma"))
    editor_compatibility.fill_unicode_exact(page, title, "한국어 제목을 그대로 입력")
    assert editor_compatibility._read_locator_text(title) == "한국어 제목을 그대로 입력"
    assert page.locator("#body").inner_text() == "보존할 본문"


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


def test_learned_fast_path_revises_only_title_and_saves_once(page, tmp_path):
    catalog = naver_editor.FeatureCatalog.load()
    current = "현재 제목"
    replacement = "검색 의도가 분명한 새 제목"
    page.get_by_role("textbox", name="제목", exact=True).fill(current)
    page.get_by_role("textbox", name="본문", exact=True).fill("보존할 본문")

    learned = naver_editor.learn_compatibility_map(page, catalog, editor_url=page.url)
    (tmp_path / "naver-editor-compatibility.json").write_text(
        json.dumps(learned), encoding="utf-8"
    )
    page.evaluate("window.draftSaveClicks = 0")
    page.get_by_role("button", name="임시저장", exact=True).evaluate(
        "node => node.addEventListener('click', () => window.draftSaveClicks++)"
    )

    result = naver_editor.revise_title(
        page,
        catalog,
        data_dir=tmp_path,
        expected_current_title=current,
        new_title=replacement,
    )

    assert result["save_state"] == "acknowledged"
    assert result["title_locator"]["source"] == "learned-map"
    assert result["save_locator"]["source"] == "learned-map"
    assert page.get_by_role("textbox", name="제목", exact=True).input_value() == replacement
    assert page.get_by_role("textbox", name="본문", exact=True).inner_text() == "보존할 본문"
    assert page.evaluate("window.draftSaveClicks") == 1


def test_title_revision_stops_before_write_on_wrong_visible_title(page, tmp_path):
    page.get_by_role("textbox", name="제목", exact=True).fill("다른 초안")
    with pytest.raises(naver_editor.EditorUIChanged, match="expected current title"):
        naver_editor.revise_title(
            page,
            naver_editor.FeatureCatalog.load(),
            data_dir=tmp_path,
            expected_current_title="수정할 초안",
            new_title="새 제목",
        )
    assert page.get_by_role("textbox", name="제목", exact=True).input_value() == "다른 초안"


def test_shipped_naver_title_and_save_fast_paths_need_no_surface_scan(page, tmp_path):
    page.set_content("""
        <div class="se-documentTitle">
          <div class="se-text-paragraph" contenteditable="true">현재 제목</div>
        </div>
        <div class="se-main-container">
          <div contenteditable="true"><p>보존할 본문</p></div>
        </div>
        <button data-click-area="tpb.save">저장</button>
        <div role="status">준비</div>
        <script>
          window.saveClicks = 0;
          document.querySelector('button').onclick = () => {
            window.saveClicks++;
            const status = document.querySelector('[role=status]');
            status.textContent = '저장 중';
            setTimeout(() => status.textContent = '임시저장이 완료되었습니다.', 20);
          };
        </script>
    """)

    result = naver_editor.revise_title(
        page,
        naver_editor.FeatureCatalog.load(),
        data_dir=tmp_path,
        expected_current_title="현재 제목",
        new_title="빠른 제목 수정",
    )

    assert result["title_locator"]["source"] == "catalog-fast-path"
    assert result["save_locator"]["source"] == "catalog-fast-path"
    assert page.locator(".se-main-container").inner_text() == "보존할 본문"
    assert page.evaluate("window.saveClicks") == 1


def test_shipped_naver_tag_fast_path_appends_each_validated_tag(page, tmp_path):
    page.set_content("""
        <div class="se-main-container">
          <div contenteditable="true"><p>보존할 본문</p></div>
        </div>
        <input aria-label="태그 입력 (최대 30개)" placeholder="태그 입력 (최대 30개)">
        <div id="tags"></div>
        <script>
          const input = document.querySelector('input');
          input.onkeydown = event => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            const tag = document.createElement('span');
            tag.textContent = input.value;
            document.querySelector('#tags').append(tag);
            input.value = '';
          };
        </script>
    """)
    driver = naver_editor.PlaywrightNaverDriver(
        page, catalog=naver_editor.FeatureCatalog.load(), data_dir=tmp_path
    )
    operation = {
        "operation_id": "tags:fast-path",
        "feature_id": "tags",
        "payload": {"tags": ["생애최초대출", "DSR"]},
    }

    driver.execute(operation)

    assert driver.resolver.last_resolution["source"] == "catalog-fast-path"
    assert page.locator("#tags span").all_text_contents() == ["생애최초대출", "DSR"]
    assert page.locator(".se-main-container").inner_text() == "보존할 본문"


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
def test_draft_resume_stays_in_the_active_session_and_does_not_save_again(browser, tmp_path, platform):
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
    assert not hasattr(automation, "verify_draft")
    saves = server["saves"]
    resumed = automation.apply(document, driver, **options)
    assert resumed["save_state"] == "acknowledged"
    assert server["saves"] == saves
    assert page.evaluate("window.publishClicks || 0") == 0
    assert document["title"] not in store.path_for(document["document_id"]).read_text()

    # A same-session content change blocks resume rather than reopening or saving.
    if platform == "naver":
        page.locator(".se-main-container b").first.evaluate("node => node.replaceWith(...node.childNodes)")
    else:
        page.locator("#source-body").fill("사용자가 직접 바꾼 내용")
    with pytest.raises((ValueError, module.EditorUIChanged)):
        automation.apply(document, driver, **options)
    assert server["saves"] == saves
    context.close()


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


@pytest.mark.parametrize("platform", ["naver", "tistory"])
@pytest.mark.parametrize("after_save", [False, True])
def test_crash_at_save_requires_manual_reconciliation_without_resaving(browser, tmp_path, platform, after_save):
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
    try:
        with pytest.raises(module.EditorUIChanged, match="manual reconciliation"):
            automation.apply(document, driver, **options)
        assert server.get("saves", 0) == int(after_save)
    finally:
        context.close()
