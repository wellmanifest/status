# Architecture

`wellmanifest/status` carries a status record between the runtime that writes
it and everything that reads it: a dashboard, an operator, a diagnostic agent,
another service. The contract bundle already defines what a record may contain.
This document states how a record must be readable, which is a separate
question: a record can be perfectly well-formed and still be understood as
saying something it does not say.

Every invariant below was written from an observed misreading in an adopting
runtime, not from anticipated risk. Each names the observation that produced
it, so an adopter can recognise the same shape.

## Scope

These invariants govern the record and its fields. They do not define states,
transitions or lifecycle vocabularies — those belong to the contract bundle and
to the domain lifecycle packs that compose with it.

## Invariants

1. **A retained failure is not a current state.** A field carrying a previous
   failure is either cleared when a new attempt begins, or carries the attempt
   and instant it belongs to. A reader cannot otherwise tell a failure that is
   still happening from one that already ended.

   *Observed 2026-09-10: an execution record kept the previous attempt's
   provider payment error after the account had been funded, and the board
   reported that failure for hours. Only an independent spend counter
   disproved it.*

2. **One record, one instant.** The record's timestamp describes all of its
   fields. A field taken from an earlier instant carries its own timestamp.

   *Observed 2026-09-10: `updated_at` advanced to the moment execution
   restarted while the error field stayed from the attempt before, so a single
   timestamp covered two different moments and the newer one was read as
   describing both.*

3. **A resting state is not a fault.** A record must let a reader separate
   "finished and waiting" from "died". Neither an empty set of running work nor
   a failed exit status of a one-shot worker is, by itself, evidence that a
   consumer is gone.

   *Observed 2026-09-10: a diagnostic that read "ready work and nothing
   running" raised two high-severity findings against healthy queues. A
   timer-driven consumer is between cycles almost all of the time, and a
   one-shot unit rests in a failed state after any failed item. The signal that
   distinguishes a stalled queue is whether anything in it moved at all.*

4. **Recorded freshness exists to be compared.** A field recording the last
   successful observation is compared against a declared tolerance before a
   verdict is derived from it. A readiness verdict taken from a single failed
   sample, while freshness is recorded and never read, is a defect of the
   contract rather than of the sample.

   *Observed 2026-09-10: a staleness flag was set from one failed read, closing
   every readiness gate, while the recorded last-success instant was never
   compared to anything. A brief store outage and a missing capability were
   reported identically.*

5. **An unchecked relation is not an absent relation.** A record distinguishes
   "no relation was found here" from "no relation exists". A reader acting on
   the second must be able to see that the claim was actually established.

   *Observed 2026-09-10: an empty projection field was read as proof that no
   external projection existed. The projection was real and recorded elsewhere,
   and deleting the records on that reading orphaned sixteen live external
   issues.*

6. **Mitigated attack vectors do not equal service death.** When an edge ingress
   dynamically shifts an abusive traffic vector into an isolated honeypot,
   rate-limiting sink, or tarpit while genuine user transactions continue to
   process within latency bounds, the status record classifies the state as
   `ddos_mitigation` or `operational (mitigated)`. A reader that collapses all
   mitigation events into complete outages creates false alerts across
   dependent subsystems.

   *Observed 2026-09-26: edge ingress shunted high-frequency scraping floods
   into tarpit endpoints; naive probers hitting public edge IPs without
   synthetic authentication markers reported total system failure despite all
   workload clusters operating at 100% capacity.*

7. **Annual availability requires dense rolling bucketing.** Status records that
   maintain annual SLA transparency must provide dense rolling calendars (such
   as 53-week 371-day matrices) with discrete percentiles ($p50$, $p95$, $p99$)
   to separate transient packet loss from systemic availability breaches.

## Composition

These invariants constrain how a runtime writes and how a consumer reads. They
grant no authority, and they never make a record executable: a well-formed,
readable record is evidence, never a command.
