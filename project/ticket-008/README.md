# Ticket 008: Harden status JSON overflow/surrogates, inode/ancestor symlinks, and subject projection collisions

- **ID**: ticket-008
- **Owner**: tom
- **Status**: DONE
- **Workflow state**: MERGED
- **Created**: 2026-11-11

## Goal and scope

Harden `standard/status_check.py` against `10**400` JSON integer overflow,
lone UTF-16 surrogates, symlink ancestor traversal and `(st_dev, st_ino)`
file-swap races in `read_regular_bytes`, ASCII control characters and `|`
delimiter collisions in `validate_stream` subject projection keys, and
line-end `$` regex anchors; sync `profiles/dsl-manifest.json`; expand
`standard/test_status_hardening.py`; and mark merged `ticket-007` `DONE`.

## Acceptance criteria

- [x] AC-01: Reject `10**400` integers, lone UTF-16 surrogates, symlink
      ancestors, `lstat`/`fstat` inode mismatches, `|` projection-key
      collisions, and ASCII control characters in identifiers, and pass
      `ruff check standard tests`, `pytest -q`, and `status_check.py self-test`.
- [x] AC-02: Refresh `standard/status_check.py` digest in
      `profiles/dsl-manifest.json`, mark `ticket-007` `DONE`, and pass
      `./project/governance-check.sh --base origin/main` and `wellman check`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
