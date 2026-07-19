# High-Level Technical Notes

## Resolve first

- **Start with real data:** Select one accessible source and save 50–100 representative samples before finalizing the schema.
- **Define identity:** Distinguish an event, recurring series, occurrence, source representation, and source update.
- **Model time precisely:** Support exact, date-only, all-day, multi-day, multi-session, recurring, postponed, and cancelled occurrences.
- **Fix cardinalities:** Decide which fields belong to events versus occurrences; allow multiple organizers, categories, audiences, venues, sources, and registration options where needed.
- **Separate category dimensions:** Model topic, format, purpose, audience, and organizer type as distinct facets.
- **Establish venue data:** Validate canonical buildings, coordinates, aliases, outdoor locations, room mappings, and usage rights.
- **Define pipeline states:** Make crawling, extraction, validation, canonicalization, review, and publication inspectable and safely repeatable.
- **Protect manual decisions:** Automated reprocessing must not silently overwrite corrections or merge decisions.
- **Define query semantics:** Specify ongoing/upcoming behavior, time overlap, recurrence expansion, map grouping, pagination, and ordering.
- **Validate extraction:** Evaluate deterministic and model-based extraction against versioned fixtures before relying on automation.

## Architecture question

Decide whether separate Next.js and Django applications provide enough value to justify two runtimes, API-contract management, and additional deployment work.

## First vertical slice

Build one source adapter through raw storage, extraction, review, venue resolution, canonical event creation, API retrieval, and a minimal map/list. Re-running it must not create duplicates, and manual corrections must survive reprocessing.

## Can wait

Map provider, task queue, scheduler, OCR, exact language-model provider, advanced deduplication, and a polished frontend.
