#!/usr/bin/env python3
"""Local face-aware privacy mosaics with explicit, reviewable policy overrides."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from file_safety import _resolve_output_path, resolve_input_file, resolve_user_path

SCHEMA_VERSION = 1
MAX_IMAGE_BYTES = 50 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
POLICY_MODES = {"background-people", "all", "none", "selected"}
CDN_SAFE_OUTPUT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class MosaicDependencyError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _normalize_box(
    value: object,
    *,
    image_width: int,
    image_height: int,
    field: str,
) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    x = int(_finite_number(value.get("x"), field=f"{field}.x"))
    y = int(_finite_number(value.get("y"), field=f"{field}.y"))
    width = int(_finite_number(value.get("width"), field=f"{field}.width"))
    height = int(_finite_number(value.get("height"), field=f"{field}.height"))
    if width <= 0 or height <= 0:
        raise ValueError(f"{field} width and height must be positive")
    left = max(0, x)
    top = max(0, y)
    right = min(image_width, x + width)
    bottom = min(image_height, y + height)
    if right <= left or bottom <= top:
        raise ValueError(f"{field} is outside the image")
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def _normalize_face(
    value: object,
    *,
    identifier: str,
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    box = _normalize_box(
        value,
        image_width=image_width,
        image_height=image_height,
        field=identifier,
    )
    assert isinstance(value, dict)
    pose = str(value.get("pose") or "frontal").casefold()
    if pose not in {"frontal", "profile"}:
        raise ValueError(f"{identifier}.pose must be frontal or profile")
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
    distance = math.hypot(
        (center_x - image_width / 2) / max(image_width / 2, 1),
        (center_y - image_height / 2) / max(image_height / 2, 1),
    )
    center_score = max(0.0, 1.0 - min(distance, 1.0))
    area = box["width"] * box["height"]
    area_ratio = area / (image_width * image_height)
    score = 0.65 * math.sqrt(area_ratio) + 0.2 * center_score + 0.15 * (
        1.0 if pose == "frontal" else 0.35
    )
    return {
        "id": identifier,
        **box,
        "pose": pose,
        "area_ratio": round(area_ratio, 6),
        "center_score": round(center_score, 6),
        "main_score": round(score, 6),
    }


def _string_id_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of face IDs")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} contains duplicate face IDs")
    return list(value)


def _clear_main_face(faces: list[dict[str, Any]]) -> str | None:
    if not faces:
        return None
    if len(faces) == 1:
        return faces[0]["id"] if faces[0]["area_ratio"] >= 0.006 else None
    ranked = sorted(faces, key=lambda item: item["main_score"], reverse=True)
    first, second = ranked[0], ranked[1]
    first_area = first["width"] * first["height"]
    second_area = second["width"] * second["height"]
    area_dominance = first_area / max(second_area, 1)
    score_margin = first["main_score"] - second["main_score"]
    if first["area_ratio"] < 0.01:
        return None
    frontal_prominence = (
        first["pose"] == "frontal"
        and second["pose"] == "profile"
        and score_margin >= 0.05
    )
    if (
        area_dominance >= 1.4
        or (area_dominance >= 1.15 and score_margin >= 0.08)
        or frontal_prominence
    ):
        return str(first["id"])
    return None


def plan_faces(
    faces: Iterable[object],
    *,
    image_width: int,
    image_height: int,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic face plan without touching image pixels."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    values = [
        _normalize_face(
            face,
            identifier=f"face-{index}",
            image_width=image_width,
            image_height=image_height,
        )
        for index, face in enumerate(faces, 1)
    ]
    raw = dict(policy or {})
    mode = str(raw.get("mode") or "background-people")
    if mode not in POLICY_MODES:
        raise ValueError(f"unsupported mosaic policy mode: {mode}")
    known = {item["id"] for item in values}
    explicit_keep = _string_id_list(raw.get("keep_face_ids"), field="keep_face_ids")
    explicit_mosaic = _string_id_list(
        raw.get("mosaic_face_ids"), field="mosaic_face_ids"
    )
    unknown = (set(explicit_keep) | set(explicit_mosaic)) - known
    if unknown:
        raise ValueError(f"unknown face IDs: {sorted(unknown)}")
    conflicts = set(explicit_keep) & set(explicit_mosaic)
    if conflicts:
        raise ValueError(f"face cannot be both kept and mosaicked: {sorted(conflicts)}")
    explicit_main = raw.get("main_face_id")
    if explicit_main is not None and not isinstance(explicit_main, str):
        raise ValueError("main_face_id must be a face ID or null")
    if explicit_main is not None and explicit_main not in known:
        raise ValueError(f"unknown main face ID: {explicit_main}")
    if explicit_main is not None and explicit_main in explicit_mosaic:
        raise ValueError("main face cannot also be mosaicked")

    padding = _finite_number(raw.get("padding", 0.18), field="padding")
    if not 0 <= padding <= 1:
        raise ValueError("padding must be between 0 and 1")
    block_size = int(_finite_number(raw.get("block_size", 14), field="block_size"))
    if not 2 <= block_size <= 100:
        raise ValueError("block_size must be between 2 and 100")
    strip_metadata = raw.get("strip_metadata", True)
    if not isinstance(strip_metadata, bool):
        raise ValueError("strip_metadata must be boolean")
    regions_raw = raw.get("regions") or []
    if not isinstance(regions_raw, list) or len(regions_raw) > 100:
        raise ValueError("regions must be a list with at most 100 entries")
    regions = [
        _normalize_box(
            region,
            image_width=image_width,
            image_height=image_height,
            field=f"regions[{index}]",
        )
        for index, region in enumerate(regions_raw)
    ]

    inferred_main: str | None = None
    review_required = False
    review_reason: str | None = None
    if mode == "background-people":
        inferred_main = explicit_main or _clear_main_face(values)
        if len(values) > 1 and inferred_main is None:
            review_required = True
            review_reason = "main-person-ambiguous"
    elif explicit_main is not None:
        inferred_main = explicit_main

    keep = set(explicit_keep)
    if inferred_main:
        keep.add(inferred_main)
    if mode == "background-people":
        mosaic = known - keep
    elif mode == "all":
        mosaic = known - keep
    else:
        mosaic = set()
    mosaic.update(explicit_mosaic)
    mosaic.difference_update(keep)

    order = {item["id"]: index for index, item in enumerate(values)}
    keep_ordered = sorted(keep, key=lambda item: order[item])
    mosaic_ordered = sorted(mosaic, key=lambda item: order[item])
    return {
        "schema_version": SCHEMA_VERSION,
        "image_width": image_width,
        "image_height": image_height,
        "mode": mode,
        "faces": values,
        "main_face_id": inferred_main,
        "keep_face_ids": keep_ordered,
        "mosaic_face_ids": mosaic_ordered,
        "regions": regions,
        "padding": round(padding, 4),
        "block_size": block_size,
        "strip_metadata": strip_metadata,
        "review_required": review_required,
        "review_reason": review_reason,
    }


def safe_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    keep = set(plan.get("keep_face_ids") or [])
    mosaic = set(plan.get("mosaic_face_ids") or [])
    return {
        "mode": plan.get("mode"),
        "padding": plan.get("padding"),
        "block_size": plan.get("block_size"),
        "strip_metadata": plan.get("strip_metadata"),
        "detected_face_count": len(plan.get("faces") or []),
        "main_face_id": plan.get("main_face_id"),
        "kept_face_count": len(plan.get("keep_face_ids") or []),
        "mosaic_face_count": len(plan.get("mosaic_face_ids") or []),
        "custom_region_count": len(plan.get("regions") or []),
        "faces": [
            {
                "id": face["id"],
                "x": face["x"],
                "y": face["y"],
                "width": face["width"],
                "height": face["height"],
                "pose": face["pose"],
                "action": (
                    "keep"
                    if face["id"] in keep
                    else "mosaic"
                    if face["id"] in mosaic
                    else "unchanged"
                ),
            }
            for face in plan.get("faces") or []
        ],
        "regions": copy_regions(plan.get("regions") or []),
        "review_required": bool(plan.get("review_required")),
        "review_reason": plan.get("review_reason"),
    }


def copy_regions(regions: Iterable[dict[str, Any]]) -> list[dict[str, int]]:
    return [
        {
            "x": int(region["x"]),
            "y": int(region["y"]),
            "width": int(region["width"]),
            "height": int(region["height"]),
        }
        for region in regions
    ]


def _box_iou(first: dict[str, Any], second: dict[str, Any]) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["width"], second["x"] + second["width"])
    bottom = min(first["y"] + first["height"], second["y"] + second["height"])
    intersection = max(0, right - left) * max(0, bottom - top)
    union = (
        first["width"] * first["height"]
        + second["width"] * second["height"]
        - intersection
    )
    return intersection / union if union else 0.0


def _deduplicate_detections(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        values,
        key=lambda item: (
            item.get("pose") == "frontal",
            item["width"] * item["height"],
        ),
        reverse=True,
    )
    kept: list[dict[str, Any]] = []
    for candidate in ranked:
        if all(_box_iou(candidate, existing) < 0.35 for existing in kept):
            kept.append(candidate)
    return sorted(kept, key=lambda item: (item["x"], item["y"]))


def _load_oriented_image(
    path: Path, *, preserve_alpha: bool = False
) -> tuple[Any, int, int]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise MosaicDependencyError(
            "Pillow is required; install AutoSEO with `--with image`"
        ) from exc
    try:
        with Image.open(path) as source:
            oriented_source = ImageOps.exif_transpose(source)
            mode = "RGBA" if preserve_alpha and "A" in oriented_source.getbands() else "RGB"
            oriented = oriented_source.convert(mode)
            return oriented.copy(), oriented.width, oriented.height
    except Exception as exc:
        raise ValueError("input is not a supported readable image") from exc


def detect_faces(raw_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Detect local frontal and profile faces without network or model downloads."""
    path = resolve_input_file(raw_path, extensions=IMAGE_EXTENSIONS)
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds the {MAX_IMAGE_BYTES}-byte safety limit")
    image, width, height = _load_oriented_image(path)
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise MosaicDependencyError(
            "OpenCV is required; install AutoSEO with `--with image`"
        ) from exc
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    minimum = max(24, min(width, height) // 25)
    detections: list[dict[str, Any]] = []

    def run(cascade_name: str, *, pose: str, matrix: Any, mirrored: bool = False) -> None:
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / cascade_name))
        if cascade.empty():
            raise MosaicDependencyError(f"OpenCV cascade is unavailable: {cascade_name}")
        for x, y, face_width, face_height in cascade.detectMultiScale(
            matrix,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(minimum, minimum),
        ):
            normalized_x = width - int(x) - int(face_width) if mirrored else int(x)
            detections.append(
                {
                    "x": normalized_x,
                    "y": int(y),
                    "width": int(face_width),
                    "height": int(face_height),
                    "pose": pose,
                }
            )

    run("haarcascade_frontalface_default.xml", pose="frontal", matrix=gray)
    run("haarcascade_profileface.xml", pose="profile", matrix=gray)
    run(
        "haarcascade_profileface.xml",
        pose="profile",
        matrix=cv2.flip(gray, 1),
        mirrored=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": _sha256_file(path),
        "image_width": width,
        "image_height": height,
        "faces": _deduplicate_detections(detections),
    }


def analyze_image(
    raw_path: str | os.PathLike[str],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_policy = dict(policy or {})
    mode = str(raw_policy.get("mode") or "background-people")
    needs_face_detection = mode in {"background-people", "all"} or any(
        raw_policy.get(field)
        for field in ("main_face_id", "keep_face_ids", "mosaic_face_ids")
    )
    if needs_face_detection:
        detection = detect_faces(raw_path)
    else:
        path = resolve_input_file(raw_path, extensions=IMAGE_EXTENSIONS)
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(f"image exceeds the {MAX_IMAGE_BYTES}-byte safety limit")
        _, width, height = _load_oriented_image(path)
        detection = {
            "schema_version": SCHEMA_VERSION,
            "source_sha256": _sha256_file(path),
            "image_width": width,
            "image_height": height,
            "faces": [],
        }
    plan = plan_faces(
        detection["faces"],
        image_width=detection["image_width"],
        image_height=detection["image_height"],
        policy=raw_policy,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": detection["source_sha256"],
        "plan": plan,
        "summary": safe_plan_summary(plan),
    }


def _expanded_box(
    box: dict[str, Any], *, width: int, height: int, padding: float
) -> tuple[int, int, int, int]:
    horizontal = int(round(box["width"] * padding))
    vertical = int(round(box["height"] * padding))
    left = max(0, int(box["x"]) - horizontal)
    top = max(0, int(box["y"]) - vertical)
    right = min(width, int(box["x"] + box["width"]) + horizontal)
    bottom = min(height, int(box["y"] + box["height"]) + vertical)
    return left, top, right, bottom


def _pixelate(image: Any, box: tuple[int, int, int, int], block_size: int) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise MosaicDependencyError(
            "Pillow is required; install AutoSEO with `--with image`"
        ) from exc
    left, top, right, bottom = box
    region = image.crop(box)
    reduced = region.resize(
        (max(1, (right - left) // block_size), max(1, (bottom - top) // block_size)),
        resample=Image.Resampling.BILINEAR,
    )
    mosaic = reduced.resize((right - left, bottom - top), resample=Image.Resampling.NEAREST)
    image.paste(mosaic, (left, top))


def _safe_output_path(raw_path: str | os.PathLike[str]) -> Path:
    return _resolve_output_path(raw_path, extensions=CDN_SAFE_OUTPUT_EXTENSIONS)


def _preserved_metadata(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise MosaicDependencyError(
            "Pillow is required; install AutoSEO with `--with image`"
        ) from exc
    with Image.open(path) as source:
        oriented = ImageOps.exif_transpose(source)
        metadata: dict[str, Any] = {}
        exif = oriented.getexif()
        if exif:
            exif[274] = 1
            metadata["exif"] = exif.tobytes()
        if source.info.get("icc_profile"):
            metadata["icc_profile"] = source.info["icc_profile"]
        return metadata


def apply_plan(
    raw_source: str | os.PathLike[str],
    raw_output: str | os.PathLike[str],
    plan: dict[str, Any],
    *,
    overwrite: bool = False,
) -> Path:
    source = resolve_input_file(raw_source, extensions=IMAGE_EXTENSIONS)
    output = _safe_output_path(raw_output)
    if source.resolve() == output.resolve():
        raise ValueError("privacy output must not overwrite the original image")
    if output.exists() and not overwrite:
        raise ValueError("output already exists; pass --overwrite to replace it")
    image, width, height = _load_oriented_image(source, preserve_alpha=True)
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("mosaic plan schema_version must be 1")
    if plan.get("image_width") != width or plan.get("image_height") != height:
        raise ValueError("mosaic plan dimensions do not match the current image")
    block_size = int(plan.get("block_size", 14))
    padding = float(plan.get("padding", 0.18))
    faces = {item["id"]: item for item in plan.get("faces") or []}
    for identifier in plan.get("mosaic_face_ids") or []:
        if identifier not in faces:
            raise ValueError(f"mosaic plan references an unknown face: {identifier}")
        _pixelate(
            image,
            _expanded_box(faces[identifier], width=width, height=height, padding=padding),
            block_size,
        )
    for region in plan.get("regions") or []:
        box = _normalize_box(
            region,
            image_width=width,
            image_height=height,
            field="region",
        )
        _pixelate(
            image,
            (box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]),
            block_size,
        )

    save_metadata = (
        {} if plan.get("strip_metadata", True) else _preserved_metadata(source)
    )
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        output.parent.chmod(0o700)
    except OSError:
        pass
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}-", suffix=output.suffix, dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        suffix = output.suffix.casefold()
        if suffix in {".jpg", ".jpeg"}:
            jpeg_image = image.convert("RGB") if image.mode != "RGB" else image
            jpeg_image.save(
                temporary,
                format="JPEG",
                quality=92,
                optimize=True,
                **save_metadata,
            )
        elif suffix == ".webp":
            image.save(
                temporary,
                format="WEBP",
                quality=90,
                method=6,
                **save_metadata,
            )
        else:
            image.save(temporary, format="PNG", optimize=True, **save_metadata)
        temporary.chmod(0o600)
        if output.exists():
            if not overwrite:
                raise ValueError("output already exists; pass --overwrite to replace it")
            if output.is_symlink():
                raise ValueError("output path must not be a symbolic link")
            os.replace(temporary, output)
        else:
            try:
                os.link(temporary, output)
            except FileExistsError as exc:
                raise ValueError(
                    "output already exists; pass --overwrite to replace it"
                ) from exc
            temporary.unlink()
        output.chmod(0o600)
        return output
    finally:
        temporary.unlink(missing_ok=True)


def write_preview(
    raw_source: str | os.PathLike[str],
    raw_output: str | os.PathLike[str],
    plan: dict[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    source = resolve_input_file(raw_source)
    output = _safe_output_path(raw_output)
    source_sha256 = _sha256_file(source)
    material = json.dumps(
        {
            "action": "write-privacy-derivative",
            "source_sha256": source_sha256,
            "output": str(output),
            "output_exists": output.exists(),
            "overwrite_existing": overwrite,
            "plan": plan,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "approval_required": True,
        "action": "write-privacy-derivative",
        "source_sha256": source_sha256,
        "output": str(output),
        "output_exists": output.exists(),
        "overwrite_existing": overwrite,
        "plan": safe_plan_summary(plan),
        "approval_token": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
    }


def _default_data_dir() -> Path:
    configured = os.environ.get("AUTOSEO_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "autoseo").resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return (base / "autoseo").resolve()
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "autoseo"
    ).resolve()


def derived_output_path(
    raw_source: str | os.PathLike[str],
    plan: dict[str, Any],
    *,
    data_dir: str | os.PathLike[str] | None = None,
) -> Path:
    source = resolve_input_file(raw_source, extensions=IMAGE_EXTENSIONS)
    base = Path(data_dir) if data_dir is not None else _default_data_dir()
    directory = resolve_user_path(base / "privacy-images")
    material = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        (_sha256_file(source) + "\0" + material).encode("utf-8")
    ).hexdigest()[:16]
    suffix = source.suffix.casefold()
    if suffix not in CDN_SAFE_OUTPUT_EXTENSIONS:
        suffix = ".png"
    return directory / f"{source.stem}-privacy-{digest}{suffix}"


def _policy_from_args(args: argparse.Namespace) -> dict[str, Any]:
    regions = []
    for value in args.region or []:
        try:
            x, y, width, height = (int(part.strip()) for part in value.split(","))
        except (TypeError, ValueError) as exc:
            raise ValueError("--region must use x,y,width,height") from exc
        regions.append({"x": x, "y": y, "width": width, "height": height})
    return {
        "mode": args.policy,
        "main_face_id": args.main_face,
        "keep_face_ids": args.keep_face or [],
        "mosaic_face_ids": args.mosaic_face or [],
        "regions": regions,
        "padding": args.padding,
        "block_size": args.block_size,
        "strip_metadata": not args.keep_metadata,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("analyze", "apply"):
        child = sub.add_parser(command)
        child.add_argument("image", type=Path)
        child.add_argument("--policy", choices=sorted(POLICY_MODES), default="background-people")
        child.add_argument("--main-face")
        child.add_argument("--keep-face", action="append")
        child.add_argument("--mosaic-face", action="append")
        child.add_argument("--region", action="append")
        child.add_argument("--padding", type=float, default=0.18)
        child.add_argument("--block-size", type=int, default=14)
        child.add_argument("--keep-metadata", action="store_true")
    apply = sub.choices["apply"]
    apply.add_argument("--output", type=Path)
    apply.add_argument("--approval-token")
    apply.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        analysis = analyze_image(args.image, policy=_policy_from_args(args))
        if args.command == "analyze":
            print(json.dumps(analysis, ensure_ascii=False, indent=2))
            return 0
        output = args.output or derived_output_path(
            args.image, analysis["plan"], data_dir=args.data_dir
        )
        preview = write_preview(
            args.image, output, analysis["plan"], overwrite=args.overwrite
        )
        if args.approval_token != preview["approval_token"]:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 4
        result = apply_plan(
            args.image,
            output,
            analysis["plan"],
            overwrite=args.overwrite,
        )
        print(
            json.dumps(
                {"schema_version": 1, "output": str(result), **analysis["summary"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (MosaicDependencyError, OSError, RuntimeError, ValueError) as exc:
        print(f"Privacy mosaic stopped safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
