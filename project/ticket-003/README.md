# Ticket 003: Adopt wellmanifest/new-project 0.20.32

- **ID**: ticket-003
- **Owner**: unresolved:human
- **Status**: DONE
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-16

## Goal and scope

To be completed from human-owned input.

## Acceptance criteria

- [ ] AC-01: Scope is approved by a human owner.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-glm.md](ai-glm.md)
## Validation evidence

- `goal governance adopt --latest --check` — up-to-date 0.20.32 @ b6ba9c21
- `./project/governance-check.sh` — GOV-PASS (0 errors, 0 warnings)
- Local `manifest.json` extensions aligned to 0.20.32 base (ticket policy,
  `$schema` removal, `.gitignore` governance ownership, integration list trim).
