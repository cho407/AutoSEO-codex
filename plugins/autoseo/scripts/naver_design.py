#!/usr/bin/env python3
"""Read-only NaverDocument validation and native design planning.

Usage: naver_design.py {validate,plan} DOCUMENT [--profile PATH]
A separate profile must be a private, owned POSIX file (0600, one link,
no symlink, at most 64 KiB). An embedded profile must agree with it after
validation; neither profiles, document content nor layout presets are rewritten.
Planning reports unverified native editor gates, never live readiness.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from file_safety import read_text_limited
from naver_document import (
    document_hash,
    native_design_plan,
    validate_design_profile,
    validate_document,
)

MAX_PROFILE_BYTES = 64 * 1024


def _check_profile_file(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("profile must be a regular non-symlink file")
    if info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError("profile must belong to the current owner and have one link")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("profile permissions must be exactly 0600")
    if info.st_size > MAX_PROFILE_BYTES:
        raise ValueError("profile exceeds the 64 KiB safety limit")


def read_profile(path: str | Path) -> dict:
    """Check both the named file and the no-follow descriptor before reading."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("safe profile loading requires POSIX O_NOFOLLOW support")
    candidate = Path(path).expanduser()  # Do not resolve away a final symlink.
    before = candidate.lstat()
    _check_profile_file(before)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(candidate, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        _check_profile_file(opened)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("profile changed while opening")
        raw = handle.read(MAX_PROFILE_BYTES + 1)
        _check_profile_file(os.fstat(handle.fileno()))
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("profile exceeds the 64 KiB safety limit")
    return validate_design_profile(json.loads(raw.decode("utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "plan"):
        subparser = commands.add_parser(command)
        subparser.add_argument("document", type=Path)
        subparser.add_argument("--profile", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = json.loads(read_text_limited(args.document, extensions={".json"}))
        if not isinstance(raw, dict):
            raise ValueError("document must be an object")
        if args.profile is not None:
            profile = read_profile(args.profile)
            if "design_profile" in raw:
                embedded = validate_design_profile(raw["design_profile"])
                if embedded != profile:
                    raise ValueError("explicit profile conflicts with embedded design_profile")
            raw = {**raw, "design_profile": profile}
        value = validate_document(raw)
        if args.command == "plan":
            result = {"status": "planned", **native_design_plan(value)}
        else:
            result = {
                "status": "validated",
                "document_id": value["document_id"],
                "design_enabled": "design_profile" in value,
                "writes_performed": False,
                "live_publish_ready": False,
            }
        result["document_hash"] = document_hash(value)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "stopped", "message": str(exc),
                          "writes_performed": False, "live_publish_ready": False}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
