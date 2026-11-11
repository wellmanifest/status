# Ticket 006: Add standalone pytest unit suite for status stream and status.json validator

- **ID**: ticket-006
- **Owner**: agent:antigravity under SESSION_EXECUTION_AUTHORIZATION
- **Status**: DONE
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-11

## Goal and scope

Add a standalone `pytest` / `unittest` regression suite (`tests/test_status.py`) exercising `validate_stream`, `validate_status_json`, contract bundle SSOT parity, framing/duplicate-key/type/date/percentage guards, and CLI `main()` exit codes in `standard/status_check.py`.

## Acceptance criteria

- [x] AC-01: Standalone `pytest -q` and `python3 -m unittest discover -s tests -v` pass all unit tests.
- [x] AC-02: `ruff check standard tests` passes with 0 errors.
- [x] AC-03: `./project/governance-check.sh --base origin/main` and `wellman check` pass with 0 errors.

## Participants

- Human participant: session request to validate, test, fix, optimize, and harden `wellmanifest/*` standards; no `user-*` file was created or modified.
