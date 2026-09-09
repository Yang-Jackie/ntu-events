# Telegram Text Source Notes

**Status:** First implemented ingestion source and intended first source for the
retained personal-use trial, with an earlier standalone research harness

## Source boundary

The project processes text and captions from selected public Telegram broadcast
channels visible to the owner's authenticated account.

One registered source represents one channel, and one source representation
identifies one message. Groups, private chats, media-only posts, and media
downloads are outside the current path.

The saved authorization session is sensitive runtime state and remains ignored
by Git.

## Research harness

The host-operated research harness predates the Django application pipeline. It
remains useful for isolated source exploration and does not canonicalize or
publish events.

Setup:

1. Create a Telegram API application at `my.telegram.org/apps`.
2. Add `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `OPENAI_API_KEY` to the
   ignored `.env`.
3. Install with `python -m uv sync`.
4. Run `python -m uv run telegram-ingestion`.

Authorization is stored under ignored `storage/telegram/sessions/`. Research
runs write JSON artifacts under ignored `storage/telegram/runs/`.

The harness retains text and captions, skips media-only posts, and limits access
to public broadcast channels visible to the authorized account.

## Application path

The Django pipeline is the implemented first application source. It provides
durable jobs, incremental retrieval, model-assisted screening and extraction,
selective raw-content retention, provenance, candidate persistence, and Admin
inspection.

Current setup, commands, provider configuration, and operational limits are
documented in the root `README.md`. Avoid duplicating those values here because
they may change with the implementation.

The application pipeline creates reviewable candidates. A separate source-neutral
worker matches and canonicalizes READY candidates; publication remains a later
milestone.

## Current limitations

- Safe Telethon client and session ownership across worker and command paths
- Detection of edited messages older than the configured retrieval overlap
- Future treatment of media and poster content

Cross-cutting operational concerns are tracked in `docs/TODO.md`. Resolve each
limitation in its owning milestone and add focused coverage with the behavior.
