from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

import naver_design  # noqa: E402
import naver_document as native  # noqa: E402


def _profile(**fields):
    return {"schema_version": 1, "preset": "compact-native", **fields}


def _text(identifier="body", role="body", **fields):
    return {"id": identifier, "type": "paragraph", "text": f"Synthetic {identifier}.",
            "design_role": role, **fields}


def _source():
    return _text("source", "source", text="Reference guide.",
                 links=[{"text": "Reference guide", "url": "https://example.org/guide"}])


def _document(blocks=None, profile=True):
    value = {"schema_version": 1, "document_id": "synthetic-design", "title": "Synthetic guide",
             "background": {"type": "none"}, "blocks": blocks if blocks is not None else [_text()],
             "tags": [], "publish_settings": {"mode": "draft"}}
    if profile:
        value["design_profile"] = _profile()
    return value


def _json_file(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def _photo(tmp_path):
    # Synthetic 1x1 PNG; no account data or external asset.
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
    )
    path = tmp_path / "synthetic.png"
    path.write_bytes(data)
    return {"id": "cover", "type": "photo", "path": str(path), "design_role": "cover",
            "design_review": {"approved": True, "sha256": hashlib.sha256(data).hexdigest(),
                              "provenance": "original", "relevance_checked": True}}


def test_semantic_role_sizes_and_media_caption(tmp_path):
    blocks = [_text("answer", "short-answer", style={"size": 15}), _photo(tmp_path),
              _text("caption", "caption", style={"size": 13}),
              _text("question", "question-heading", type="heading", level=2, style={"size": 19}),
              _text(style={"size": 15}),
              _text("minor", "minor-heading", type="heading", level=3, style={"size": 16}),
              _text("detail", "detail", style={"size": 16}),
              _text("sources", "source-heading"), _source()]
    before = copy.deepcopy(blocks)
    plan = native.native_design_plan(_document(blocks))
    styles = {item["role"]: item["style"] for item in plan["paragraphs"]}
    assert styles["question-heading"] == {"size": 19, "bold": True}
    assert styles["minor-heading"] == {"size": 16, "bold": True}
    assert styles["body"] == {"size": 15, "bold": False}
    assert styles["detail"] == {"size": 16, "bold": False}
    assert styles["caption"] == {"size": 13, "bold": False}
    assert styles["source"]["size"] == 13
    assert blocks == before


@pytest.mark.parametrize("size", [14, "15", 15.0, True])
def test_native_role_rejects_unsupported_or_noninteger_size(size):
    with pytest.raises(ValueError, match="size"):
        native.validate_document(_document([_text(style={"size": size})]))
    with pytest.raises(ValueError, match="size"):
        native.validate_design_profile(_profile(roles={"body": {"size": size}}))


def test_list_markers_are_explicit_and_never_rewrite_content():
    document = _document([_text(), _text("neutral", list_marker_style="neutral"),
                          _text("circle", list_marker_style="circle")])
    before = copy.deepcopy(document)
    rows = native.native_design_plan(document)["paragraphs"]
    assert rows[0]["list_marker"] == rows[1]["list_marker"] == {
        "style": "neutral", "prefix": "", "availability": "not-requested", "gate": "none"}
    assert rows[2]["list_marker"] == {
        "style": "circle", "prefix": "● ", "availability": "unavailable",
        "gate": "list-marker-rendering-unverified", "preview_text": "● Synthetic circle."}
    assert document == before


@pytest.mark.parametrize("block", [
    _text(role="quote"), _text(role="body", type="heading", level=2),
    _text(role="summary", type="quote"),
    _text("heading", "minor-heading", type="heading", level=2),
    _text(role="detail", format_role="body"), _text(style={"bold": True}),
])
def test_role_type_level_and_emphasis_conflicts(block):
    with pytest.raises(ValueError, match="conflict"):
        native.validate_document(_document([block, _text("following")]))


@pytest.mark.parametrize("field,value", [
    ("url", "https://example.org/"), ("path", "synthetic.json"), ("selector", ".synthetic"),
])
def test_profile_rejects_unknown_executable_or_location_fields(field, value):
    with pytest.raises(ValueError, match="profile fields"):
        native.validate_design_profile(_profile(**{field: value}))
    with pytest.raises(ValueError, match="styles allow only"):
        native.validate_design_profile(_profile(roles={"body": {field: value}}))


@pytest.mark.parametrize("existing", [False, True])
def test_single_divider_has_exact_source_boundary(existing):
    blocks = [_text()]
    if existing:
        blocks.append({"id": "divider", "type": "divider"})
    blocks += [_text("sources", "source-heading"), _source()]
    document = _document(blocks)
    document["design_profile"]["source_divider"] = "single"
    divider = native.native_design_plan(document)["divider"]
    assert divider["before_block_id"] == "sources"
    assert divider["after_block_id"] == "body"
    assert divider["existing_block_id"] == ("divider" if existing else None)
    assert divider["action"] == ("verify-existing" if existing else "insert-unavailable")
    assert divider["availability"] == "unavailable"


@pytest.mark.parametrize("case", ["source-only", "double", "misplaced", "trailing", "no-source"])
def test_single_divider_rejects_ambiguous_boundaries(case):
    divider = {"id": "divider", "type": "divider"}
    blocks = {
        "source-only": [_source()],
        "double": [_text(), divider, {"id": "second", "type": "divider"}, _source()],
        "misplaced": [divider, _text(), _source()],
        "trailing": [_text(), _source(), _text("trailing")],
        "no-source": [_text(), divider],
    }[case]
    document = _document(blocks)
    document["design_profile"]["source_divider"] = "single"
    with pytest.raises(ValueError, match="source|divider"):
        native.validate_document(document)


@pytest.mark.parametrize("case", ["same-role", "same-content", "spacer"])
def test_duplicate_callouts_and_blank_spacer_lines_are_rejected(case):
    blocks = {
        "same-role": [_text("first", "summary"), _text("second", "summary")],
        "same-content": [_text("first", "summary", text="Repeated content."),
                         _text("second", text="Repeated content.")],
        "spacer": [_text(text="First line.\n\nSecond line.")],
    }[case]
    document = _document(blocks)
    document["design_profile"]["max_callouts"] = 2
    with pytest.raises(ValueError, match="duplicated|spacer"):
        native.validate_document(document)


def test_media_review_is_bound_to_exact_bytes(tmp_path):
    photo = _photo(tmp_path)
    document = _document([photo, _text()])
    original_hash = native.document_hash(document)
    assert native.native_design_plan(document)["media"][0]["availability"] == "unavailable"
    path = Path(photo["path"])
    path.write_bytes(path.read_bytes() + b"changed")
    for operation in (native.validate_document, native.native_design_plan, native.document_hash):
        with pytest.raises(ValueError, match="changed after review"):
            operation(document)
    photo["design_review"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert native.document_hash(document) != original_hash


def test_no_profile_preserves_legacy_formatting_and_requires_opt_in_for_plan():
    document = _document([{"id": "body", "type": "paragraph", "text": "Legacy content.",
                           "style": {"size": 14, "alignment": "center"}}], profile=False)
    normalized = native.validate_document(document)
    assert "design_profile" not in normalized
    assert normalized["blocks"][0]["style"] == document["blocks"][0]["style"]
    with pytest.raises(ValueError, match="explicit design_profile"):
        native.native_design_plan(document)
    document["blocks"][0]["design_role"] = "body"
    with pytest.raises(ValueError, match="explicit design_profile"):
        native.validate_document(document)


@pytest.mark.skipif(os.name != "posix", reason="POSIX private profile contract")
def test_cli_validate_and_plan_are_readonly_and_report_unavailable_gates(tmp_path):
    blocks = [_photo(tmp_path), _text(list_marker_style="circle"),
              _text("quote", "quote", type="quote"), _source()]
    document = _json_file(tmp_path, "document.json", _document(blocks, profile=False))
    profile = _json_file(tmp_path, "profile.json", _profile(source_divider="single"))
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    results = {}
    for command in ("validate", "plan"):
        process = subprocess.run(
            [sys.executable, str(SCRIPTS / "naver_design.py"), command, str(document),
             "--profile", str(profile)], capture_output=True, text=True, check=False,
        )
        assert process.returncode == 0, process.stderr
        assert process.stderr == ""
        results[command] = json.loads(process.stdout)
        assert results[command]["writes_performed"] is False
        assert results[command]["live_publish_ready"] is False
    assert results["validate"]["design_enabled"] is True
    assert results["validate"]["document_hash"] == results["plan"]["document_hash"]
    plan = results["plan"]
    assert plan["paragraphs"][0]["gate"] == "input-buffer-native-formatting-unverified"
    assert plan["paragraphs"][1]["gate"] == "quote-placement-unverified"
    assert plan["paragraphs"][0]["list_marker"]["availability"] == "unavailable"
    assert all(row["availability"] == "unavailable" for row in plan["paragraphs"] + plan["media"])
    assert "upload-unverified" in plan["media"][0]["gate"]
    assert plan["divider"]["availability"] == "unavailable"
    assert "exact-native-boundary-readback-required" in plan["divider"]["gate"]
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_cli_legacy_validation_and_plan_error(tmp_path, capsys):
    document = _json_file(tmp_path, "legacy.json", _document([
        {"id": "body", "type": "paragraph", "text": "Legacy.", "style": {"size": 14}}
    ], profile=False))
    assert naver_design.main(["validate", str(document)]) == 0
    assert json.loads(capsys.readouterr().out)["design_enabled"] is False
    assert naver_design.main(["plan", str(document)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "explicit design_profile" in json.loads(output.err)["message"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX private profile contract")
def test_cli_rejects_conflicting_profiles_and_layout_without_rewriting(tmp_path, capsys):
    value = _document()
    document = _json_file(tmp_path, "document.json", value)
    profile = _json_file(tmp_path, "profile.json", _profile(roles={"body": {"size": 16}}))
    before = document.read_bytes()
    args = ["validate", str(document), "--profile", str(profile)]
    assert naver_design.main(args) == 2
    assert "conflicts with embedded" in json.loads(capsys.readouterr().err)["message"]
    assert document.read_bytes() == before
    # Equivalent explicit and embedded profiles agree even with expanded defaults.
    profile.write_text(json.dumps(native.validate_design_profile(_profile())), encoding="utf-8")
    assert naver_design.main(args) == 0
    capsys.readouterr()
    value.pop("design_profile")
    value["layout_preset"] = "blog-centered"
    document.write_text(json.dumps(value), encoding="utf-8")
    before = document.read_bytes()
    assert naver_design.main(args) == 2
    assert "active layout_preset" in json.loads(capsys.readouterr().err)["message"]
    assert document.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX private profile contract")
@pytest.mark.parametrize("unsafe", ["permissions", "symlink", "hardlink", "directory"])
def test_cli_rejects_unsafe_profile_files(tmp_path, capsys, unsafe):
    document = _json_file(tmp_path, "document.json", _document(profile=False))
    profile = _json_file(tmp_path, "profile.json", _profile())
    if unsafe == "permissions":
        profile.chmod(0o644)
    elif unsafe in {"symlink", "hardlink"}:
        alias = tmp_path / "alias.json"
        if unsafe == "symlink":
            alias.symlink_to(profile)
        else:
            os.link(profile, alias)
        profile = alias
    else:
        profile = tmp_path
    assert naver_design.main(["plan", str(document), "--profile", str(profile)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)
    assert error["status"] == "stopped"
    assert error["writes_performed"] is False
    assert error["live_publish_ready"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX private profile contract")
def test_profile_byte_limit_accepts_boundary_and_rejects_overflow(tmp_path):
    path = _json_file(tmp_path, "profile.json", _profile())
    raw = path.read_bytes()
    path.write_bytes(raw + b" " * (naver_design.MAX_PROFILE_BYTES - len(raw)))
    assert naver_design.read_profile(path)["preset"] == "compact-native"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="64 KiB"):
        naver_design.read_profile(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX private profile contract")
def test_profile_replacement_between_lstat_and_open_is_rejected(tmp_path, monkeypatch):
    path = _json_file(tmp_path, "profile.json", _profile())
    replacement = _json_file(tmp_path, "replacement.json", _profile(roles={"body": {"size": 16}}))
    original_open = os.open

    def replace_then_open(candidate, flags, *args, **kwargs):
        if Path(candidate) == path:
            replacement.replace(path)
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(naver_design.os, "open", replace_then_open)
    with pytest.raises(ValueError, match="changed while opening"):
        naver_design.read_profile(path)


def test_schema_mirrors_native_profile_style_and_block_contract():
    # Structural contract check: jsonschema is optional, not required by this test.
    schema = json.loads((PLUGIN / "schema" / "naver-document.schema.json").read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    profile = definitions["designProfile"]
    assert profile["type"] == "object"
    assert set(profile["properties"]) == native.NATIVE_PROFILE_FIELDS
    assert profile["additionalProperties"] is False
    assert set(profile["required"]) == {"schema_version", "preset"}
    assert profile["properties"]["schema_version"] == {"type": "integer", "const": 1}
    assert profile["properties"]["max_callouts"] == {"type": "integer", "enum": [0, 1, 2]}
    assert profile["properties"]["source_divider"]["enum"] == ["none", "single"]
    assert profile["properties"]["media"]["enum"] == ["optional", "reviewed-cover-and-explainer"]
    style = definitions["nativeStyle"]
    assert set(style["properties"]) == {"size", "bold", "alignment", "line_spacing"}
    assert style["properties"]["size"]["type"] == "integer"
    assert set(style["properties"]["size"]["enum"]) == native.NATIVE_FONT_SIZES
    assert style["properties"]["bold"]["type"] == "boolean"
    assert style["additionalProperties"] is False
    roles = profile["properties"]["roles"]
    assert roles["type"] == "object" and roles["additionalProperties"] is False
    assert set(roles["properties"]) == set(native.NATIVE_ROLE_SIZES)
    for role, definition in roles["properties"].items():
        properties = definition["allOf"][1]["properties"]
        assert set(properties["size"]["enum"]) == native.NATIVE_ROLE_SIZES[role]
        assert properties["bold"]["const"] == (role in native.NATIVE_BOLD_ROLES)
    block = definitions["nativeBlock"]
    assert block["unevaluatedProperties"] is False
    for branch in block["oneOf"]:
        properties = branch["properties"]
        block_type = properties["type"]["const"]
        assert set(properties) | {"id"} == native.NATIVE_BLOCK_FIELDS[block_type]
    review = definitions["designReview"]
    assert set(review["properties"]) == set(review["required"]) == {
        "approved", "sha256", "provenance", "relevance_checked"}
    assert review["properties"]["sha256"]["type"] == "string"
    assert review["properties"]["approved"]["const"] is True
    assert review["properties"]["relevance_checked"]["const"] is True
    assert review["additionalProperties"] is False
