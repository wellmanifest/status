#!/usr/bin/env python3
"""Dependency-free validator/projector for Wellmanifest status-cycle JSONL and status.json."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
import tempfile
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, TextIO

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_EVIDENCE_REFS = 64
ENVELOPE_KEYS = {"schema", "recordType", "sequence", "dsl", "correlationId", "payload"}
DSL_KEYS = {"manifestId", "schemaRef", "grammarRef"}
CODE = re.compile(r"\A[A-Z][A-Z0-9_]{2,63}\Z")
DATE_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
ALLOWED_SYSTEM_STATUSES = {
    "operational",
    "degraded",
    "ddos_mitigation",
    "maintenance",
    "major_outage",
}


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


def _check_utf8_str(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StatusError("STATUS-JSON-SURROGATE: lone UTF-16 surrogate is forbidden") from exc


def _validate_json_tree(root: Any, max_depth: int = MAX_JSON_DEPTH) -> None:
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
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            for child in current:
                stack.append((child, depth + 1))
        elif isinstance(current, str):
            _check_utf8_str(current)
        elif type(current) is int:
            try:
                ok = math.isfinite(float(current))
            except OverflowError:
                ok = False
            if not ok:
                raise StatusError("STATUS-JSON-OVERFLOW: integer magnitude exceeds finite range")
        elif isinstance(current, float) and not math.isfinite(current):
            raise StatusError("STATUS-JSON-NONFINITE: non-finite float value is forbidden")


def read_regular_bytes(path: Path, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    if type(max_bytes) is not int or max_bytes < 1:
        raise StatusError("STATUS-IO-BOUNDS: max_bytes must be a positive integer")
    if not path.is_absolute():
        cur = Path()
        for part in path.parts[:-1]:
            cur = cur / part
            if cur.is_symlink():
                raise StatusError(f"STATUS-IO-SYMLINK: symlink ancestor is refused: {cur}")
    elif any(anc.is_symlink() for anc in path.parents if len(anc.parts) > 2):
        raise StatusError(f"STATUS-IO-SYMLINK: symlink ancestor is refused: {path}")
    try:
        lst = os.lstat(path)
    except OSError as exc:
        raise StatusError(f"STATUS-IO-OPEN: cannot stat regular file {path}: {exc}") from exc
    if stat.S_ISLNK(lst.st_mode):
        raise StatusError(f"STATUS-IO-SYMLINK: symlink files are refused: {path}")
    if not stat.S_ISREG(lst.st_mode):
        raise StatusError(f"STATUS-IO-REGULAR: non-regular files are refused: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise StatusError(f"STATUS-IO-OPEN: cannot open regular file {path}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise StatusError(f"STATUS-IO-REGULAR: non-regular files are refused: {path}")
        if (st.st_dev, st.st_ino) != (lst.st_dev, lst.st_ino):
            raise StatusError(f"STATUS-IO-INODE: file inode changed during open: {path}")
        if st.st_size > max_bytes:
            raise StatusError(f"STATUS-IO-SIZE: file exceeds {max_bytes} bytes: {path}")
        chunks = bytearray()
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > max_bytes:
                raise StatusError(f"STATUS-IO-SIZE: file exceeds {max_bytes} bytes: {path}")
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
        )
    except RecursionError as exc:
        raise StatusError("STATUS-JSON-DEPTH: JSON nesting depth exceeds maximum") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise StatusError(f"STATUS-JSON-PARSE: invalid JSON payload: {exc}") from exc
    _validate_json_tree(parsed)
    return parsed


@lru_cache(maxsize=1)
def _contract() -> tuple[dict[str, dict[str, set[str]]], set[str], set[str]]:
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "status.contract.json"
    bundle = load_strict_json(read_regular_bytes(contract_path).decode("utf-8", errors="strict"))
    profiles = {
        name: {state: set(targets) for state, targets in spec["transitions"].items()}
        for name, spec in bundle["profiles"].items()
    }
    return profiles, set(bundle["payloadFields"]), set(bundle["runtimeOwnedFields"])


PROFILES, PAYLOAD_KEYS, RUNTIME_FIELDS = _contract()


def _non_empty_str(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= 500
        and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    )


def validate_stream(path: Path) -> dict[str, str]:
    raw = read_regular_bytes(path)
    if not raw or not raw.endswith(b"\n") or b"\r" in raw or raw.startswith(b"\xef\xbb\xbf"):
        raise StatusError("STATUS-JSONL-FRAMING: require non-empty UTF-8 LF-terminated JSONL")
    state: dict[tuple[str, str], str] = {}
    for sequence, raw_line in enumerate(raw.split(b"\n")[:-1], 1):
        if not raw_line:
            raise StatusError("STATUS-JSONL-BLANK: blank line")
        line = raw_line.decode("utf-8", errors="strict")
        value = load_strict_json(line)
        if not isinstance(value, dict) or set(value) != ENVELOPE_KEYS:
            raise StatusError("STATUS-ENVELOPE: invalid wellmanifest.jsonl candidate")
        if (
            value["schema"] != "wellmanifest.jsonl/candidate/v1"
            or value["recordType"] != "status.transition"
            or type(value["sequence"]) is not int
            or value["sequence"] != sequence
        ):
            raise StatusError("STATUS-ENVELOPE: schema, type or sequence mismatch")
        dsl = value["dsl"]
        if (
            not isinstance(dsl, dict)
            or set(dsl) != DSL_KEYS
            or not all(_non_empty_str(dsl[k]) for k in DSL_KEYS)
        ):
            raise StatusError("STATUS-ENVELOPE: invalid dsl metadata")
        if not _non_empty_str(value["correlationId"]):
            raise StatusError("STATUS-ENVELOPE: invalid correlationId")
        payload = value["payload"]
        if (
            not isinstance(payload, dict)
            or set(payload) != PAYLOAD_KEYS
            or RUNTIME_FIELDS.intersection(payload)
        ):
            raise StatusError("STATUS-CANDIDATE-FIELDS: closed payload differs")
        profile = payload["profile"]
        if not isinstance(profile, str) or profile not in PROFILES:
            raise StatusError("STATUS-PROFILE: unknown lifecycle profile")
        graph = PROFILES[profile]
        source, target = payload["from"], payload["to"]
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in graph
            or target not in graph[source]
        ):
            raise StatusError("STATUS-TRANSITION: edge is not allowed or leaves terminal state")
        if (
            not _non_empty_str(payload["cycleId"])
            or not _non_empty_str(payload["subjectRef"])
            or "|" in payload["cycleId"]
            or "|" in payload["subjectRef"]
        ):
            raise StatusError("STATUS-SUBJECT: cycleId and subjectRef must be non-empty safe IDs")
        if not isinstance(payload["reasonCode"], str) or not CODE.fullmatch(payload["reasonCode"]):
            raise StatusError("STATUS-REASON: reasonCode is invalid")
        if (
            not isinstance(payload["summary"], str)
            or not 1 <= len(payload["summary"]) <= 500
            or "\x00" in payload["summary"]
        ):
            raise StatusError("STATUS-SUMMARY: summary is invalid")
        evidence_refs = payload["evidenceRefs"]
        if (
            not isinstance(evidence_refs, list)
            or len(evidence_refs) > MAX_EVIDENCE_REFS
            or not all(_non_empty_str(item) for item in evidence_refs)
        ):
            raise StatusError("STATUS-EVIDENCE: evidenceRefs must be <= 64 non-empty strings")
        key = (payload["cycleId"], payload["subjectRef"])
        observed = state.get(key)
        if observed is not None and observed != source:
            raise StatusError("STATUS-CHAIN: from state differs from prior transition")
        state[key] = target
    return {f"{cycle}|{subject}": status for (cycle, subject), status in sorted(state.items())}


def validate_status_json(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise StatusError("STATUS-JSON: root must be a JSON object")
    _validate_json_tree(data)
    if (
        "system_status" not in data
        or not isinstance(data["system_status"], str)
        or data["system_status"] not in ALLOWED_SYSTEM_STATUSES
    ):
        raise StatusError(
            "STATUS-JSON: invalid or missing system_status, must be one of "
            f"{sorted(ALLOWED_SYSTEM_STATUSES)}"
        )
    if "components" in data:
        if not isinstance(data["components"], list):
            raise StatusError("STATUS-JSON: components must be a list")
        seen_ids: set[str] = set()
        for comp in data["components"]:
            if (
                not isinstance(comp, dict)
                or not _non_empty_str(comp.get("id"))
                or "status" not in comp
            ):
                raise StatusError("STATUS-JSON: component missing valid 'id' or 'status'")
            if comp["id"] in seen_ids:
                raise StatusError(f"STATUS-JSON: duplicate component id '{comp['id']}'")
            seen_ids.add(comp["id"])
            if not isinstance(comp["status"], str) or comp["status"] not in ALLOWED_SYSTEM_STATUSES:
                raise StatusError(f"STATUS-JSON: invalid component status '{comp['status']}'")
    if "calendar" in data:
        if not isinstance(data["calendar"], list):
            raise StatusError("STATUS-JSON: calendar must be a list")
        seen_dates: set[str] = set()
        for day in data["calendar"]:
            if not isinstance(day, dict):
                raise StatusError("STATUS-JSON: calendar entry must be an object")
            raw_date = day.get("date")
            if not isinstance(raw_date, str) or not DATE_PATTERN.fullmatch(raw_date):
                raise StatusError("STATUS-JSON: calendar day missing valid 'date' (YYYY-MM-DD)")
            try:
                date.fromisoformat(raw_date)
            except ValueError as exc:
                raise StatusError(f"STATUS-JSON: impossible calendar date '{raw_date}'") from exc
            if raw_date in seen_dates:
                raise StatusError(f"STATUS-JSON: duplicate calendar date '{raw_date}'")
            seen_dates.add(raw_date)
            if "status" in day and (
                not isinstance(day["status"], str) or day["status"] not in ALLOWED_SYSTEM_STATUSES
            ):
                raise StatusError(f"STATUS-JSON: invalid calendar day status '{day['status']}'")
            if "uptime_percentage" in day:
                pct = day["uptime_percentage"]
                if isinstance(pct, bool) or not isinstance(pct, (int, float)):
                    raise StatusError(
                        "STATUS-JSON: invalid uptime_percentage, must be finite number in [0, 100]"
                    )
                try:
                    pct_f = float(pct)
                except OverflowError as exc:
                    raise StatusError(
                        "STATUS-JSON: invalid uptime_percentage, must be finite number in [0, 100]"
                    ) from exc
                if not math.isfinite(pct_f) or not 0.0 <= pct_f <= 100.0:
                    raise StatusError(
                        "STATUS-JSON: invalid uptime_percentage, must be finite number in [0, 100]"
                    )
    return {"valid": True, "system_status": data["system_status"]}


def _write_json(
    payload: dict[str, Any], stream: TextIO = sys.stdout, *, sort_keys: bool = False
) -> None:
    stream.write(json.dumps(payload, sort_keys=sort_keys) + "\n")


def self_test() -> None:
    base = {
        "schema": "wellmanifest.jsonl/candidate/v1",
        "recordType": "status.transition",
        "sequence": 1,
        "dsl": {
            "manifestId": "wellmanifest.status",
            "schemaRef": "schema://status",
            "grammarRef": "grammar://status",
        },
        "correlationId": "cycle:test",
        "payload": {
            "cycleId": "cycle:test",
            "profile": "autonomy-cycle/v1",
            "subjectRef": "task:test",
            "from": "queued",
            "to": "running",
            "reasonCode": "WORK_STARTED",
            "summary": "started\u2028cleanly",
            "evidenceRefs": [],
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "cycle.jsonl"
        path.write_text(
            json.dumps(base, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8"
        )
        assert validate_stream(path)["cycle:test|task:test"] == "running"
        mutations = (
            ("unknown", lambda item: item["payload"].update(profile="missing/v1")),
            (
                "terminal",
                lambda item: item["payload"].update(**{"from": "succeeded", "to": "running"}),
            ),
            ("runtime", lambda item: item["payload"].update(producer="agent:model")),
            ("bool_seq", lambda item: item.update(sequence=True)),
            ("unhashable_subject", lambda item: item["payload"].update(cycleId=["bad"])),
        )
        failures = 0
        for _, mutate in mutations:
            item = json.loads(json.dumps(base))
            mutate(item)
            path.write_text(json.dumps(item, separators=(",", ":")) + "\n", encoding="utf-8")
            try:
                validate_stream(path)
            except StatusError:
                failures += 1
        assert failures == len(mutations)

        for raw in (b"", b'{"schema":"a","schema":"b"}\n'):
            path.write_bytes(raw)
            try:
                validate_stream(path)
                raise AssertionError("Expected framing/duplicate-key failure")
            except StatusError:
                pass

    valid_status_doc = {
        "schema": "wellmanifest.status/v1",
        "system_status": "ddos_mitigation",
        "components": [
            {"id": "ingress", "name": "Ingress", "status": "ddos_mitigation"},
            {"id": "api", "name": "API", "status": "operational"},
        ],
        "calendar": [{"date": "2026-09-26", "status": "operational", "uptime_percentage": 100.0}],
    }
    res = validate_status_json(valid_status_doc)
    assert res["valid"] is True and res["system_status"] == "ddos_mitigation"

    for bad_doc in (
        {"system_status": "bogus_status"},
        {"system_status": "operational", "calendar": [{"date": "2026-02-31"}]},
        {
            "system_status": "operational",
            "calendar": [{"date": "2026-09-26", "uptime_percentage": True}],
        },
        {
            "system_status": "operational",
            "components": [
                {"id": "api", "status": "operational"},
                {"id": "api", "status": "degraded"},
            ],
        },
    ):
        try:
            validate_status_json(bad_doc)
            raise AssertionError(f"Expected failure for {bad_doc}")
        except StatusError:
            pass

    _write_json({"schema": "wellmanifest.status/self-test/v1", "ok": True, "cases": 13})


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--file", type=Path, required=True)
    val_json = sub.add_parser("validate-json")
    val_json.add_argument("--file", type=Path, required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        elif args.command == "validate-json":
            raw_text = read_regular_bytes(args.file).decode("utf-8", errors="strict")
            content = load_strict_json(raw_text)
            result = validate_status_json(content)
            _write_json(
                {"schema": "wellmanifest.status/json-validation/v1", "ok": True, "result": result},
                sort_keys=True,
            )
        else:
            _write_json(
                {
                    "schema": "wellmanifest.status/projection/v1",
                    "ok": True,
                    "subjects": validate_stream(args.file),
                },
                sort_keys=True,
            )
        return 0
    except (StatusError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _write_json(
            {"schema": "wellmanifest.status/validation/v1", "ok": False, "error": str(exc)},
            stream=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
