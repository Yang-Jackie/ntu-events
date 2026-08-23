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

## Source revisions and older Telegram edits

When edited content is fetched, its changed content produces a new raw document,
extraction, and candidate observation that now enters matching and
canonicalization. Normal Telegram retrieval revisits only a bounded overlap, so
edits older than that window may not be observed. Broader edit-discovery cadence
belongs to personal-use hardening.

## Local runtime network boundary

Docker Compose currently publishes PostgreSQL and Django through host port
mappings while also providing development defaults. Before the event API exposes
canonical data, make the owner-only boundary explicit by binding development
services to loopback or implementing an approved private-access control. Django
`ALLOWED_HOSTS` alone is not a network access boundary.

## Django 6 URL form transition

The current Admin tests pass with `RemovedInDjango60Warning` messages because
Django 6 will change the default scheme assumed by form URL fields. Review the
existing URL-entry behavior and opt into the intended scheme explicitly before
upgrading.
