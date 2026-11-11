#!/usr/bin/env python3
"""Dependency-free validator/projector for Wellmanifest status-cycle JSONL and status.json."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

_STD_DIR = str(Path(__file__).resolve().parent)
if _STD_DIR not in sys.path:
    sys.path.insert(0, _STD_DIR)

from status_io import (  # noqa: E402
    _SENSITIVE_RE,
    MAX_FILE_BYTES,
    MAX_JSON_DEPTH,
    StatusError,
    _check_utf8_str,
    _parse_finite_float,
    _parse_finite_int,
    _reject_json_constant,
    _unique_object,
    _validate_json_tree,
    _write_json,
    load_strict_json,
    read_regular_bytes,
)

MAX_EVIDENCE_REFS = 64
MAX_STATUS_COMPONENTS = 1024
MAX_CALENDAR_DAYS = 3660
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

__all__ = [
    "ALLOWED_SYSTEM_STATUSES",
    "CODE",
    "DATE_PATTERN",
    "DSL_KEYS",
    "ENVELOPE_KEYS",
    "MAX_CALENDAR_DAYS",
    "MAX_EVIDENCE_REFS",
    "MAX_FILE_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_STATUS_COMPONENTS",
    "PAYLOAD_KEYS",
    "PROFILES",
    "RUNTIME_FIELDS",
    "_SENSITIVE_RE",
    "StatusError",
    "_check_utf8_str",
    "_parse_finite_float",
    "_parse_finite_int",
    "_reject_json_constant",
    "_unique_object",
    "_validate_json_tree",
    "_write_json",
    "load_strict_json",
    "main",
    "read_regular_bytes",
    "self_test",
    "validate_status_json",
    "validate_stream",
]


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


def _has_ascii_control(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 or 0x80 <= ord(ch) <= 0x9F for ch in value)


def _non_empty_str(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= 500
        and not _has_ascii_control(value)
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
        _validate_json_tree(value, reject_secrets=True)
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
            or _has_ascii_control(payload["summary"])
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
    _validate_json_tree(data, reject_secrets=True)
    if "schema" in data and data["schema"] != "wellmanifest.status/v1":
        raise StatusError("STATUS-JSON: unsupported status.json schema")
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
        if (
            not isinstance(data["components"], list)
            or len(data["components"]) > MAX_STATUS_COMPONENTS
        ):
            raise StatusError(
                f"STATUS-JSON: components must be a list of <= {MAX_STATUS_COMPONENTS} items"
            )
        seen_ids: set[str] = set()
        for comp in data["components"]:
            if (
                not isinstance(comp, dict)
                or not _non_empty_str(comp.get("id"))
                or "status" not in comp
                or ("name" in comp and not _non_empty_str(comp["name"]))
            ):
                raise StatusError("STATUS-JSON: component missing valid 'id' or 'status'")
            if comp["id"] in seen_ids:
                raise StatusError(f"STATUS-JSON: duplicate component id '{comp['id']}'")
            seen_ids.add(comp["id"])
            if not isinstance(comp["status"], str) or comp["status"] not in ALLOWED_SYSTEM_STATUSES:
                raise StatusError(f"STATUS-JSON: invalid component status '{comp['status']}'")
    if "calendar" in data:
        if not isinstance(data["calendar"], list) or len(data["calendar"]) > MAX_CALENDAR_DAYS:
            raise StatusError(
                f"STATUS-JSON: calendar must be a list of <= {MAX_CALENDAR_DAYS} items"
            )
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
