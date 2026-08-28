# Ticket 001: Define governed status-cycle standard

- **ID**: ticket-001
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-08-28

## Goal and scope

Define a portable status-cycle projection that separates observed state,
proposed transition and runtime-confirmed transition. Compose it with
`wellmanifest/jsonl` framing and `wellmanifest/dsl` without taking ownership of
domain lifecycle vocabularies.

## Acceptance criteria

- [x] AC-01: A closed profile defines states, terminal states and allowed
  transitions; unknown profiles and invalid edges fail closed.
- [x] AC-02: LLM candidates omit runtime-owned authority, timestamps, hashes
  and receipts; a trusted runtime seals only a validated transition.
- [x] AC-03: Status records compose with `wellmanifest/jsonl` and arbitrary
  DSL payload references through `wellmanifest/dsl`.
- [x] AC-04: Dependency-free tests prove valid cycles, idempotent observations,
  terminal-state protection, hash drift and malformed input rejection.
- [ ] AC-05: A Subactor Supervisor adapter demonstrates the standard on live
  assessment cycles without widening execution authority.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)
