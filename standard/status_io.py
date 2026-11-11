"""Bounded regular-file I/O, strict JSON loading, symlink guards, and secret scanning."""

from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, TextIO

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 64

_SENSITIVE_RE = re.compile(
    r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}|"
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}\b|"
    r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}\b|"
    r"\bAK"
    r"IA[0-9A-Z]{16}\b|"
    r"-----BEGIN [A-Z0-9 ]*PRI"
    r"VATE KEY-----"
)


class StatusError(ValueError):
    """Raised when a status transition stream or status.json document violates the contract."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StatusError(f"STATUS-JSON-DUPLICATE-KEY: duplicate object key '{key}'")
        result[key] = value
    return result


def _reject_json_constant(token: str) -> Any:
    raise StatusError(f"STATUS-JSON-NONFINITE: non-finite JSON constant '{token}' is forbidden")


def _parse_finite_float(token: str) -> float:
    parsed = float(token)
    if not math.isfinite(parsed):
        raise StatusError(f"STATUS-JSON-NONFINITE: non-finite JSON number '{token}' is forbidden")
    return parsed


def _parse_finite_int(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > 309:
        raise StatusError("STATUS-JSON-OVERFLOW: integer magnitude exceeds finite range")
    parsed = int(token)
    try:
        ok = math.isfinite(float(parsed))
    except OverflowError:
        ok = False
    if not ok:
        raise StatusError("STATUS-JSON-OVERFLOW: integer magnitude exceeds finite range")
    return parsed


def _check_utf8_str(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StatusError("STATUS-JSON-SURROGATE: lone UTF-16 surrogate is forbidden") from exc


def _validate_json_tree(
    root: Any, max_depth: int = MAX_JSON_DEPTH, *, reject_secrets: bool = False
) -> None:
    if type(max_depth) is not int or max_depth < 1:
        raise StatusError("STATUS-JSON-DEPTH: max_depth must be a positive integer")
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise StatusError(f"STATUS-JSON-DEPTH: JSON nesting depth exceeds {max_depth}")
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise StatusError("STATUS-JSON-KEY: JSON object keys must be strings")
                _check_utf8_str(key)
                if reject_secrets and _SENSITIVE_RE.search(key):
                    raise StatusError("STATUS-SECRET: inline credential material is forbidden")
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            for child in current:
                stack.append((child, depth + 1))
        elif isinstance(current, str):
            _check_utf8_str(current)
            if reject_secrets and _SENSITIVE_RE.search(current):
                raise StatusError("STATUS-SECRET: inline credential material is forbidden")
        elif type(current) is int:
            try:
                ok = math.isfinite(float(current))
            except OverflowError:
                ok = False
            if not ok:
                raise StatusError("STATUS-JSON-OVERFLOW: integer magnitude exceeds finite range")
        elif isinstance(current, float) and not math.isfinite(current):
            raise StatusError("STATUS-JSON-NONFINITE: non-finite float value is forbidden")


def read_regular_bytes(path: str | Path, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    if type(max_bytes) is not int or max_bytes < 1:
        raise StatusError("STATUS-IO-BOUNDS: max_bytes must be a positive integer")
    raw_path = os.fspath(path)
    path_obj = Path(raw_path)
    if not path_obj.is_absolute():
        cur = Path()
        for part in path_obj.parts[:-1]:
            cur = cur / part
            if part not in {".", ".."} and cur.is_symlink():
                raise StatusError(f"STATUS-IO-SYMLINK: symlink ancestor is refused: {cur}")
    abs_path = Path(os.path.abspath(raw_path))
    if any(anc.is_symlink() for anc in abs_path.parents if len(anc.parts) > 2):
        raise StatusError(f"STATUS-IO-SYMLINK: symlink ancestor is refused: {path_obj}")
    try:
        lst = os.lstat(path_obj)
    except OSError as exc:
        raise StatusError(f"STATUS-IO-OPEN: cannot stat regular file {path_obj}: {exc}") from exc
    if stat.S_ISLNK(lst.st_mode):
        raise StatusError(f"STATUS-IO-SYMLINK: symlink files are refused: {path_obj}")
    if not stat.S_ISREG(lst.st_mode):
        raise StatusError(f"STATUS-IO-REGULAR: non-regular files are refused: {path_obj}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path_obj, flags)
    except OSError as exc:
        raise StatusError(f"STATUS-IO-OPEN: cannot open regular file {path_obj}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise StatusError(f"STATUS-IO-REGULAR: non-regular files are refused: {path_obj}")
        if (st.st_dev, st.st_ino) != (lst.st_dev, lst.st_ino):
            raise StatusError(f"STATUS-IO-INODE: file inode changed during open: {path_obj}")
        if st.st_size > max_bytes:
            raise StatusError(f"STATUS-IO-SIZE: file exceeds {max_bytes} bytes: {path_obj}")
        chunks = bytearray()
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > max_bytes:
                raise StatusError(f"STATUS-IO-SIZE: file exceeds {max_bytes} bytes: {path_obj}")
    finally:
        os.close(fd)
    return bytes(chunks)


def load_strict_json(text: str) -> Any:
    if not isinstance(text, str):
        raise StatusError("STATUS-JSON-TYPE: JSON text must be a string")
    _check_utf8_str(text)
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise StatusError(f"STATUS-IO-SIZE: JSON payload exceeds {MAX_FILE_BYTES} bytes")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
            parse_float=_parse_finite_float,
            parse_int=_parse_finite_int,
        )
    except RecursionError as exc:
        raise StatusError("STATUS-JSON-DEPTH: JSON nesting depth exceeds maximum") from exc
    except StatusError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise StatusError(f"STATUS-JSON-PARSE: invalid JSON payload: {exc}") from exc
    _validate_json_tree(parsed)
    return parsed


def _write_json(
    payload: dict[str, Any], stream: TextIO = sys.stdout, *, sort_keys: bool = False
) -> None:
    stream.write(json.dumps(payload, sort_keys=sort_keys, allow_nan=False) + "\n")
