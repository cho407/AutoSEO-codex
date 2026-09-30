from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/autoseo/scripts"))

from blog_style import (  # noqa: E402
    catalog,
    load_selection,
    main,
    profile_status,
    resolve_profile,
    save_file_selection,
    save_selection,
    validate_local_profile,
    validate_profile_name,
    validate_selection,
)


def local_profile(name: str = "synthetic-style") -> dict:
    definition = copy.deepcopy(catalog()["profiles"]["balanced-editorial"])
    definition.update(scope="personal", label="Synthetic test style")
    definition["visual"].update(primary="#123456", accent="#ABCDEF", step_ratio="4:5")
    return {"schema_version": 1, "kind": "BlogStyleLocalProfile", "name": name, "definition": definition}


def private_profile(tmp_path: Path, value: dict | None = None) -> Path:
    path = tmp_path / "private-profile.json"
    path.write_text(json.dumps(value or local_profile()), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_profile_selection_defaults_without_creating_personal_data(tmp_path: Path) -> None:
    status = profile_status(tmp_path / "autoseo-data")
    assert status["configured"] is False
    assert status["profile"] == "balanced-editorial"
    assert not (tmp_path / "autoseo-data").exists()
    assert resolve_profile(data_dir=tmp_path / "autoseo-data")["profile"] == "balanced-editorial"


def test_profile_selection_requires_confirmation_and_is_owner_only(tmp_path: Path) -> None:
    data_dir = tmp_path / "autoseo-data"
    with pytest.raises(ValueError, match="confirmation"):
        save_selection("balanced-editorial", data_dir=data_dir, confirmed=False)

    path = save_selection("balanced-editorial", data_dir=data_dir, confirmed=True)
    assert path.name == "blog-style.json"
    assert load_selection(data_dir=data_dir)["profile"] == "balanced-editorial"
    assert profile_status(data_dir)["scope"] == "universal"
    selected = resolve_profile(data_dir=data_dir)
    assert selected["profile"] == "balanced-editorial"
    assert selected["text"]["source_alignment"] == "left"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"schema_version", "kind", "profile", "confirmed_at"}


def test_profile_selection_rejects_symlink_destination(tmp_path: Path) -> None:
    data_dir = tmp_path / "autoseo-data"
    data_dir.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("{}", encoding="utf-8")
    (data_dir / "blog-style.json").symlink_to(target)

    with pytest.raises(ValueError, match="symbolic link"):
        save_selection("balanced-editorial", data_dir=data_dir, confirmed=True)
    assert target.read_text(encoding="utf-8") == "{}"


def test_only_shipped_profiles_can_be_selected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        validate_profile_name("private-reference", data_dir=tmp_path / "isolated-data")



def test_local_file_requires_confirmation_and_stays_external(tmp_path: Path) -> None:
    file = private_profile(tmp_path)
    data_dir = tmp_path / "data"
    original = file.read_bytes()
    with pytest.raises(ValueError, match="confirmation"):
        save_file_selection(file, data_dir=data_dir, confirmed=False)
    assert not data_dir.exists()
    with pytest.raises(ValueError, match="unsupported"):
        validate_profile_name("synthetic-style", data_dir=data_dir)
    saved = save_file_selection(file, data_dir=data_dir, confirmed=True)
    selection = load_selection(data_dir)
    assert selection["profile"] == "synthetic-style"
    assert selection["profile_file"] == str(file.absolute())
    assert selection["profile_sha256"] == hashlib.sha256(original).hexdigest()
    assert selection["confirmed_at"]
    assert set(json.loads(saved.read_text())) == {
        "schema_version", "kind", "profile", "confirmed_at", "profile_file", "profile_sha256"
    }
    assert file.read_bytes() == original
    assert resolve_profile("synthetic-style", data_dir=data_dir)["visual"]["primary"] == "#123456"
    assert validate_profile_name("synthetic-style", data_dir=data_dir) == "synthetic-style"
    assert profile_status(data_dir)["scope"] == "personal"
    with pytest.raises(ValueError, match="match"):
        resolve_profile("other-style", data_dir=data_dir)
    save_selection("balanced-editorial", data_dir=data_dir, confirmed=True)
    assert "profile_file" not in load_selection(data_dir)
    with pytest.raises(ValueError, match="unsupported"):
        validate_profile_name("synthetic-style", data_dir=data_dir)


@pytest.mark.parametrize("failure", ["missing", "changed", "invalid", "renamed"])
def test_selected_local_file_fails_closed(tmp_path: Path, failure: str) -> None:
    file = private_profile(tmp_path)
    data_dir = tmp_path / "data"
    save_file_selection(file, data_dir=data_dir, confirmed=True)
    if failure == "missing":
        file.unlink()
    elif failure == "invalid":
        file.write_text("{}", encoding="utf-8")
    elif failure == "renamed":
        file.write_text(json.dumps(local_profile("renamed-style")), encoding="utf-8")
    else:
        value = local_profile()
        value["definition"]["visual"]["primary"] = "#654321"
        file.write_text(json.dumps(value), encoding="utf-8")
    status = profile_status(data_dir)
    assert status["configured"] is True
    assert status["valid"] is False
    assert "profile" not in status
    with pytest.raises((ValueError, OSError)):
        resolve_profile(data_dir=data_dir)
    with pytest.raises((ValueError, OSError)):
        validate_profile_name("synthetic-style", data_dir=data_dir)
    if failure == "changed":
        save_file_selection(file, data_dir=data_dir, confirmed=True)
        assert resolve_profile(data_dir=data_dir)["visual"]["primary"] == "#654321"


def test_name_only_non_catalog_selection_requires_migration(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "blog-style.json").write_text(json.dumps({
        "schema_version": 1, "kind": "BlogStyleSelection",
        "profile": "retired-personal", "confirmed_at": "2026-01-01T00:00:00Z",
    }))
    assert profile_status(data_dir)["valid"] is False
    assert "migration required" in profile_status(data_dir)["error"]
    with pytest.raises(ValueError, match="migration required"):
        resolve_profile(data_dir=data_dir)
    file = private_profile(tmp_path, local_profile("retired-personal"))
    save_file_selection(file, data_dir=data_dir, confirmed=True)
    assert resolve_profile(data_dir=data_dir)["scope"] == "personal"


@pytest.mark.parametrize("link", ["symbolic", "hard", "parent"])
def test_local_profile_rejects_links(tmp_path: Path, link: str) -> None:
    file = private_profile(tmp_path)
    linked = tmp_path / "linked.json"
    if link == "symbolic":
        linked.symlink_to(file)
    elif link == "hard":
        os.link(file, linked)
    else:
        directory = tmp_path / "linked-dir"
        directory.symlink_to(tmp_path, target_is_directory=True)
        linked = directory / file.name
    with pytest.raises(ValueError, match="link"):
        save_file_selection(linked, data_dir=tmp_path / "data", confirmed=True)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode checks")
@pytest.mark.parametrize("mode", [0o400, 0o640, 0o644, 0o1600])
def test_local_profile_rejects_non_private_modes(tmp_path: Path, mode: int) -> None:
    file = private_profile(tmp_path)
    file.chmod(mode)
    with pytest.raises(ValueError, match="0600"):
        save_file_selection(file, data_dir=tmp_path / "data", confirmed=True)


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership check")
def test_local_profile_rejects_other_owner(tmp_path: Path, monkeypatch) -> None:
    file = private_profile(tmp_path)
    monkeypatch.setattr(os, "getuid", lambda: file.stat().st_uid + 1)
    with pytest.raises(ValueError, match="owner"):
        save_file_selection(file, data_dir=tmp_path / "data", confirmed=True)


def test_local_profile_bounds_regular_file_and_private_location(tmp_path: Path) -> None:
    file = private_profile(tmp_path)
    raw = file.read_bytes()
    file.write_bytes(raw + b" " * (65536 - len(raw)))
    save_file_selection(file, data_dir=tmp_path / "data", confirmed=True)
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(ValueError, match="65536"):
        save_file_selection(file, data_dir=tmp_path / "data", confirmed=True)
    with pytest.raises(ValueError, match="regular"):
        save_file_selection(tmp_path, data_dir=tmp_path / "data", confirmed=True)
    with pytest.raises(ValueError, match="repository"):
        save_file_selection(ROOT / "plugins/autoseo/data/blog-style-profiles.json", confirmed=True)
    cache = tmp_path / ".cache"
    cache.mkdir()
    with pytest.raises(ValueError, match="cache"):
        save_file_selection(private_profile(cache), data_dir=tmp_path / "data", confirmed=True)


def test_cli_set_file_and_invalid_status(tmp_path: Path, capsys) -> None:
    file = private_profile(tmp_path)
    args = ["--data-dir", str(tmp_path / "data")]
    with pytest.raises(SystemExit) as error:
        main([*args, "set-file", str(file)])
    assert error.value.code == 2
    capsys.readouterr()
    assert main([*args, "set-file", str(file), "--confirm"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["profile_file"] == str(file)
    file.unlink()
    assert main([*args, "status"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is False


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("name", "../unsafe"), ("name", "balanced-editorial"),
    ("definition.scope", "universal"), ("definition.selector", "#editor"),
    ("definition.text.script", "execute"), ("definition.text.body_size", True),
    ("definition.text.body_size", 9), ("definition.text.body_size", 16.5),
    ("definition.text.body_line_spacing", 4), ("definition.visual.primary", "red"),
    ("definition.visual.hero_ratio", "arbitrary"), ("definition.visual.selector", "body"),
    ("definition.keep", ["x"] * 21), ("definition.description", "x" * 501),
    ("definition.description", " " * 500 + "x"), ("definition.visual.composition", []),
])
def test_local_profile_schema_and_runtime_reject_invalid_data(field: str, value) -> None:
    profile = local_profile()
    target = profile
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    with pytest.raises(ValueError):
        validate_local_profile(profile)
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "plugins/autoseo/schema/blog-style-local-profile.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(profile)


def test_local_and_generic_selections_agree_with_schema(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_dir = ROOT / "plugins/autoseo/schema"
    profile = local_profile()
    jsonschema.Draft202012Validator(json.loads(
        (schema_dir / "blog-style-local-profile.schema.json").read_text()
    )).validate(profile)
    file = private_profile(tmp_path, profile)
    data_dir = tmp_path / "data"
    validator = jsonschema.Draft202012Validator(json.loads(
        (schema_dir / "blog-style-selection.schema.json").read_text()
    ), format_checker=jsonschema.FormatChecker())
    for save in (
        lambda: save_selection("balanced-editorial", data_dir=data_dir, confirmed=True),
        lambda: save_file_selection(file, data_dir=data_dir, confirmed=True),
    ):
        save()
        selection = load_selection(data_dir)
        validator.validate(selection)
        for change in ({"profile_file": "relative.json"}, {"profile_sha256": "bad"}, {"extra": 1}):
            invalid = {**selection, **change}
            with pytest.raises(ValueError):
                validate_selection(invalid)
            with pytest.raises(jsonschema.ValidationError):
                validator.validate(invalid)


def test_invalid_selection_paths_report_invalid_instead_of_default(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    selection = data_dir / "blog-style.json"
    selection.symlink_to(tmp_path / "missing.json")
    assert profile_status(data_dir)["valid"] is False
    with pytest.raises(ValueError, match="symbolic link"):
        resolve_profile(data_dir=data_dir)
    selection.unlink()
    selection.mkdir()
    assert profile_status(data_dir)["valid"] is False
    with pytest.raises(ValueError):
        resolve_profile(data_dir=data_dir)
