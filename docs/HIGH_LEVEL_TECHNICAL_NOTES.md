# High-Level Technical Notes

This file is a short working summary. `TECHNICAL_SPECIFICATION.md` is
authoritative for durable technical direction, and `IMPLEMENTATION_PLAN.md`
is authoritative for progress.

## Current state

- The product is owner-operated and non-public.
- Telegram broadcast channels are the first production ingestion source.
- Source material, processing records, and candidates are inspectable.
- Structurally valid candidates retain business-rule problems as review issues.
- Every candidate has a mutable review that can synchronize a draft canonical
  event automatically or after manual correction.
- Sparse useful events are retained; contradictions block synchronization, and
  exact-title duplicates require an explicit separate-event decision.
- Milestone 5 is the first canonical event API contract.

## Durable guardrails

- Keep source observations separate from canonical product data.
- Preserve provenance and enough evidence to explain automated output.
- Treat source content and provider output as untrusted.
- Keep user-visible decisions in backend-owned workflows.
- Never guess missing event or location facts.
- Make reruns safe and protect manual decisions.
- Do not expose the product publicly before the readiness gate.

## Milestone 5 questions

Decide these while implementing and testing the first useful event API:

- Which canonical event, occurrence, registration, classification, organizer,
  venue, and provenance fields the first interface needs
- Which records are visible to the owner-facing API before publication rules
  exist
- What filter, ordering, pagination, and identifier behavior the first map/list
  slice requires
- How online-only events remain list-visible without map geometry

Record the resulting durable behavior only after it is verified.

## Later questions

- Map provider and interaction details belong to the discovery-interface
  milestone.
- Change handling, source cadence, and operational recovery belong to
  personal-use hardening.
- New retrieval methods belong to the source that demonstrates their need.
- Hosting, monitoring, authentication, and rollout belong to public-readiness
  work.
