from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/autoseo/scripts"))

from blog_image import (  # noqa: E402
    check_image,
    generation_prompt,
    make_review,
    render_template,
    require_image_reviews,
    validate_brief,
)


def brief(**kwargs):
    return {"schema_version": 1, "role": "hero", "topic": "일상 정리",
            "title": "정돈된 하루를 만드는 작은 습관", "layout": "card", **kwargs}


def test_policy_is_injected_without_model_inventing_style():
    prompt = generation_prompt(brief())
    assert "1600" in prompt and "watermark" in prompt
    assert "clean-editorial" in prompt
    assert "balanced-editorial" in prompt
    with pytest.raises(ValueError):
        validate_brief(brief(layout="<script>"))
    with pytest.raises(ValueError):
        validate_brief(brief(theme="anything"))


def test_default_is_subject_led_not_a_slide_or_implicit_title_card():
    value = {"schema_version": 1, "topic": "글쓰기 준비", "title": "차분한 준비",
             "visual_subject": "창가 책상 위 펼친 노트와 연필",
             "art_direction": "종이 결이 보이는 따뜻한 연필 삽화",
             "article_context": "초고를 준비하는 장면을 보여주는 도입부"}
    normalized = validate_brief(value)
    assert normalized["layout"] == "social-card"
    assert normalized["aspect_ratio"] == "1:1"
    assert normalized["palette"] == "contextual"
    assert normalized["style_profile"] == "balanced-editorial"
    prompt = generation_prompt(value)
    assert "Title and subtitle are metadata" in generation_prompt({**value, "layout": "editorial"})
    assert "presentation slide" in prompt
    assert "창가 책상" in prompt
    with pytest.raises(ValueError, match="visual_subject"):
        validate_brief({key: val for key, val in value.items() if key != "visual_subject"})


def test_personal_style_profile_is_explicit_and_changes_only_visual_guidance():
    value = brief(
        layout="social-card",
        visual_subject="공식 앱 화면을 종이 프레임 안에 배치한 단계 안내",
        style_profile="tactile-howto",
        aspect_ratio="4:5",
    )
    normalized = validate_brief(value)
    assert normalized["style_profile"] == "tactile-howto"
    prompt = generation_prompt(value)
    assert "tactile-howto" in prompt
    assert "cream grid or tactile paper" in prompt
    assert "4:5" in prompt


@pytest.mark.parametrize("layout", ["editorial", "cover", "photo", "social-card"])
def test_local_renderer_does_not_downgrade_editorial_assets_to_cards(tmp_path, layout):
    with pytest.raises(ValueError, match="explicit card or steps"):
        render_template(brief(layout=layout, visual_subject="창가의 노트"), tmp_path / "asset.png")
    assert not (tmp_path / "asset.png").exists()


def test_editorial_brief_rejects_invalid_directions_and_template_palette():
    with pytest.raises(ValueError):
        validate_brief(brief(art_direction="불필요한\n제어 문자"))
    with pytest.raises(ValueError):
        validate_brief(brief(article_context="문" * 301))
    with pytest.raises(ValueError, match="palette"):
        validate_brief(brief(palette="contextual"))
    assert "approved short title" in generation_prompt(brief(layout="cover", visual_subject="질감 있는 종이 표지"))


def test_body_images_support_non_slide_ratios_without_weakening_og(tmp_path):
    path = tmp_path / "illustration.png"
    value = brief(layout="editorial", visual_subject="창가의 노트", aspect_ratio="4:3")
    Image.new("RGB", (1600, 1200), "white").save(path)
    assert check_image(path, value)["technical_pass"]
    assert "1600 x 1200" in generation_prompt(value)
    assert "wrong-aspect-ratio" in check_image(path, brief())["issues"]
    with pytest.raises(ValueError, match="aspect"):
        validate_brief({**value, "role": "og"})
    with pytest.raises(ValueError, match="aspect"):
        validate_brief(brief(aspect_ratio="arbitrary"))


def test_social_card_supports_portrait_composition_and_needs_actual_review(tmp_path):
    value = brief(layout="social-card", visual_subject="노트와 연필 사진, 짧은 핵심 문구", aspect_ratio="4:5")
    path = tmp_path / "card-news.png"
    Image.new("RGB", (1280, 1600), "white").save(path)
    assert check_image(path, value)["status"] == "visual-review-required"
    with pytest.raises(ValueError, match="aspect"):
        validate_brief({**value, "role": "og"})


def test_visual_review_rejects_slide_composition_and_changed_direction(tmp_path):
    from blog_image import policy

    path = tmp_path / "asset.png"
    Image.new("RGB", (1600, 900), "white").save(path)
    value = brief(layout="editorial", visual_subject="창가의 노트")
    checks = dict.fromkeys(policy()["visual_checks"], True)
    checks["clean_composition"] = False
    review = make_review(path, value, checks=checks, reviewer="user")
    assert check_image(path, value, review=review)["issues"] == ["clean_composition"]
    checks["clean_composition"] = True
    review = make_review(path, value, checks=checks, reviewer="user")
    assert check_image(path, {**value, "art_direction": "사진 같은 질감"}, review=review)["status"] == "visual-review-required"


def test_shipped_brief_and_schema_use_social_card_defaults():
    root = Path(__file__).resolve().parents[1] / "plugins/autoseo"
    example = json.loads((root / "examples/blog-image-brief-v1.json").read_text())
    schema = json.loads((root / "schema/blog-image-brief.schema.json").read_text())
    value = validate_brief(example)
    assert value["layout"] == schema["properties"]["layout"]["default"] == "social-card"
    assert value["visual_subject"] and value["art_direction"]
    assert set(value) <= set(schema["properties"])


def test_small_or_corrupt_image_fails_and_large_image_needs_visual_review(tmp_path):
    path = tmp_path / "photo.png"
    Image.new("RGB", (400, 200), "white").save(path)
    assert check_image(path, brief())["status"] == "rejected"
    Image.new("RGB", (1600, 900), "white").save(path)
    report = check_image(path, brief())
    assert report["technical_pass"] is True
    assert report["status"] == "visual-review-required"
    path.write_bytes(b"not an image")
    assert check_image(path, brief())["status"] == "rejected"
    Image.new("RGB", (1600, 900), "white").save(path, format="GIF")
    assert check_image(path, brief())["status"] == "rejected"


def test_review_is_bound_to_exact_image_and_brief(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (1600, 900), "#eeeedd").save(path)
    value = brief()
    checks = {key: True for key in ("topic_match", "clean_composition", "legible_at_mobile",
                                   "no_visual_artifacts", "truthful", "safe_crop")}
    review = make_review(path, value, checks=checks, reviewer="agent-visual")
    assert check_image(path, value, review=review)["status"] == "accepted"
    assert check_image(path, brief(topic="다른 주제"), review=review)["status"] == "visual-review-required"
    Image.new("RGB", (1600, 900), "blue").save(path)
    assert check_image(path, value, review=review)["status"] == "visual-review-required"
    with pytest.raises(ValueError):
        make_review(path, value, checks={**checks, "truthful": "true"}, reviewer="agent-visual")


def test_failed_visual_review_never_passes(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (1600, 900), "white").save(path)
    with pytest.raises(ValueError):
        make_review(path, brief(), checks={}, reviewer="agent-visual")


def test_renderer_rejects_photo_substitution_overwrite_and_overflow(tmp_path):
    with pytest.raises(ValueError, match="photo"):
        render_template(brief(layout="photo"), tmp_path / "photo.png")
    path = tmp_path / "already.png"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError):
        render_template(brief(), path)
    assert path.read_bytes() == b"keep"
    with pytest.raises(ValueError):
        validate_brief(brief(title="한" * 201))
    target = tmp_path / "target.png"
    target.write_bytes(b"original")
    link = tmp_path / "linked.png"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        render_template(brief(), link)
    assert target.read_bytes() == b"original"


def test_document_gate_only_accepts_reviewed_attached_generated_images(tmp_path):
    asset = tmp_path / "hero.png"
    Image.new("RGB", (1600, 900), "white").save(asset)
    document = {"blocks": [{"id": "hero", "type": "photo", "path": str(asset)}],
                "generated_images": [{"path": str(asset), "brief": brief(), "review": {}}]}
    with pytest.raises(ValueError, match="quality"):
        require_image_reviews(document)
    checks = {key: True for key in ("topic_match", "clean_composition", "legible_at_mobile",
                                   "no_visual_artifacts", "truthful", "safe_crop")}
    document["generated_images"][0]["review"] = make_review(asset, brief(), checks=checks, reviewer="user")
    require_image_reviews(document)
    removed = copy.deepcopy(document)
    removed["blocks"] = []
    with pytest.raises(ValueError, match="attached"):
        require_image_reviews(removed)
    # Legacy documents and real user photos remain compatible, not fake-approved.
    require_image_reviews({"blocks": document["blocks"]})
    assert json.dumps(document)


@pytest.mark.parametrize("platform", ["naver", "tistory"])
def test_real_automation_checks_generated_assets_before_writes(tmp_path, platform):
    import naver_document
    import naver_editor
    import tistory_document
    import tistory_editor
    from test_naver_editor import MockEditorDriver
    from test_naver_editor import _document as naver_doc
    from test_tistory_editor import MockTistoryDriver
    from test_tistory_editor import _document as tistory_doc

    asset = tmp_path / "hero.png"
    Image.new("RGB", (1600, 900), "white").save(asset)
    if platform == "naver":
        value = naver_doc()
        value["blocks"].append({"id": "photo", "type": "photo", "path": str(asset)})
        document_module = naver_document
        driver = MockEditorDriver()
        automation = naver_editor.EditorAutomation(naver_editor.CheckpointStore(tmp_path))
        kwargs = {}
    else:
        value = tistory_doc(tmp_path, with_media=False)
        value["blocks"].append({"id": "photo", "type": "image", "media_id": "hero"})
        value["media"] = [{"id": "hero", "path": str(asset), "alt": "테스트 이미지"}]
        document_module = tistory_document
        driver = MockTistoryDriver()
        automation = tistory_editor.TistoryEditorAutomation(tistory_editor.CheckpointStore(tmp_path))
        kwargs = {"prepared_media": {"hero": asset}}
    legacy_hash = document_module.document_hash(value)
    value["generated_images"] = [{"path": str(asset), "brief": brief(), "review": {}}]
    normalized = document_module.validate_document(value)
    assert normalized["generated_images"]
    assert document_module.document_hash(value) != legacy_hash
    with pytest.raises(ValueError, match="quality"):
        automation.apply(value, driver, **kwargs)
    assert driver.calls == []
    assert getattr(driver, "uploads", []) == []


def test_successful_template_and_font_failure_never_claim_visual_pass(tmp_path):
    value = brief(title="A quieter writing routine", subtitle="Choose a topic. Gather evidence. Edit once.")
    # Read-only OS font resources vary by platform; absence must be explicit.
    try:
        result = render_template(value, tmp_path / "card.png")
    except ValueError as exc:
        if "local font" in str(exc):
            pytest.skip("no supported OS font in this environment")
        raise
    assert result["technical_pass"] is True
    assert result["status"] == "visual-review-required"
    assert result["width"] == 1600
    with pytest.raises(ValueError, match="font"):
        render_template(value, tmp_path / "missing.png", font_path=tmp_path / "no-font.ttf")
    assert not (tmp_path / "missing.png").exists()
