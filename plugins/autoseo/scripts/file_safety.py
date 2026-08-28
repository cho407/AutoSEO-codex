#!/usr/bin/env python3
"""Small, standard-library-only helpers for bounded local file access.

AutoSEO commands commonly accept an input or output path. These helpers keep
those operations inside user-controlled working, home, or temporary folders,
bound input size, and refuse silent overwrites by default.
"""

from __future__ import annotations

import errno
import os
import tempfile
from pathlib import Path
from typing import Iterable, TextIO

DEFAULT_MAX_TEXT_BYTES = 20 * 1024 * 1024


def _allowed_roots() -> tuple[Path, ...]:
    roots = {Path(tempfile.gettempdir()).resolve()}
    working = Path.cwd().resolve()
    if working != Path(working.anchor).resolve():
        roots.add(working)
    try:
        roots.add(Path.home().resolve())
    except RuntimeError:
        pass
    return tuple(sorted(roots, key=str))


def _is_within(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def resolve_user_path(
    raw_path: str | os.PathLike[str],
    *,
    extensions: Iterable[str] | None = None,
) -> Path:
    """Resolve a user path and keep it inside a normal user-writable root."""
    path = Path(raw_path).expanduser().resolve(strict=False)
    if not _is_within(path, _allowed_roots()):
        raise ValueError("path must stay within the working, home, or temporary directory")
    if extensions is not None:
        allowed = {value.lower() for value in extensions}
        if path.suffix.lower() not in allowed:
            raise ValueError(f"path extension must be one of: {sorted(allowed)}")
    return path


def _resolve_output_path(
    raw_path: str | os.PathLike[str],
    *,
    extensions: Iterable[str] | None = None,
) -> Path:
    """Resolve an output path without following its final path component."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    parent = candidate.parent.resolve(strict=False)
    path = parent / candidate.name
    if not _is_within(path, _allowed_roots()):
        raise ValueError("path must stay within the working, home, or temporary directory")
    if extensions is not None:
        allowed = {value.lower() for value in extensions}
        if path.suffix.lower() not in allowed:
            raise ValueError(f"path extension must be one of: {sorted(allowed)}")
    if path.is_symlink():
        raise ValueError("output path must not be a symbolic link")
    return path


def resolve_input_file(
    raw_path: str | os.PathLike[str],
    *,
    extensions: Iterable[str] | None = None,
) -> Path:
    path = resolve_user_path(raw_path, extensions=extensions)
    if not path.is_file():
        raise ValueError("input path must be an existing regular file")
    return path


def read_text_limited(
    raw_path: str | os.PathLike[str],
    *,
    max_bytes: int = DEFAULT_MAX_TEXT_BYTES,
    extensions: Iterable[str] | None = None,
) -> str:
    """Read at most ``max_bytes`` and decode as UTF-8 with replacements."""
    path = resolve_input_file(raw_path, extensions=extensions)
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"input file exceeds the {max_bytes}-byte safety limit")
    return raw.decode("utf-8", errors="replace")


def read_stream_limited(
    stream: TextIO,
    *,
    max_chars: int = DEFAULT_MAX_TEXT_BYTES,
) -> str:
    """Read bounded text from stdin-like streams."""
    value = stream.read(max_chars + 1)
    if len(value) > max_chars:
        raise ValueError(f"input stream exceeds the {max_chars}-character safety limit")
    return value


def write_text_safely(
    raw_path: str | os.PathLike[str],
    content: str,
    *,
    overwrite: bool = False,
    extensions: Iterable[str] | None = None,
) -> Path:
    """Write UTF-8 text, refusing existing files unless explicitly allowed."""
    path = _resolve_output_path(raw_path, extensions=extensions)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise ValueError("output already exists; pass --overwrite to replace it") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("output path must not be a symbolic link") from exc
        raise
    return path


def write_text_atomically(
    raw_path: str | os.PathLike[str],
    content: str,
    *,
    extensions: Iterable[str] | None = None,
) -> Path:
    """Atomically replace a text file without following a destination symlink."""
    path = _resolve_output_path(raw_path, extensions=extensions)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def prepare_output_directory(
    raw_path: str | os.PathLike[str],
    *,
    allow_existing_files: bool = False,
) -> Path:
    """Create or validate an output directory without deleting its contents."""
    path = resolve_user_path(raw_path)
    broad_roots = {Path(path.anchor).resolve(), Path(tempfile.gettempdir()).resolve()}
    try:
        broad_roots.add(Path.home().resolve())
    except RuntimeError:
        pass
    if path in broad_roots:
        raise ValueError("output must be a dedicated subdirectory")
    if path.exists() and not path.is_dir():
        raise ValueError("output directory path points to a file")
    if path.is_dir() and not allow_existing_files:
        try:
            next(path.iterdir())
        except StopIteration:
            pass
        else:
            raise ValueError(
                "output directory is not empty; pass --overwrite-output to allow writes"
            )
    path.mkdir(parents=True, exist_ok=True)
    return path
