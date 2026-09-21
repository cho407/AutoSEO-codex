from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/autoseo/scripts"))

import blog_format  # noqa: E402
import naver_document  # noqa: E402
import tistory_document  # noqa: E402


def document(**changes):
    return {"schema_version": 1, "document_id": "format-demo", "title": "읽기 편한 블로그",
            "layout_preset": "blog-centered", "blocks": [
                {"id": "intro", "type": "paragraph", "text": "짧은 도입 문장입니다.", "format_role": "intro"},
                {"id": "section", "type": "heading", "level": 2, "text": "확인할 내용"},
                {"id": "body", "type": "paragraph", "text": "첫 문장입니다.\n두 번째 문장입니다."},
                {"id": "source", "type": "paragraph", "text": "확인한 자료와 기준일", "format_role": "source"},
            ], **changes}


def test_naver_preset_compiles_styles_without_rewriting_content_or_explicit_choices():
    raw = document()
    raw["blocks"][2]["style"] = {"alignment": "left", "bold": False}
    before = copy.deepcopy(raw)
    operations = naver_document.build_operations(raw)
    by_id = {op["payload"].get("id"): op["payload"] for op in operations}
    assert by_id["intro"]["style"]["alignment"] == "center"
    assert by_id["section"]["style"]["bold"] is True
    assert by_id["section"]["style"]["size"] == 24
    assert by_id["body"]["style"]["alignment"] == "left"
    assert by_id["body"]["style"]["bold"] is False
    assert by_id["source"]["style"]["alignment"] == "left"
    assert [by_id[b["id"]]["text"] for b in raw["blocks"]] == [b["text"] for b in raw["blocks"]]
    assert raw == before


@pytest.mark.parametrize("module", [naver_document, tistory_document])
def test_preset_is_idempotent_and_changing_it_changes_hash_without_sticky_defaults(module):
    raw = document()
    normalized = module.validate_document(raw)
    assert module.validate_document(normalized) == normalized
    assert not normalized["blocks"][1].get("style")  # defaults are not mistaken for user overrides
    changed = {**normalized, "layout_preset": "article-readable"}
    assert module.document_hash(changed) != module.document_hash(normalized)
    if module is naver_document:
        assert module.build_operations(changed)[1]["payload"]["style"]["alignment"] == "left"
    else:
        assert 'text-align:left' in module.render_document(changed)


def test_legacy_documents_keep_their_plain_output_and_no_implicit_migration():
    raw = document()
    raw.pop("layout_preset")
    for block in raw["blocks"]:
        block.pop("format_role", None)
    assert "layout_preset" not in naver_document.validate_document(raw)
    assert naver_document.build_operations(raw)[1]["payload"]["style"] == {}
    assert tistory_document.validate_document(raw)["format"] == "markdown"
    assert "style=" not in tistory_document.render_document(raw, output_format="html")


def test_tistory_uses_safe_html_for_visible_alignment_and_semantic_headings():
    raw = document()
    raw["blocks"][2]["text"] = "<script>not executable</script>\n원문은 보존합니다."
    raw["blocks"].append({"id": "list", "type": "unordered-list", "items": ["A", "B"]})
    normalized = tistory_document.validate_document(raw)
    assert normalized["format"] == "html"
    rendered = tistory_document.render_document(normalized)
    assert '<h2 style="' in rendered and 'font-size:24px' in rendered
    assert 'text-align:center' in rendered and 'line-height:1.8' in rendered
    assert '<ul style="text-align:left' in rendered
    assert '<script>' not in rendered
    assert '&lt;script&gt;not executable&lt;/script&gt;<br>원문은 보존합니다.' in rendered
    operations = tistory_document.build_operations(normalized, {})
    assert operations[2]["payload"]["text"] == rendered


def test_explicit_markdown_does_not_silently_drop_formatting():
    with pytest.raises(ValueError, match="HTML"):
        tistory_document.validate_document(document(format="markdown"))
    with pytest.raises(ValueError, match="HTML"):
        tistory_document.render_document(document(), output_format="markdown")
    assert tistory_document.validate_document(document(format="markdown", layout_preset="none"))["format"] == "markdown"


@pytest.mark.parametrize("style", [{"size": float("nan")}, {"size": float("inf")},
                                  {"line_spacing": 0}, {"alignment": "center;display:none"},
                                  {"color": "red;position:fixed"}, {"font": 'Arial";background:url(x)'},
                                  {"position": "fixed"}, {"bold": "true"}])
def test_tistory_rejects_unsafe_style_values_before_rendering(style):
    raw = document()
    raw["blocks"][0]["style"] = style
    with pytest.raises(ValueError):
        tistory_document.validate_document(raw)


@pytest.mark.parametrize("module", [naver_document, tistory_document])
def test_unknown_presets_and_roles_stop_instead_of_silently_being_ignored(module):
    with pytest.raises(ValueError, match="preset"):
        module.validate_document(document(layout_preset="unknown"))
    raw = document()
    raw["blocks"][0]["format_role"] = "arbitrary-css"
    with pytest.raises(ValueError, match="role"):
        module.validate_document(raw)


def test_apply_cli_preserves_original_and_approval_settings(tmp_path, capsys):
    source, output = tmp_path / "source.json", tmp_path / "styled.json"
    raw = document()
    raw.pop("layout_preset")
    raw["publish_settings"] = {"mode": "draft", "visibility": "private"}
    source.write_text(json.dumps(raw), encoding="utf-8")
    original = source.read_bytes()
    assert blog_format.main(["apply", "naver", str(source), "--output", str(output)]) == 0
    applied = json.loads(output.read_text())
    assert applied["layout_preset"] == "blog-centered"
    assert applied["publish_settings"]["mode"] == "draft"
    assert applied["publish_settings"]["visibility"] == "private"
    assert source.read_bytes() == original
    assert raw["blocks"][0]["text"] not in capsys.readouterr().out
    saved = output.read_bytes()
    assert blog_format.main(["apply", "naver", str(source), "--output", str(output)]) == 2
    assert output.read_bytes() == saved
