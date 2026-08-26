#!/usr/bin/env python3
"""
IPTC ``DigitalSourceType`` audit + injection for AI-generated images.

Google Merchant Center requires AI-generated product images to carry
the IPTC ``DigitalSourceType: TrainedAlgorithmicMedia`` label. This
script wraps ``exiftool`` to (a) audit a file or directory for the
label, and (b) inject the label where missing.

Why a script and not just docs
==============================
``skills/autoseo-images/SKILL.md`` documents the exiftool one-liner, but
audits should not depend on operators remembering to run it by hand.
This wrapper exposes audit + inject as commands that integrate with
the rest of autoseo's CLI pattern and can be invoked from the
autoseo-images skill or an agent loop.

IPTC vocabulary
===============
- ``trainedAlgorithmicMedia``  fully AI-generated (diffusion-model
  product imagery, AI-generated marketing photos)
- ``compositeSynthetic``       captured + AI-generated mix
- ``digitalCapture``           fully captured photo, no AI element

CLI
===
    python iptc_ai_label.py audit ./images/
    python iptc_ai_label.py audit ./hero.webp
    python iptc_ai_label.py inject ./ai-hero.webp \
        --source-type trainedAlgorithmicMedia --confirm-write
    python iptc_ai_label.py audit ./images/ --json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

from file_safety import resolve_input_file

IPTC_VOCAB = {
    "trainedAlgorithmicMedia": "https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
    "compositeSynthetic": "https://cv.iptc.org/newscodes/digitalsourcetype/compositeSynthetic",
    "algorithmicMedia": "https://cv.iptc.org/newscodes/digitalsourcetype/algorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia": "https://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia",
    "digitalCapture": "https://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture",
    "negativeFilm": "https://cv.iptc.org/newscodes/digitalsourcetype/negativeFilm",
    "positiveFilm": "https://cv.iptc.org/newscodes/digitalsourcetype/positiveFilm",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def _exiftool_path() -> str | None:
    """Resolve the local executable once; never invoke through a shell."""
    value = shutil.which("exiftool")
    if not value:
        return None
    candidate = Path(value).resolve()
    if not candidate.is_file():
        return None
    return str(candidate)


def exiftool_available() -> bool:
    """Return True iff a regular ``exiftool`` executable is on PATH."""
    return _exiftool_path() is not None


def _iter_images(target: Path) -> Iterable[Path]:
    if target.is_file():
        if target.suffix.lower() in IMAGE_EXTENSIONS:
            yield target
        return
    if target.is_dir():
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                yield path


def _read_source_type(image: Path) -> Optional[str]:
    """Read XMP-iptcExt:DigitalSourceType from a single image. None if missing."""
    executable = _exiftool_path()
    if not executable:
        raise RuntimeError("exiftool not installed; install via apt/brew")
    try:
        result = subprocess.run(
            [
                executable,
                "-XMP-iptcExt:DigitalSourceType",
                "-s3",  # value-only
                str(image),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None
    value = result.stdout.strip()
    return value or None


def audit(target: Path) -> dict:
    """Audit a file or directory. Returns a JSON-serializable summary."""
    report: dict = {
        "target": str(target),
        "exiftool_available": exiftool_available(),
        "images": [],
        "summary": {},
    }
    if not target.exists():
        report["summary"] = {"error": "target-not-found"}
        return report
    if not report["exiftool_available"]:
        report["summary"] = {"error": "exiftool-not-installed"}
        return report

    counts: dict[str, int] = {"missing": 0, **{label: 0 for label in IPTC_VOCAB},
                              "other": 0}
    for image in _iter_images(target):
        value = _read_source_type(image)
        if value is None:
            label = "missing"
        else:
            # Vocabulary values are returned either as bare names or as
            # the full IPTC URI; normalise to the bare name.
            short = value.rsplit("/", 1)[-1]
            if short in counts:
                label = short
            else:
                label = "other"
        counts[label] += 1
        report["images"].append({
            "path": str(image),
            "source_type": value,
            "label": label,
        })

    report["summary"] = counts
    report["summary"]["total"] = sum(counts.values())
    return report


def inject(
    image: Path,
    source_type: str,
    *,
    confirmed: bool = False,
    keep_backup: bool = True,
) -> dict:
    """Inject XMP-iptcExt:DigitalSourceType into a single image."""
    out: dict = {"image": str(image), "source_type": source_type, "ok": False, "error": None}
    if not confirmed:
        out["error"] = (
            "file modification refused: inspect the target and retry with "
            "--confirm-write"
        )
        return out
    if source_type not in IPTC_VOCAB:
        out["error"] = (
            f"unknown source_type {source_type!r}; "
            f"valid: {sorted(IPTC_VOCAB)}"
        )
        return out
    executable = _exiftool_path()
    if not executable:
        out["error"] = "exiftool-not-installed"
        return out
    try:
        image = resolve_input_file(image, extensions=IMAGE_EXTENSIONS)
    except ValueError as exc:
        out["error"] = str(exc)
        return out
    uri = IPTC_VOCAB[source_type]
    command = [
        executable,
        f"-XMP-iptcExt:DigitalSourceType={uri}",
    ]
    if not keep_backup:
        command.append("-overwrite_original")
    command.append(str(image))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        out["error"] = "exiftool-timeout"
        return out
    if result.returncode != 0:
        out["error"] = result.stderr.strip() or "exiftool-failed"
        return out
    out["ok"] = True
    return out


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="IPTC DigitalSourceType audit + inject (Merchant Center policy)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Audit file or directory for the IPTC label")
    p_audit.add_argument("target")
    p_audit.add_argument("--json", action="store_true")

    p_inject = sub.add_parser("inject", help="Inject DigitalSourceType into an image")
    p_inject.add_argument("image")
    p_inject.add_argument(
        "--source-type",
        default="trainedAlgorithmicMedia",
        choices=sorted(IPTC_VOCAB),
    )
    p_inject.add_argument(
        "--confirm-write",
        action="store_true",
        help="Confirm modification of the selected image",
    )
    p_inject.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not keep exiftool's _original backup (requires --confirm-write)",
    )
    p_inject.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "audit":
        report = audit(Path(args.target))
        if args.json:
            print(json.dumps(report, indent=2))
            sys.exit(0 if "error" not in report["summary"] else 2)
        print(f"Target: {report['target']}")
        if "error" in report["summary"]:
            print(f"Error: {report['summary']['error']}", file=sys.stderr)
            sys.exit(2)
        print(f"Total images: {report['summary'].get('total')}")
        for label in ("missing", *sorted(IPTC_VOCAB), "other"):
            print(f"  {label}: {report['summary'].get(label, 0)}")
        sys.exit(0)
    elif args.command == "inject":
        out = inject(
            Path(args.image),
            args.source_type,
            confirmed=args.confirm_write,
            keep_backup=not args.no_backup,
        )
        if args.json:
            print(json.dumps(out, indent=2))
            sys.exit(0 if out["ok"] else 2)
        if out["ok"]:
            print(f"Injected {args.source_type} into {args.image}")
            sys.exit(0)
        print(f"Error: {out['error']}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    _cli()
