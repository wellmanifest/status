# Ticket 002: State the reading invariants for a status record

- **ID**: ticket-002
- **Owner**: bot:wellmanifest
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-10

## Goal and scope

The contract bundle defines what a status record may contain. It does not say
how a record must be readable, and those are different questions: a record can
be perfectly well-formed and still be understood as saying something it does
not say.

Five invariants, each written from an observed misreading in an adopting
runtime on 2026-09-10 and citing it, so an adopter recognises the shape rather
than reasoning from an abstraction:

1. a retained failure is not a current state;
2. one record, one instant;
3. a resting state is not a fault;
4. recorded freshness exists to be compared;
5. an unchecked relation is not an absent relation.

`docs/**` had no owning workstream, which is why this ticket also declares it
under `governance` alongside the other narrative files. That declares ownership
for a previously unowned path; no existing path changes owner.

## Acceptance criteria

- [x] AC-01: The standard states the reading invariants with their observations,
  `docs/**` has a declared owner, and the standard's self-test passes.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
