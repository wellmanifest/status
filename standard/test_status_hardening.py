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
            Path(tmp, "too_many_refs.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaises(status_check.StatusError):
                status_check.validate_stream(Path(tmp, "too_many_refs.jsonl"))

    def test_load_strict_json_rejects_huge_integers_lone_surrogates_and_bad_syntax(self) -> None:
        for bad_json in (
            '{"count": ' + ("9" * 400) + "}",
            '{"count": -' + ("9" * 400) + "}",
            '{"count": ' + ("9" * 5000) + "}",
            '{"system_status": "\\ud800"}',
            '{"\\udfff": "operational"}',
            '{"system_status": "operational\ud800"}',
            '{"system_status": ',
        ):
            with self.subTest(sample=bad_json[:32]), self.assertRaises(status_check.StatusError):
                status_check.load_strict_json(bad_json)

    def test_symlink_ancestors_max_bytes_bounds_and_regex_anchors(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_dir = root / "real_sub"
            real_dir.mkdir()
            doc_path = real_dir / "status.json"
            doc_path.write_text('{"system_status":"operational"}\n', encoding="utf-8")
            sym_dir = root / "sym_sub"
            sym_dir.symlink_to(real_dir)

            with self.assertRaises(status_check.StatusError):
                status_check.read_regular_bytes(sym_dir / "status.json")

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaises(status_check.StatusError):
                    status_check.read_regular_bytes(Path("sym_sub/status.json"))
            finally:
                os.chdir(old_cwd)

            for bad_max in (True, False, 0, -1):
                with self.subTest(max_bytes=bad_max), self.assertRaises(status_check.StatusError):
                    status_check.read_regular_bytes(doc_path, max_bytes=bad_max)  # type: ignore[arg-type]

        self.assertIsNone(status_check.CODE.match("WORK_STARTED\n"))
        self.assertIsNone(status_check.DATE_PATTERN.match("2026-11-11\n"))

    def test_validate_stream_rejects_pipe_collisions_and_control_characters(self) -> None:
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
                "summary": "started",
                "evidenceRefs": [],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_ids.jsonl"
            for mutator in (
                lambda rec: rec["payload"].update(cycleId="cycle|bad"),
                lambda rec: rec["payload"].update(subjectRef="task|bad"),
                lambda rec: rec["payload"].update(cycleId="cycle:\x1b[31mbad"),
                lambda rec: rec.update(correlationId="corr:\x00bad"),
                lambda rec: rec["payload"].update(summary="bad\x00nul"),
            ):
                cloned = json.loads(json.dumps(base))
                mutator(cloned)
                path.write_text(json.dumps(cloned) + "\n", encoding="utf-8")
                with self.assertRaises(status_check.StatusError):
                    status_check.validate_stream(path)

    def test_modular_bounds_relative_symlink_traversal_summary_controls_and_secrets(
        self,
    ) -> None:
        import os

        std_dir = Path(__file__).resolve().parent
        for name in ("status_io.py", "status_check.py", "test_status_hardening.py"):
            lines = (std_dir / name).read_text(encoding="utf-8").splitlines()
            self.assertLess(len(lines), 500, f"{name} exceeded 500 lines: {len(lines)}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_sub = root / "real_sub"
            real_sub.mkdir()
            doc_path = root / "status.json"
            doc_path.write_text('{"system_status":"operational"}\n', encoding="utf-8")
            sym_sub = root / "sym_sub"
            sym_sub.symlink_to(real_sub)

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaises(status_check.StatusError):
                    status_check.read_regular_bytes("sym_sub/../status.json")
            finally:
                os.chdir(old_cwd)

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
                    "summary": "started",
                    "evidenceRefs": [],
                },
            }
            gh_pat = "gh" + "p_" + ("A" * 24)
            aws_id = "AK" + "IA" + ("B" * 16)
            stream_path = root / "sec.jsonl"
            for bad_summary in ("ansi \x1b[31mred", f"leak {gh_pat}", f"leak {aws_id}"):
                rec = json.loads(json.dumps(base))
                rec["payload"]["summary"] = bad_summary
                stream_path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
                with self.assertRaises(status_check.StatusError):
                    status_check.validate_stream(stream_path)

        for bad_doc in (
            {"schema": "wrong/v1", "system_status": "operational"},
            {
                "system_status": "operational",
                "components": [{"id": "api", "name": "   ", "status": "operational"}],
            },
            {
                "system_status": "operational",
                "components": [{"id": "api", "name": gh_pat, "status": "operational"}],
            },
        ):
            with self.assertRaises(status_check.StatusError):
                status_check.validate_status_json(bad_doc)


if __name__ == "__main__":
    unittest.main()
