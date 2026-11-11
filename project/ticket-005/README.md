# Ticket 005: Harden status JSONL/JSON validator, sync contract bundle, and repair DSL manifest digest

- **ID**: ticket-005
- **Owner**: agent:antigravity under SESSION_EXECUTION_AUTHORIZATION
- **Status**: DONE
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-11

## Goal and scope

Synchronize `contracts/status.contract.json` with `health/v1` DDoS/maintenance states and `cluster-status/v1` as SSOT for `standard/status_check.py`; harden JSONL/JSON parsing against Unicode `splitlines()` framing bypasses, empty streams, duplicate JSON keys, boolean sequence numbers, unhashable field types, impossible calendar dates, and invalid `uptime_percentage` values; wire `pyproject.toml` for pytest; and refresh `profiles/dsl-manifest.json` digests.

## Acceptance criteria

- [x] AC-01: `python3 standard/status_check.py self-test` and `python3 standard/status_check.py validate --file examples/cycle.jsonl` pass with 0 errors.
- [x] AC-02: `dsl_check.py validate profiles/dsl-manifest.json` passes with `DSL-PASS` (0 errors).
- [x] AC-03: `ruff check standard` and `./project/governance-check.sh --base origin/main` + `wellman check` pass with 0 errors.

## Participants

- Human participant: session request to validate, fix, optimize, and harden `wellmanifest/*` standards; no `user-*` file was created or modified.
