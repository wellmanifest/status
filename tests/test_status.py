from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import status_check


def make_record(
    sequence: int = 1,
    *,
    profile: str = "autonomy-cycle/v1",
    source: str = "queued",
    target: str = "running",
    cycle_id: str = "cycle:001",
    subject: str = "task:001",
    reason: str = "WORK_STARTED",
    summary: str = "Transition recorded.",
    evidence: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema": "wellmanifest.jsonl/candidate/v1",
        "recordType": "status.transition",
        "sequence": sequence,
        "dsl": {
            "manifestId": "wellmanifest.status",
            "schemaRef": "https://wellmanifest.com/schemas/status/candidate.v1.json",
            "grammarRef": "https://github.com/wellmanifest/status/blob/main/grammars/status-candidate.gbnf",
        },
        "correlationId": cycle_id,
        "payload": {
            "cycleId": cycle_id,
            "profile": profile,
            "subjectRef": subject,
            "from": source,
            "to": target,
            "reasonCode": reason,
            "summary": summary,
            "evidenceRefs": evidence if evidence is not None else [],
        },
    }


class StatusStreamTests(unittest.TestCase):
    def test_example_cycle_stream_projects_terminal_state(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "cycle.jsonl"
        projected = status_check.validate_stream(example)
        self.assertEqual(projected, {"cycle:demo-001|task:demo-001": "succeeded"})

    def test_all_contract_profiles_and_unicode_line_separators_are_supported(self) -> None:
        records = [
            make_record(1, profile="autonomy-cycle/v1", source="queued", target="running", summary="line\u2028sep\u2029ok"),
            make_record(2, profile="health/v1", source="unknown", target="ddos_mitigation", cycle_id="cycle:h", subject="svc:edge"),
            make_record(3, profile="cluster-status/v1", source="operational", target="maintenance", cycle_id="cycle:c", subject="cluster:eu"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi.jsonl"
            lines = "".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in records)
            path.write_text(lines, encoding="utf-8")
            result = status_check.validate_stream(path)
        self.assertEqual(
            result,
            {
                "cycle:001|task:001": "running",
                "cycle:c|cluster:eu": "maintenance",
                "cycle:h|svc:edge": "ddos_mitigation",
            },
        )

    def test_framing_bom_crlf_blank_line_and_duplicate_keys_are_rejected(self) -> None:
        valid_bytes = (json.dumps(make_record(), separators=(",", ":")) + "\n").encode("utf-8")
        samples = [
            b"",
            valid_bytes[:-1],
            valid_bytes[:-1] + b"\r\n",
            b"\xef\xbb\xbf" + valid_bytes,
            valid_bytes + b"\n",
            b'{"schema":"wellmanifest.jsonl/candidate/v1","schema":"dup"}\n',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            for raw in samples:
                path.write_bytes(raw)
                with self.assertRaises(status_check.StatusError):
                    status_check.validate_stream(path)

    def test_bool_sequence_unhashable_fields_and_broken_chain_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            rec_bool = make_record()
            rec_bool["sequence"] = True
            path.write_text(json.dumps(rec_bool) + "\n", encoding="utf-8")
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(path)

            rec_list = make_record()
            assert isinstance(rec_list["payload"], dict)
            rec_list["payload"]["subjectRef"] = ["bad"]
            path.write_text(json.dumps(rec_list) + "\n", encoding="utf-8")
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(path)

            chain = [
                make_record(1, source="queued", target="waiting", reason="QUEUED_WAIT"),
            ]
            path.write_text(json.dumps(chain[0]) + "\n", encoding="utf-8")
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(path)

            broken_chain = [
                make_record(1, source="queued", target="running"),
                make_record(2, source="waiting", target="cancelled"),
            ]
            path.write_text("".join(json.dumps(r) + "\n" for r in broken_chain), encoding="utf-8")
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(path)


class StatusJsonAndCliTests(unittest.TestCase):
    def test_validate_status_json_enforces_dates_percentages_and_unique_ids(self) -> None:
        valid = {
            "system_status": "operational",
            "components": [{"id": "api", "status": "operational"}],
            "calendar": [{"date": "2026-11-11", "status": "operational", "uptime_percentage": 99.95}],
        }
        self.assertEqual(status_check.validate_status_json(valid), {"valid": True, "system_status": "operational"})

        invalid_docs = [
            {"system_status": "unknown"},
            {"system_status": "operational", "components": [{"id": "", "status": "operational"}]},
            {"system_status": "operational", "components": [{"id": "a", "status": "operational"}, {"id": "a", "status": "degraded"}]},
            {"system_status": "operational", "calendar": [{"date": "2026-02-29"}]},
            {"system_status": "operational", "calendar": [{"date": 20261111}]},
            {"system_status": "operational", "calendar": [{"date": "2026-11-11"}, {"date": "2026-11-11"}]},
            {"system_status": "operational", "calendar": [{"date": "2026-11-11", "uptime_percentage": -0.1}]},
            {"system_status": "operational", "calendar": [{"date": "2026-11-11", "uptime_percentage": 100.1}]},
            {"system_status": "operational", "calendar": [{"date": "2026-11-11", "uptime_percentage": False}]},
        ]
        for doc in invalid_docs:
            with self.assertRaises(status_check.StatusError):
                status_check.validate_status_json(doc)

    def test_cli_commands_return_deterministic_exit_codes(self) -> None:
        script = Path(__file__).resolve().parents[1] / "standard" / "status_check.py"
        with tempfile.TemporaryDirectory() as tmp:
            status_path = Path(tmp) / "status.json"
            status_path.write_text('{"system_status":"operational"}\n', encoding="utf-8")
            ok_proc = subprocess.run(
                [sys.executable, str(script), "validate-json", "--file", str(status_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ok_proc.returncode, 0)
            self.assertTrue(json.loads(ok_proc.stdout)["ok"])

            status_path.write_text('{"system_status":"operational","system_status":"degraded"}\n', encoding="utf-8")
            bad_proc = subprocess.run(
                [sys.executable, str(script), "validate-json", "--file", str(status_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bad_proc.returncode, 1)
            self.assertFalse(json.loads(bad_proc.stderr)["ok"])


if __name__ == "__main__":
    unittest.main()
