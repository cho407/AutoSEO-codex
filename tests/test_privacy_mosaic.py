from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

import privacy_mosaic  # noqa: E402


def _face(x: int, y: int, width: int, height: int, *, pose: str = "frontal") -> dict:
    return {"x": x, "y": y, "width": width, "height": height, "pose": pose}


def test_background_policy_keeps_one_clear_main_face_and_mosaics_bystanders() -> None:
    faces = [
        _face(40, 80, 40, 40),
        _face(180, 35, 180, 180),
        _face(500, 95, 45, 45, pose="profile"),
    ]

    plan = privacy_mosaic.plan_faces(
        faces,
        image_width=640,
        image_height=360,
        policy={"mode": "background-people"},
    )

    assert plan["main_face_id"] == "face-2"
    assert plan["keep_face_ids"] == ["face-2"]
    assert plan["mosaic_face_ids"] == ["face-1", "face-3"]
    assert plan["review_required"] is False


def test_ambiguous_group_has_no_arbitrary_main_and_defaults_to_privacy() -> None:
    faces = [
        _face(150, 80, 80, 80),
        _face(290, 80, 80, 80),
        _face(430, 80, 80, 80),
    ]

    plan = privacy_mosaic.plan_faces(
        faces,
        image_width=640,
        image_height=360,
        policy={"mode": "background-people"},
    )

    assert plan["main_face_id"] is None
    assert plan["mosaic_face_ids"] == ["face-1", "face-2", "face-3"]
    assert plan["review_required"] is True
    assert plan["review_reason"] == "main-person-ambiguous"


def test_clear_frontal_subject_can_be_main_among_profile_bystanders() -> None:
    faces = [
        _face(100, 80, 90, 90, pose="profile"),
        _face(275, 65, 100, 100, pose="frontal"),
        _face(470, 80, 90, 90, pose="profile"),
    ]

    plan = privacy_mosaic.plan_faces(
        faces,
        image_width=640,
        image_height=360,
        policy={"mode": "background-people"},
    )

    assert plan["main_face_id"] == "face-2"
    assert plan["mosaic_face_ids"] == ["face-1", "face-3"]


def test_explicit_face_and_region_instructions_override_the_default() -> None:
    faces = [
        _face(50, 50, 120, 120),
        _face(230, 40, 150, 150),
        _face(450, 60, 100, 100),
    ]

    plan = privacy_mosaic.plan_faces(
        faces,
        image_width=640,
        image_height=360,
        policy={
            "mode": "selected",
            "keep_face_ids": ["face-1"],
            "mosaic_face_ids": ["face-2"],
            "regions": [{"x": 500, "y": 250, "width": 100, "height": 80}],
        },
    )

    assert plan["main_face_id"] is None
    assert plan["keep_face_ids"] == ["face-1"]
    assert plan["mosaic_face_ids"] == ["face-2"]
    assert plan["regions"] == [
        {"x": 500, "y": 250, "width": 100, "height": 80}
    ]


def test_conflicting_explicit_instructions_are_rejected() -> None:
    with pytest.raises(ValueError, match="both kept and mosaicked"):
        privacy_mosaic.plan_faces(
            [_face(10, 10, 50, 50)],
            image_width=100,
            image_height=100,
            policy={
                "mode": "selected",
                "keep_face_ids": ["face-1"],
                "mosaic_face_ids": ["face-1"],
            },
        )


def test_explicit_main_face_cannot_also_be_mosaicked() -> None:
    with pytest.raises(ValueError, match="main face cannot also be mosaicked"):
        privacy_mosaic.plan_faces(
            [_face(10, 10, 50, 50), _face(70, 10, 20, 20)],
            image_width=120,
            image_height=80,
            policy={
                "mode": "background-people",
                "main_face_id": "face-1",
                "mosaic_face_ids": ["face-1"],
            },
        )


def test_write_preview_is_bound_to_source_bytes_plan_and_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "people.jpg"
    source.write_bytes(b"first-image")
    destination = tmp_path / "people-privacy.jpg"
    plan = privacy_mosaic.plan_faces(
        [_face(10, 10, 50, 50)],
        image_width=100,
        image_height=100,
        policy={"mode": "all"},
    )

    first = privacy_mosaic.write_preview(source, destination, plan)
    source.write_bytes(b"changed-image")
    second = privacy_mosaic.write_preview(source, destination, plan)
    overwrite = privacy_mosaic.write_preview(
        source, destination, plan, overwrite=True
    )

    assert first["approval_required"] is True
    assert first["approval_token"] != second["approval_token"]
    assert first["source_sha256"] != second["source_sha256"]
    assert first["output"] == str(destination.resolve())
    assert second["approval_token"] != overwrite["approval_token"]
    assert overwrite["overwrite_existing"] is True


def test_checkpoint_safe_summary_does_not_contain_source_paths() -> None:
    plan = privacy_mosaic.plan_faces(
        [_face(10, 10, 50, 50), _face(70, 10, 20, 20)],
        image_width=120,
        image_height=80,
        policy={"mode": "background-people", "main_face_id": "face-1"},
    )

    summary = privacy_mosaic.safe_plan_summary(plan)
    encoded = json.dumps(summary)

    assert summary["detected_face_count"] == 2
    assert summary["mosaic_face_count"] == 1
    assert summary["mode"] == "background-people"
    assert summary["padding"] == 0.18
    assert summary["block_size"] == 14
    assert summary["strip_metadata"] is True
    assert "/" not in encoded


def test_apply_plan_pixelates_only_the_selected_region_and_preserves_original(
    tmp_path: Path,
) -> None:
    image_module = pytest.importorskip("PIL.Image")
    source = tmp_path / "gradient.png"
    destination = tmp_path / "gradient-privacy.png"
    image = image_module.new("RGB", (32, 16))
    for x in range(32):
        for y in range(16):
            image.putpixel((x, y), (x * 7 % 255, y * 13 % 255, (x + y) * 5 % 255))
    image.save(source)
    original_bytes = source.read_bytes()
    plan = {
        "schema_version": 1,
        "image_width": 32,
        "image_height": 16,
        "faces": [],
        "main_face_id": None,
        "keep_face_ids": [],
        "mosaic_face_ids": [],
        "regions": [{"x": 0, "y": 0, "width": 16, "height": 16}],
        "padding": 0.0,
        "block_size": 6,
        "strip_metadata": True,
        "review_required": False,
        "review_reason": None,
    }

    privacy_mosaic.apply_plan(source, destination, plan)

    assert source.read_bytes() == original_bytes
    before = image_module.open(source).convert("RGB")
    after = image_module.open(destination).convert("RGB")
    assert before.crop((0, 0, 16, 16)).tobytes() != after.crop((0, 0, 16, 16)).tobytes()
    assert before.crop((16, 0, 32, 16)).tobytes() == after.crop((16, 0, 32, 16)).tobytes()


def test_apply_plan_refuses_a_destination_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    target = tmp_path / "target.png"
    destination = tmp_path / "privacy.png"
    source.write_bytes(b"source")
    target.write_bytes(b"keep")
    destination.symlink_to(target)
    plan = {
        "schema_version": 1,
        "image_width": 1,
        "image_height": 1,
        "faces": [],
        "mosaic_face_ids": [],
        "regions": [],
    }

    with pytest.raises(ValueError, match="symbolic link"):
        privacy_mosaic.apply_plan(source, destination, plan)
    assert target.read_bytes() == b"keep"


def test_local_detector_loads_bundled_cascades_without_network(tmp_path: Path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    pytest.importorskip("cv2")
    source = tmp_path / "blank.png"
    image_module.new("RGB", (96, 64), color=(240, 240, 240)).save(source)

    result = privacy_mosaic.detect_faces(source)

    assert result["image_width"] == 96
    assert result["image_height"] == 64
    assert result["faces"] == []
    assert len(result["source_sha256"]) == 64


def test_metadata_is_stripped_by_default_and_preserved_only_when_requested(
    tmp_path: Path,
) -> None:
    image_module = pytest.importorskip("PIL.Image")
    source = tmp_path / "metadata.jpg"
    stripped = tmp_path / "metadata-stripped.jpg"
    preserved = tmp_path / "metadata-preserved.jpg"
    exif = image_module.Exif()
    exif[315] = "Private Photographer"
    image_module.new("RGB", (16, 16), color=(10, 20, 30)).save(source, exif=exif)
    base = {
        "schema_version": 1,
        "image_width": 16,
        "image_height": 16,
        "faces": [],
        "main_face_id": None,
        "keep_face_ids": [],
        "mosaic_face_ids": [],
        "regions": [],
        "padding": 0.0,
        "block_size": 6,
        "review_required": False,
        "review_reason": None,
    }

    privacy_mosaic.apply_plan(source, stripped, {**base, "strip_metadata": True})
    privacy_mosaic.apply_plan(source, preserved, {**base, "strip_metadata": False})

    assert image_module.open(stripped).getexif().get(315) is None
    assert image_module.open(preserved).getexif().get(315) == "Private Photographer"
