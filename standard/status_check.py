#!/usr/bin/env python3
"""Dependency-free validator/projector for Wellmanifest status-cycle JSONL."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PROFILES = {
    "autonomy-cycle/v1": {
        "queued": {"running", "cancelled"},
        "running": {"waiting", "blocked", "succeeded", "failed", "cancelled"},
        "waiting": {"running", "blocked", "cancelled"},
        "blocked": {"running", "failed", "cancelled"},
        "succeeded": set(), "failed": set(), "cancelled": set(),
    },
    "health/v1": {
        "unknown": {"healthy", "degraded", "unhealthy"},
        "healthy": {"degraded", "unhealthy"},
        "degraded": {"healthy", "unhealthy"},
        "unhealthy": {"healthy", "degraded"},
    },
}
ENVELOPE_KEYS = {"schema", "recordType", "sequence", "dsl", "correlationId", "payload"}
PAYLOAD_KEYS = {"cycleId", "profile", "subjectRef", "from", "to", "reasonCode", "summary", "evidenceRefs"}
RUNTIME_FIELDS = {"transitionId", "producer", "observedAt", "inputHash", "previousHash", "transitionHash", "receiptRef"}
CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class StatusError(ValueError):
    pass


def validate_stream(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n") or b"\r" in raw or raw.startswith(b"\xef\xbb\xbf"):
        raise StatusError("STATUS-JSONL-FRAMING: require UTF-8 LF-terminated JSONL")
    state: dict[tuple[str, str], str] = {}
    for sequence, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line:
            raise StatusError("STATUS-JSONL-BLANK: blank line")
        value = json.loads(line)
        if not isinstance(value, dict) or set(value) != ENVELOPE_KEYS:
            raise StatusError("STATUS-ENVELOPE: invalid wellmanifest.jsonl candidate")
        if value["schema"] != "wellmanifest.jsonl/candidate/v1" or value["recordType"] != "status.transition" or value["sequence"] != sequence:
            raise StatusError("STATUS-ENVELOPE: schema, type or sequence mismatch")
        payload = value["payload"]
        if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS or RUNTIME_FIELDS.intersection(payload):
            raise StatusError("STATUS-CANDIDATE-FIELDS: closed payload differs")
        profile = payload["profile"]
        graph = PROFILES.get(profile)
        if graph is None:
            raise StatusError("STATUS-PROFILE: unknown lifecycle profile")
        source, target = payload["from"], payload["to"]
        if source not in graph or target not in graph[source]:
            raise StatusError("STATUS-TRANSITION: edge is not allowed or leaves terminal state")
        if not isinstance(payload["reasonCode"], str) or not CODE.fullmatch(payload["reasonCode"]):
            raise StatusError("STATUS-REASON: reasonCode is invalid")
        if not isinstance(payload["summary"], str) or not 1 <= len(payload["summary"]) <= 500:
            raise StatusError("STATUS-SUMMARY: summary is invalid")
        if not isinstance(payload["evidenceRefs"], list) or not all(isinstance(item, str) and item for item in payload["evidenceRefs"]):
            raise StatusError("STATUS-EVIDENCE: evidenceRefs must be strings")
        key = (payload["cycleId"], payload["subjectRef"])
        observed = state.get(key)
        if observed is not None and observed != source:
            raise StatusError("STATUS-CHAIN: from state differs from prior transition")
        state[key] = target
    return {f"{cycle}|{subject}": status for (cycle, subject), status in sorted(state.items())}


def self_test() -> None:
    base = {
        "schema": "wellmanifest.jsonl/candidate/v1", "recordType": "status.transition", "sequence": 1,
        "dsl": {"manifestId": "wellmanifest.status", "schemaRef": "schema://status", "grammarRef": "grammar://status"},
        "correlationId": "cycle:test", "payload": {"cycleId": "cycle:test", "profile": "autonomy-cycle/v1", "subjectRef": "task:test", "from": "queued", "to": "running", "reasonCode": "WORK_STARTED", "summary": "started", "evidenceRefs": []},
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "cycle.jsonl"
        path.write_text(json.dumps(base, separators=(",", ":")) + "\n", encoding="utf-8")
        assert validate_stream(path)["cycle:test|task:test"] == "running"
        failures = []
        for name, mutate in (
            ("unknown", lambda item: item["payload"].update(profile="missing/v1")),
            ("terminal", lambda item: item["payload"].update(**{"from": "succeeded", "to": "running"})),
            ("runtime", lambda item: item["payload"].update(producer="agent:model")),
        ):
            item = json.loads(json.dumps(base)); mutate(item)
            path.write_text(json.dumps(item, separators=(",", ":")) + "\n", encoding="utf-8")
            try: validate_stream(path)
            except (StatusError, json.JSONDecodeError): failures.append(name)
        assert len(failures) == 3
    print(json.dumps({"schema": "wellmanifest.status/self-test/v1", "ok": True, "cases": 4}))


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate"); validate.add_argument("--file", type=Path, required=True)
    sub.add_parser("self-test"); args = parser.parse_args()
    try:
        if args.command == "self-test": self_test()
        else: print(json.dumps({"schema": "wellmanifest.status/projection/v1", "ok": True, "subjects": validate_stream(args.file)}, sort_keys=True))
        return 0
    except (StatusError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": "wellmanifest.status/validation/v1", "ok": False, "error": str(exc)}), file=sys.stderr); return 1


if __name__ == "__main__": raise SystemExit(main())
