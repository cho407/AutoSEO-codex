"""Synthetic real-Playwright coverage, not evidence of live account readiness."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/autoseo/scripts"))

import naver_document as native  # noqa: E402
import naver_editor as editor  # noqa: E402

pytest_plugins = ("test_editor_browser_safety",)


def document():
    return {
        "schema_version": 1, "document_id": "synthetic-native-runtime", "title": "Synthetic native guide",
        "background": {"type": "none"}, "tags": [], "publish_settings": {"mode": "draft"},
        "design_profile": {"schema_version": 1, "preset": "compact-native"},
        "blocks": [
            {"id": "intro", "type": "paragraph", "text": "Intro paragraph."},
            {"id": "question", "type": "heading", "level": 2, "text": "Question heading?",
             "style": {"size": 19, "alignment": "center", "line_spacing": 1.8}, "spacing_before": "section"},
            {"id": "body", "type": "paragraph", "text": "Normal body paragraph."},
            {"id": "minor", "type": "heading", "level": 3, "text": "Minor heading", "style": {"size": 16}},
            {"id": "circle", "type": "paragraph", "text": "Circle body.", "list_marker_style": "circle"},
        ],
    }


def driver(page, tmp_path, enabled=True):
    return editor.PlaywrightNaverDriver(page, catalog=editor.FeatureCatalog.load(), data_dir=tmp_path,
                                        experimental_native_text=enabled)


def compiled(value):
    return native.build_operations(value, experimental_native_text=True)


def test_cli_plan_drives_real_executor_and_persisted_style_layout(input_buffer_page, tmp_path, capsys):
    value = document()
    original = copy.deepcopy(value)
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    assert editor.main(["plan", str(path), "--experimental-native-text"]) == 0
    plan = json.loads(capsys.readouterr().out)
    operations = plan["compiled_operations"]
    page = input_buffer_page
    runtime = driver(page, tmp_path)
    runtime.prepare_operations(operations)
    for operation in operations:
        runtime.execute(operation)
        assert runtime.verify(operation)
    rows = runtime._native_snapshot()
    assert [row["text"] for row in rows] == [
        "Intro paragraph.", "", "Question heading?", "Normal body paragraph.",
        "Minor heading", "● Circle body.", "",
    ]
    assert [(row["style"]["size"], row["style"]["bold"]) for row in rows if row["text"]] == [
        (15, False), (19, True), (15, False), (16, True), (15, False),
    ]
    assert rows[2]["style"]["alignment"] == "center"
    assert rows[2]["style"]["line_spacing"] == 1.8
    assert rows[3]["style"]["alignment"] == "left"
    assert rows[3]["style"]["line_spacing"] == 1.5
    assert runtime.verify_document(value)
    saved_hash = runtime.snapshot_hash()
    assert runtime.verify_saved_draft(value) == saved_hash
    assert runtime._native_snapshot() == rows
    assert page.evaluate("window.publishClicks") == 0
    assert value == original
    assert path.read_text() == json.dumps(value)


def test_checkpoint_resume_and_style_only_edit_require_reconciliation(input_buffer_page, tmp_path):
    value = document()
    runtime = driver(input_buffer_page, tmp_path)
    automation = editor.EditorAutomation(editor.CheckpointStore(tmp_path))
    result = automation.apply(value, runtime)
    assert result["save_state"] == "acknowledged"
    assert result["saved_surface_hash"] == runtime.snapshot_hash()
    automation.apply(value, runtime)
    assert input_buffer_page.evaluate("window.draftSaveClicks") == 1
    input_buffer_page.locator(".se-section-text p").nth(2).evaluate("p => p.style.fontWeight = '400'")
    assert not runtime.verify_document(value)
    with pytest.raises(ValueError, match="content changed"):
        automation.apply(value, runtime)
    assert input_buffer_page.evaluate("window.draftSaveClicks") == 1


def test_default_native_flag_stays_off(input_buffer_page, tmp_path):
    runtime = driver(input_buffer_page, tmp_path, enabled=False)
    with pytest.raises((editor.EditorUIChanged, ValueError), match="does not safely support|plan-only"):
        editor.EditorAutomation(editor.CheckpointStore(tmp_path)).apply(document(), runtime)
    assert input_buffer_page.evaluate("window.inputEvents") == 0


@pytest.mark.parametrize("field,value", [
    ("alignment", "right"), ("line_spacing", 1.55), ("line_spacing", "1.8"),
    ("line_spacing", True), ("size", 14), ("italic", True),
])
def test_unobserved_styles_are_rejected(field, value):
    source = document()
    source["blocks"][0]["style"] = {field: value}
    with pytest.raises(ValueError):
        compiled(source)


@pytest.mark.parametrize("case", ["start", "unknown", "nontext", "no-profile", "blank-inside"])
def test_spacing_rejects_unsafe_requests(case):
    source = document()
    if case == "start":
        source["blocks"][0]["spacing_before"] = "section"
    elif case == "unknown":
        source["blocks"][0]["spacing_before"] = "large"
    elif case == "nontext":
        source["blocks"].append({"id": "divider", "type": "divider", "spacing_before": "section"})
    elif case == "no-profile":
        source.pop("design_profile")
    else:
        source["blocks"][0]["text"] = "First.\n\nSecond."
    with pytest.raises(ValueError):
        compiled(source)


@pytest.mark.parametrize("text,expected", [("Item.", "● Item."), ("● Item.", "● Item.")])
def test_circle_preserves_source_and_renders_once(text, expected):
    source = document()
    source["blocks"][-1]["text"] = text
    before = copy.deepcopy(source)
    assert compiled(source)[-2]["payload"]["text"] == expected
    assert native.native_design_plan(source)["paragraphs"][-1]["rendered_text"] == expected
    assert source == before


@pytest.mark.parametrize("kind", ["quote", "photo", "divider", "links", "tags", "guided"])
def test_full_preflight_refuses_unsupported_content_before_title(input_buffer_page, tmp_path, kind):
    source = document()
    if kind == "quote":
        source["blocks"].append({"id": "quote", "type": "quote", "text": "Unsupported quote."})
    elif kind == "photo":
        data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=")
        path = tmp_path / "synthetic.png"
        path.write_bytes(data)
        source["blocks"].append({"id": "cover", "type": "photo", "path": str(path), "design_role": "cover",
            "design_review": {"approved": True, "sha256": hashlib.sha256(data).hexdigest(),
                              "provenance": "original", "relevance_checked": True}})
    elif kind == "divider":
        source["blocks"].append({"id": "divider", "type": "divider"})
    elif kind == "links":
        source["blocks"][0]["links"] = [{"text": "Intro", "url": "https://example.org/guide"}]
    elif kind == "tags":
        source["tags"] = ["synthetic"]
    else:
        source["editor_options"] = {"spellcheck": True}
    with pytest.raises((ValueError, editor.EditorUIChanged)):
        editor.EditorAutomation(editor.CheckpointStore(tmp_path)).apply(source, driver(input_buffer_page, tmp_path))
    assert input_buffer_page.evaluate("window.inputEvents") == 0
    assert input_buffer_page.evaluate("window.draftSaveClicks") == 0
    assert input_buffer_page.evaluate("window.publishClicks") == 0


@pytest.mark.parametrize("case", ["missing", "ambiguous", "unknown-bold", "invalid-aria", "overlay"])
def test_preflight_controls_fail_closed(input_buffer_page, tmp_path, case):
    page = input_buffer_page
    if case == "missing":
        page.locator('button[data-name="font-size"]').evaluate("n => n.remove()")
    elif case == "ambiguous":
        page.locator('button[data-name="font-size"]').evaluate("n => n.after(n.cloneNode(true))")
    elif case == "unknown-bold":
        page.locator('button[data-name="bold"]').evaluate("n => n.className = 'unmeasured-toggle'")
    elif case == "invalid-aria":
        page.locator('button[data-name="bold"]').evaluate("n => n.setAttribute('aria-pressed', 'mixed')")
    else:
        page.evaluate("() => { const n = document.createElement('div'); n.className = 'se-popup-dim'; n.textContent = 'Overlay'; document.body.append(n); }")
    with pytest.raises(editor.EditorUIChanged):
        editor.EditorAutomation(editor.CheckpointStore(tmp_path)).apply(document(), driver(page, tmp_path))
    assert page.evaluate("window.inputEvents") == 0
    assert page.evaluate("window.publishClicks") == 0


@pytest.mark.parametrize("case", ["occupied", "misfocused", "partial-top", "partial-buffer", "stolen", "missing-option", "ambiguous-option"])
def test_native_input_guards_stop_uncertain_writes(input_buffer_page, tmp_path, case):
    page = input_buffer_page
    runtime = driver(page, tmp_path)
    operations = compiled(document())
    runtime.prepare_operations(operations)
    runtime.execute(operations[0])
    inputs = page.evaluate("window.inputEvents")
    if case == "occupied":
        page.locator('.se-section-text p').evaluate("n => n.append('Occupied despite placeholder')")
    elif case in {"misfocused", "partial-top", "partial-buffer"}:
        page.evaluate("""kind => {
            section.addEventListener('click', () => {
                if (kind === 'misfocused') { focusParagraph(document.querySelector('.se-section-documentTitle p')); return; }
                if (kind === 'partial-top') {
                    const s = window.getSelection(), r = document.createRange();
                    r.selectNodeContents(document.querySelector('.se-section-text p')); s.removeAllRanges(); s.addRange(r);
                } else {
                    buffer.textContent = 'selected'; const s = frame.contentWindow.getSelection();
                    const r = frame.contentDocument.createRange(); r.selectNodeContents(buffer); s.removeAllRanges(); s.addRange(r);
                }
            });
        }""", case)
    elif case == "stolen":
        page.evaluate("""() => {
            const field = document.createElement('input'); document.body.append(field);
            document.querySelector('[data-name=font-size]').addEventListener('click', () => field.focus());
        }""")
    else:
        page.locator('button[data-name="font-size"]').evaluate("""(n, kind) => n.addEventListener('click', () => {
            const option = document.querySelector('[data-role=option][data-value=fs15]');
            if (kind === 'missing-option') option.remove(); else option.after(option.cloneNode(true));
        })""", case)
    with pytest.raises((editor.EditorUIChanged, ValueError)):
        runtime.execute(operations[1])
    assert page.evaluate("window.inputEvents") == inputs
    assert page.evaluate("window.draftSaveClicks") == 0
    assert page.evaluate("window.publishClicks") == 0


@pytest.mark.parametrize("corruption", ["blank", "run", "saved-style"])
def test_exact_blank_layout_and_all_runs_are_verified(input_buffer_page, tmp_path, corruption):
    page = input_buffer_page
    runtime = driver(page, tmp_path)
    source = document()
    editor.EditorAutomation(editor.CheckpointStore(tmp_path)).apply(source, runtime)
    fingerprint = runtime.snapshot_hash()
    if corruption == "blank":
        page.locator('.se-section-text p').nth(1).evaluate("n => n.remove()")
    elif corruption == "run":
        page.locator('.se-section-text p').nth(2).evaluate("""n => {
            const span = document.createElement('span'); span.style.fontWeight = '400';
            span.textContent = n.textContent.slice(-1); n.textContent = n.textContent.slice(0, -1); n.append(span);
        }""")
    else:
        page.evaluate("""() => {
            const saved = JSON.parse(localStorage.getItem(storageKey));
            saved.paragraphs[2].style = saved.paragraphs[2].style.replace('700', '400');
            localStorage.setItem(storageKey, JSON.stringify(saved));
        }""")
        with pytest.raises(editor.EditorUIChanged, match="fingerprint"):
            runtime.verify_saved_draft(source)
        return
    assert runtime.snapshot_hash() != fingerprint
    assert not runtime.verify_document(source)
    assert page.evaluate("window.publishClicks") == 0
