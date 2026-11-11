# Ticket 007: Harden status regular-file IO, strict JSON bounds, and overflow guards

- **ID**: ticket-007
- **Owner**: tom
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-11

## Goal and scope

Harden `standard/status_check.py` against symlink/FIFO/oversized file reads,
non-finite or deeply nested JSON payloads, non-string object keys, excessive
`evidenceRefs`, and `OverflowError` on huge integer `uptime_percentage`, sync
`profiles/dsl-manifest.json`, add regression tests in
`standard/test_status_hardening.py`, and mark merged `ticket-006` `DONE`.

## Acceptance criteria

- [x] AC-01: Enforce `O_NOFOLLOW | O_NONBLOCK` 4 MiB regular-file reads,
      reject `NaN`/`Infinity`/`1e999`/`> 64` JSON depth, guard `10**400`
      `OverflowError` and `evidenceRefs` bounds, and pass `ruff check standard
      tests`, `pytest -q`, and `status_check.py self-test`.
- [x] AC-02: Refresh `standard/status_check.py` digest in
      `profiles/dsl-manifest.json` and pass `./project/governance-check.sh
      --base origin/main` and `wellman check`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
