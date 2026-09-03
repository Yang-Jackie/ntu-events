# High-Level Technical Notes

This file is a short working summary. `TECHNICAL_SPECIFICATION.md` is
authoritative for durable technical direction, and `IMPLEMENTATION_PLAN.md`
is authoritative for progress.

## Current state

- The product is owner-operated and non-public.
- Telegram broadcast channels are the first production ingestion source.
- Source pipelines end at the persisted EventCandidate boundary. Candidate
  creation, matching, reconciliation, plan application, and Event provenance
  remain source-neutral; canonicalization has its own decision-provider boundary.
- Source material, processing records, and candidates are inspectable.
- Structurally valid candidates retain business-rule problems as candidate issues.
- Every candidate keeps an immutable extracted payload and an editable effective
  payload. Only BLOCKED candidates are editable; both valid repairs and newly
  extracted candidates enter READY, and creation of the candidate's sole plan
  moves it to PROCESSED.
- Ingestion and canonicalization are separate processes at the EventCandidate
  boundary. Ingestion jobs finish after candidate persistence. One globally
  locked, serial canonicalization worker consumes every unplanned READY
  candidate and traces model work back through its extraction provenance.
- Matching retrieves the 10 nearest indexed titles plus bounded structured
  lookups, applies a fixed additive score led by 65% title weight, and keeps at
  most five canonical Events scoring at least 30%. Missing fields do not change
  the denominator, no identity gate applies, and dates at least 120 days apart
  subtract 20 points.
- No match automatically adds a draft Event. Matched candidates use the model to
  choose one ADD, UPDATE, or LINK_ONLY action from stored match evidence.
- Plan application is atomic, idempotent, referentially strict, and protected
  against stale target graphs. Source links, observations, and EventRevision
  snapshots preserve provenance and applied history.
- Reconciliation sees the latest committed Event graph. Manual edits to
  source-derived fields are not durable overrides and may be replaced by a later
  automatic UPDATE; publication and verification controls remain owner-owned.
- Milestone 4A remains active for matching evaluation and recovery behavior
  before the canonical event API begins in Milestone 5.

## Durable guardrails

- Keep source observations separate from canonical product data.
- Preserve provenance and enough evidence to explain automated output.
- Treat source content and provider output as untrusted.
- Keep user-visible decisions in backend-owned workflows.
- Never guess missing event or location facts.
- Make reruns safe and reject writes based on stale Event graphs.
- Do not expose the product publicly before the readiness gate.

## Remaining Milestone 4A questions

- Which additional true-duplicate, follow-up, separate-edition, and false-match
  cases should calibrate the implemented shortlist weights and threshold
- How rejected, failed, and stale plans are retried or regenerated during
  repeated owner operation

## Milestone 5 questions

After Milestone 4A, decide these while implementing and testing the first useful
event API:

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
- Broader canonical change handling, source cadence, and operational recovery
  beyond deduplication belong to personal-use hardening.
- New retrieval methods belong to the source that demonstrates their need.
- Hosting, monitoring, authentication, and rollout belong to public-readiness
  work.
