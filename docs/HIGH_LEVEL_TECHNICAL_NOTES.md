# High-Level Technical Notes

This file is a short working summary. `TECHNICAL_SPECIFICATION.md` is
authoritative for durable technical direction, and `IMPLEMENTATION_PLAN.md`
is authoritative for progress.

## Current state

- The product is owner-operated and non-public.
- Telegram broadcast channels are the first production ingestion source.
- Source material, processing records, and candidates are inspectable.
- Structurally valid candidates retain business-rule problems as review issues.
- Core event, occurrence, organizer, classification, building, venue, and
  provenance data structures exist.
- Milestone 4 is implementing the path from candidate review to canonical event
  data.

## Durable guardrails

- Keep source observations separate from canonical product data.
- Preserve provenance and enough evidence to explain automated output.
- Treat source content and provider output as untrusted.
- Keep user-visible decisions in backend-owned workflows.
- Never guess missing event or location facts.
- Make reruns safe and protect manual decisions.
- Do not expose the product publicly before the readiness gate.

## Milestone 4 questions

Decide these while implementing and testing the remaining processing workflow:

- How reviewer corrections and approval relate to immutable extracted candidates
- How candidate occurrences, registrations, classifications, and modality map
  into the canonical domain after review
- How venue matches and unresolved locations are reviewed
- How canonicalization avoids accidental duplicates and preserves provenance
- What limited change or duplicate behavior, if any, is necessary for the first
  safe vertical path

Record the resulting durable behavior only after it is verified.

## Later questions

- API resource and filter semantics belong to the API milestone.
- Map provider and interaction details belong to the discovery-interface
  milestone.
- Change handling, source cadence, and operational recovery belong to
  personal-use hardening.
- New retrieval methods belong to the source that demonstrates their need.
- Hosting, monitoring, authentication, and rollout belong to public-readiness
  work.
