# Ticket 010: Harden status_io symlink-parent traversal, secret-key guards, C1 controls, and status bounds

- **ID**: ticket-010
- **Owner**: tom
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-11

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: On 2026-11-11 user authorized auditing, fixing bugs, optimizing, and hardening `wellmanifest/*` standard repositories.

Harden `_check_no_symlink_ancestors` in `standard/status_io.py` against un-normalized absolute (`sym_dir/../real`) and sibling relative (`../sym_dir`) symlink-parent traversal before `os.path.abspath`, declare `__all__`, and reject credential-named dictionary keys when `reject_secrets=True`; reject C1 (`0x80..0x9F`) terminal control characters in `_has_ascii_control` while preserving U+2028/U+2029 line separators in `summary`, and bound `components` (`<= 1024`) and `calendar` (`<= 3660`) arrays in `validate_status_json`; sync `profiles/dsl-manifest.json` digests; expand `standard/test_status_hardening.py`; and reconcile merged `project/ticket-009/README.md` status to `DONE`.

## Acceptance criteria

- [x] AC-01: Reject un-normalized absolute and sibling relative symlink-parent traversal in `_check_no_symlink_ancestors`, reject credential-named dictionary keys in `_validate_json_tree`, reject C1 (`0x80..0x9F`) control characters in `_has_ascii_control`, bound `components` and `calendar` list sizes in `validate_status_json`, sync `profiles/dsl-manifest.json`, and mark `project/ticket-009/README.md` `DONE`.
- [x] AC-02: All Python modules remain strictly `< 500` lines and pass `ruff check --no-cache standard tests`, `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`, `python3 standard/status_check.py self-test`, `python3 standard/status_check.py validate --file examples/cycle.jsonl`, `./project/governance-check.sh --base origin/main`, and `wellman check` with 0 errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
