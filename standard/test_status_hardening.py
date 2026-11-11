"""Adversarial regression tests for wellmanifest/status JSON, IO, depth, and overflow guards."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import status_check


class StatusHardeningTests(unittest.TestCase):
    def test_load_strict_json_rejects_non_finite_float_overflow_and_deep_nesting(self) -> None:
        for bad_json in (
            '{"system_status": NaN}',
            '{"system_status": Infinity}',
            '{"system_status": -Infinity}',
            '{"uptime_percentage": 1e999}',
            '{"uptime_percentage": -1e999}',
            ("[" * 66) + "1" + ("]" * 66),
            ("[" * 1500) + "1" + ("]" * 1500),
        ):
            with self.subTest(payload=bad_json[:32]):
                with self.assertRaises(status_check.StatusError):
                    status_check.load_strict_json(bad_json)

    def test_regular_file_reader_and_cli_reject_symlinks_directories_and_oversized_files(
        self,
    ) -> None:
        script = Path(__file__).resolve().parent / "status_check.py"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_json = base / "status.json"
            real_json.write_text('{"system_status":"operational"}\n', encoding="utf-8")
            sym_json = base / "sym-status.json"
            sym_json.symlink_to(real_json)

            with self.assertRaises(status_check.StatusError):
                status_check.read_regular_bytes(sym_json)
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(sym_json)

            proc = subprocess.run(
                [sys.executable, str(script), "validate-json", "--file", str(sym_json)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            err_doc = json.loads(proc.stderr)
            self.assertFalse(err_doc["ok"])
            self.assertIn("SYMLINK", err_doc["error"])

            sub_dir = base / "adir"
            sub_dir.mkdir()
            with self.assertRaises(status_check.StatusError):
                status_check.read_regular_bytes(sub_dir)

            big_file = base / "huge.json"
            pad = b"a" * (status_check.MAX_FILE_BYTES + 32)
            big_file.write_bytes(b'{"x":"' + pad + b'"}\n')
            with self.assertRaises(status_check.StatusError):
                status_check.read_regular_bytes(big_file)

    def test_validate_status_json_rejects_huge_int_overflow_non_string_keys_and_deep_nesting(
        self,
    ) -> None:
        huge_int_doc = {
            "system_status": "operational",
            "calendar": [{"date": "2026-11-11", "uptime_percentage": 10**400}],
        }
        with self.assertRaises(status_check.StatusError):
            status_check.validate_status_json(huge_int_doc)

        non_str_doc: dict[Any, Any] = {"system_status": "operational", 1: "bad"}
        with self.assertRaises(status_check.StatusError):
            status_check.validate_status_json(non_str_doc)

        nested: Any = "leaf"
        for _ in range(70):
            nested = [nested]
        deep_doc = {"system_status": "operational", "meta": nested}
        with self.assertRaises(status_check.StatusError):
            status_check.validate_status_json(deep_doc)

    def test_validate_stream_rejects_excessive_evidence_refs(self) -> None:
        record = {
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
                "summary": "started",
                "evidenceRefs": [f"ref:{i}" for i in range(status_check.MAX_EVIDENCE_REFS + 1)],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "too_many_refs.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(path)


if __name__ == "__main__":
    unittest.main()
