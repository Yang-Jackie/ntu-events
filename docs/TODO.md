# Current Engineering Concerns

This is a short list of known implementation concerns, not a second roadmap.
Milestone ownership and completion status belong in `IMPLEMENTATION_PLAN.md`.

## Telegram client and session lifecycle

The worker currently rebuilds the underlying Telethon client for each job, and
separate commands can touch the same saved session file. Decide and test a
resource-lifetime and mutual-exclusion approach that works for the worker,
login, channel discovery, and inline troubleshooting paths.

## Retried job persistence

A reclaimed job can encounter records written by its earlier attempt. Review
screening and invocation uniqueness so retrying a partially completed or stale
job resumes safely instead of violating constraints or duplicating work.

## Edited-message reprocessing

Screening takes changed message content into account, but extraction reuse can
still treat an older successful extraction for the same source representation
as current. Tie reuse to the processed content or otherwise make the changed
content state explicit.
