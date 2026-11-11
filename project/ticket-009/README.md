# Ticket 009: Modularize status_io and harden relative symlink traversal, JSON bounds, control chars, and secret scanning

- **ID**: ticket-009
- **Owner**: tom
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-11-11

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: On 2026-11-11 user authorized auditing, fixing bugs, optimizing, and hardening `wellmanifest/*` standard repositories.

Extract bounded regular-file/JSON I/O, symlink-ancestor checks, and secret scanning into `standard/status_io.py` so `standard/status_check.py` drops well below 500 lines; prevent relative `sym_dir/..` symlink-parent traversal in `read_regular_bytes`; bound JSON integer digit length before `int()` conversion in `load_strict_json`; pass `allow_nan=False` in `_write_json`; reject all ASCII control characters in `validate_stream` `summary` and inline credential material across `validate_stream` and `validate_status_json`; enforce optional `schema` and `components[*].name` invariants in `validate_status_json`; sync `profiles/dsl-manifest.json` digests; expand `standard/test_status_hardening.py`; and reconcile merged `project/ticket-008/README.md` status to `DONE`.

## Acceptance criteria

- [x] AC-01: Extract `standard/status_io.py` (< 500L), block `sym_dir/..` relative symlink traversal, bound JSON integer digits before `int()`, reject ASCII control characters in `summary` and inline credential material across streams and `status.json`, enforce `schema` and `components[*].name` invariants, sync `profiles/dsl-manifest.json`, and mark `project/ticket-008/README.md` `DONE`.
- [x] AC-02: All Python modules remain strictly `< 500` lines and pass `ruff check --no-cache standard tests`, `pytest -q -p no:cacheprovider`, `python3 standard/status_check.py self-test`, `python3 standard/status_check.py validate --file examples/cycle.jsonl`, `./project/governance-check.sh --base origin/main`, and `wellman check` with 0 errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
