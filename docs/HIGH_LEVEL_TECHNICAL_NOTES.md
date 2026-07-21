# High-Level Technical Notes

## Delivery posture

Build privately for the owner first. Public deployment requires sustained evidence of utility, coverage, data quality, manageable review, and rerun safety.

## Resolve first

- **Start with real data:** Select one accessible source and save 50–100 representative samples before finalizing the schema.
- **Use constrained LLM-first ingestion:** Let the model interpret content and explore approved pages through bounded, traced, read-only browser tools; prohibit authentication, submissions, purchases, CAPTCHA bypass, and other external state changes.
- **Define identity:** Distinguish an event, recurring series, occurrence, source representation, and source update.
- **Model time precisely:** Support exact, date-only, all-day, multi-day, multi-session, recurring, postponed, and cancelled occurrences.
- **Fix cardinalities:** Decide which fields belong to events versus occurrences; allow multiple organizers, categories, audiences, venues, sources, and registration options where needed.
- **Separate category dimensions:** Model topic, format, purpose, audience, and organizer type as distinct facets.
- **Establish venue data:** Validate canonical buildings, coordinates, aliases, outdoor locations, room mappings, and usage rights.
- **Define pipeline states:** Make crawling, extraction, validation, canonicalization, review, and publication inspectable and safely repeatable.
- **Protect manual decisions:** Automated reprocessing must not silently overwrite corrections or merge decisions.
- **Define query semantics:** Specify ongoing/upcoming behavior, time overlap, recurrence expansion, map grouping, pagination, and ordering.
- **Validate extraction:** Evaluate LLM extraction and browser-agent behavior against versioned fixtures, traces, and labelled expected results before relying on automation.

## First personal-use vertical slice

Build one LLM-first source workflow through constrained browser exploration where needed, raw storage, extraction, review, venue resolution, canonical event creation, API retrieval, and a minimal local map/list for the owner. Re-running it must not create duplicates, and manual corrections must survive reprocessing.

## Owner decisions before public release

Decide personal access mode, minimum source coverage, evidence thresholds and observation period, and rollout type.

## Can wait

Map provider, task queue, scheduler, OCR, exact language-model provider, advanced deduplication, a polished frontend, production hosting, and public-launch operations.
