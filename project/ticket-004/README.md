# Ticket 004: Standardize 53-week uptime calendar, DDoS incident states, and synthetic JSON endpoint

- **ID**: ticket-004
- **Owner**: human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-26

## Goal and scope

Standardize 53-week uptime calendar, DDoS incident states with dynamic attack vector shunting, machine-readable `/status.json` schema, and component health invariants under Tomasz Sapletta Prototypowanie.pl.

## Acceptance criteria

- [x] AC-01: Create `docs/STATUS_53_WEEK_CALENDAR_AND_DDOS.md` with 53-week uptime calendar and DDoS vector shift specification.
- [x] AC-02: Update `docs/ARCHITECTURE.md` with Invariants 6 and 7.
- [x] AC-03: Update `standard/status_check.py` with `cluster-status/v1` profile, `validate_status_json`, and self-test suite.
- [x] AC-04: Passes `./project/governance-check.sh`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
