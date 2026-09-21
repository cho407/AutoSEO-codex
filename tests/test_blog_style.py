from __future__ import annotations

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
    profile_status,
    resolve_profile,
    save_selection,
    validate_catalog,
    validate_profile_name,
)


def test_catalog_keeps_generic_quality_floor_separate_from_personal_profile() -> None:
    value = validate_catalog(catalog())

    assert value["default_profile"] == "balanced-editorial"
    assert value["profiles"]["balanced-editorial"]["scope"] == "universal"
    assert value["profiles"]["tactile-howto"]["scope"] == "personal"
    assert value["profiles"]["tactile-howto"]["visual"]["hero_ratio"] == "1:1"
    assert value["profiles"]["tactile-howto"]["visual"]["step_ratio"] == "4:5"


def test_profile_selection_defaults_without_creating_personal_data(tmp_path: Path) -> None:
    status = profile_status(tmp_path / "autoseo-data")
    assert status["configured"] is False
    assert status["profile"] == "balanced-editorial"
    assert not (tmp_path / "autoseo-data").exists()
    assert resolve_profile(data_dir=tmp_path / "autoseo-data")["profile"] == "balanced-editorial"


def test_profile_selection_requires_confirmation_and_is_owner_only(tmp_path: Path) -> None:
    data_dir = tmp_path / "autoseo-data"
    with pytest.raises(ValueError, match="confirmation"):
        save_selection("tactile-howto", data_dir=data_dir, confirmed=False)

    path = save_selection("tactile-howto", data_dir=data_dir, confirmed=True)
    assert path.name == "blog-style.json"
    assert load_selection(data_dir=data_dir)["profile"] == "tactile-howto"
    assert profile_status(data_dir)["scope"] == "personal"
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
        save_selection("tactile-howto", data_dir=data_dir, confirmed=True)
    assert target.read_text(encoding="utf-8") == "{}"


def test_only_shipped_profiles_can_be_selected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        validate_profile_name("private-reference")
