#!/usr/bin/env python3
"""
Thin wrapper around the Unlighthouse CLI (https://unlighthouse.dev).

Unlighthouse is an MIT-licensed OSS Lighthouse runner that crawls an
entire site and outputs a single aggregate report. It's the closest
free-tier equivalent to running PageSpeed against every URL on a site
and aggregating the results — a workflow PSI's API quota does not
support without a paid Google Cloud bill.

This wrapper:
  - Validates the target via url_safety before any subprocess starts.
  - Refuses execution unless the caller explicitly acknowledges that the
    third-party crawler has its own network stack and is outside AutoSEO's
    per-request SSRF interception.
  - Invokes an already-installed ``unlighthouse-ci`` executable with
    sensible defaults. It never downloads or installs packages.
  - Captures the JSON summary the CLI writes and returns it parsed
    so autoseo agents can ingest the result without re-running
    Lighthouse.

Prerequisites
=============
Install and trust ``unlighthouse-ci`` yourself, then either place it on
``PATH`` or set ``AUTOSEO_UNLIGHTHOUSE_BIN`` to its executable path.

Usage::

    python scripts/unlighthouse_run.py https://example.com
    python scripts/unlighthouse_run.py https://example.com --json
    python scripts/unlighthouse_run.py https://example.com --device desktop --max-routes 50
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from file_safety import prepare_output_directory, read_text_limited  # noqa: E402
from url_safety import URLSafetyError, validate_url_strict  # noqa: E402

MAX_SUMMARY_BYTES = 20 * 1024 * 1024


def _resolve_unlighthouse() -> tuple[str | None, str | None]:
    """Resolve an explicitly trusted local executable without downloading it."""
    override = os.environ.get("AUTOSEO_UNLIGHTHOUSE_BIN")
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return None, "AUTOSEO_UNLIGHTHOUSE_BIN is not an executable file"
        return str(candidate), None
    executable = shutil.which("unlighthouse-ci")
    if executable:
        return executable, None
    return None, (
        "unlighthouse-ci was not found. Install and review it separately, then "
        "place it on PATH or set AUTOSEO_UNLIGHTHOUSE_BIN. AutoSEO will not "
        "download packages automatically."
    )


def run(
    target: str,
    *,
    device: str = "mobile",
    max_routes: int | None = 200,
    output_dir: str | None = None,
    timeout: int = 600,
    allow_external_crawler: bool = False,
    allow_output_overwrite: bool = False,
) -> dict:
    if not allow_external_crawler:
        return {
            "ok": False,
            "error": (
                "external crawler execution refused: obtain explicit user consent "
                "and pass --allow-external-crawler. Run it in a network-isolated "
                "environment when auditing an untrusted site."
            ),
        }

    try:
        target, _ = validate_url_strict(target)
    except URLSafetyError as exc:
        return {"ok": False, "error": f"url_safety: {exc}"}

    executable, executable_error = _resolve_unlighthouse()
    if executable_error:
        return {"ok": False, "error": executable_error}

    if device not in {"mobile", "desktop"}:
        return {"ok": False, "error": "device must be mobile or desktop"}
    if max_routes is not None and not 1 <= max_routes <= 5000:
        return {"ok": False, "error": "max_routes must be between 1 and 5000"}
    if not 1 <= timeout <= 3600:
        return {"ok": False, "error": "timeout must be between 1 and 3600 seconds"}

    try:
        out_dir = (
            prepare_output_directory(
                output_dir,
                allow_existing_files=allow_output_overwrite,
            )
            if output_dir
            else Path(tempfile.mkdtemp(prefix="autoseo-unlighthouse-"))
        )
    except ValueError as exc:
        return {"ok": False, "error": f"output refused: {exc}"}

    cmd = [
        executable,
        "--site", target,
        "--device", device,
        "--output-path", str(out_dir),
        # Reasonable defaults for a one-shot audit; callers can override.
        "--build-static-files",
    ]
    if max_routes is not None:
        cmd.extend(["--scanner", json.dumps({"maxRoutes": max_routes})])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"unlighthouse timed out after {timeout}s",
                "output_dir": str(out_dir)}
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"unlighthouse-ci invocation failed: {exc}"}

    summary_path = out_dir / "ci-result.json"
    summary: dict = {}
    if summary_path.is_file():
        try:
            summary = json.loads(
                read_text_limited(summary_path, max_bytes=MAX_SUMMARY_BYTES)
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return {"ok": False, "error": f"ci-result.json invalid JSON: {exc}",
                    "output_dir": str(out_dir)}

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "target": target,
        "output_dir": str(out_dir),
        "summary": summary,
        "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Unlighthouse (multi-page Lighthouse) on a site."
    )
    parser.add_argument("target", help="Site URL to crawl (https://example.com).")
    parser.add_argument(
        "--device", choices=("mobile", "desktop"), default="mobile",
    )
    parser.add_argument(
        "--max-routes", type=int, default=200,
        help="Cap the crawl at N URLs (default 200).",
    )
    parser.add_argument(
        "--output-dir", help="Directory for the HTML/JSON report (default temp).",
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="Allow the crawler to write into a non-empty output directory",
    )
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Subprocess timeout in seconds (default 600).",
    )
    parser.add_argument(
        "--allow-external-crawler",
        action="store_true",
        help=(
            "Acknowledge that Unlighthouse follows links and loads subresources "
            "with its own network stack. Use only after explicit user consent."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run(
        args.target,
        device=args.device,
        max_routes=args.max_routes,
        output_dir=args.output_dir,
        timeout=args.timeout,
        allow_external_crawler=args.allow_external_crawler,
        allow_output_overwrite=args.overwrite_output,
    )

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        status = "OK" if result["ok"] else "FAIL"
        print(f"Unlighthouse: {status}")
        print(f"  Target:     {result.get('target', args.target)}")
        print(f"  Output dir: {result.get('output_dir')}")
        if result.get("error"):
            print(f"  Error:      {result['error']}")
        elif result.get("summary"):
            scores = result["summary"].get("scores") or result["summary"].get("score") or {}
            if scores:
                for k, v in scores.items():
                    print(f"  {k:14s} {v}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
