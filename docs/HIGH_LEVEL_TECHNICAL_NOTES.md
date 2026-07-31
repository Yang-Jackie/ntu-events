# High-Level Technical Notes

## Delivery posture

Build privately for the owner first. Public deployment requires sustained evidence of utility, coverage, data quality, manageable review, and rerun safety.

## Agreed core rules

- A source representation is distinct from an event and retains its identity
  across future revisions; revision processing is deferred.
- A representation may produce several candidates, and an event may eventually
  have several source representations.
- A series groups events only. An occurrence is a continuous, independently
  meaningful attendance block; midnight alone never splits it.
- The domain has no agenda-item model.
- Registration is owned by exactly one series, event, or occurrence, with
  closest-scope inheritance.
- All scheduling uses Singapore local date and time without a general timezone model.
- Initial canonicalization is idempotent and create-only. It creates non-public
  draft or review-required events and never updates existing canonical records.
- Cross-source matching, source conflicts, content changes, corrections,
  postponements, cancellations, and automatic publication are deferred.
- Event format, topic, purpose, audience, and organizer type are separate,
  editable classification facets. The first four are plural event
  relationships.
- The initial venue map covers the main campus and adjacent NIE. Buildings and
  landmarks are seeded from current official sources; rooms are added as
  production inputs require them, and raw extracted locations never create
  canonical venue records automatically. Seeded map points remain null until a
  reviewed authoritative coordinate import is available.

See `TECHNICAL_SPECIFICATION.md` section 7 for the authoritative model.

## Resolve before scaffolding

- **Start with real data:** Select one accessible source and save 50–100 representative samples before finalizing the schema.
- **Use source-appropriate ingestion:** Prefer reliable APIs, feeds, exports, embedded metadata, or managed structured results when available. Use the model to interpret unstructured content and explore approved pages through bounded, traced, read-only browser tools; prohibit authentication, submissions, purchases, CAPTCHA bypass, and other external state changes.
- **Define pipeline states:** Make crawling, extraction, validation, canonicalization, review, and publication inspectable and safely repeatable.
- **Protect manual decisions:** Automated reprocessing must not silently overwrite corrections or merge decisions.
- **Define query semantics:** Specify ongoing/upcoming behavior, time overlap, recurrence expansion, map grouping, pagination, and ordering.
- **Validate interpretation:** Evaluate deterministic mappings, provider outputs, LLM extraction, and browser-agent behavior against versioned fixtures, provenance, traces, and labelled expected results before relying on automation.

## First personal-use vertical slice

Build one source-appropriate workflow using deterministic mapping or LLM-first unstructured extraction, with constrained browser exploration where needed, raw storage, provider provenance, review, venue resolution, canonical event creation, API retrieval, and a minimal local map/list for the owner. Re-running it must not create duplicates, and manual corrections must survive reprocessing.

## Owner decisions before public release

Decide personal access mode, minimum source coverage, evidence thresholds and observation period, and rollout type.

## Can wait

Map provider, task queue, scheduler, OCR, exact language-model provider, advanced deduplication, a polished frontend, production hosting, and public-launch operations.
