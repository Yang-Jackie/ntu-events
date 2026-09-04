# High-Level Technical Notes

This file is a short working summary. `TECHNICAL_SPECIFICATION.md` is
authoritative for durable technical direction, and `IMPLEMENTATION_PLAN.md`
is authoritative for progress.

## Current state

- The product is owner-operated and non-public.
- Telegram broadcast channels are the first production ingestion source.
- Ingestion stops at persisted EventCandidates; a separate source-neutral worker
  matches and canonicalizes READY candidates.
- Plans are inspectable, validated, transactional, idempotent, and rejected when
  their target Event graph is stale.
- Source evidence, model invocations, candidate decisions, observations, and
  automated Event revisions remain inspectable.

## Current focus

Milestone 6 is active:

- Consume the generated Event API client rather than duplicating its contract
- Select the map library and render reviewed building or standalone venue points
- Keep map bounds, list results, filters, and URL state synchronized
- Keep online-only and unresolved-location occurrences visible in the list when
  no physical-location filter is active

## Durable guardrails

- Keep source observations separate from canonical product data.
- Preserve enough provenance to explain automated output.
- Treat source content and provider output as untrusted.
- Keep user-visible decisions in backend-owned workflows.
- Never guess missing event or location facts.
- Reject writes based on stale Event graphs.
- Keep the product non-public until the owner approves the readiness gate.
