# Engineering concerns

This is a short list of known implementation concerns, not a second roadmap.
Milestone ownership and completion status belong in the
[implementation plan](IMPLEMENTATION_PLAN.md).

## Discovery result coverage (Milestone 8)

`apps/web/app/page.tsx` builds filter choices from the first unfiltered API page
and map markers from the displayed filtered page. The API returns 50 Events per
page, so available filter values and map coverage can be incomplete. Decide how
results, markers, counts, and filters represent the agreed search scope; verify
that behavior across page boundaries rather than implying complete coverage.

## Time and registration discovery (Milestone 8, if selected)

The list API filters by date, not minute/hour windows or registration status.
Detail provides registration timing and status where supplied; capacity status
is retained source information, not a live availability feed. If the design uses
these capabilities, agree handling of unknown or stale facts and any needed API
changes. Avoid inferring that an event is ongoing or registration is open solely
from a partial schedule or the presence of a link.

## Telegram client and session lifecycle (Milestone 10)

The worker currently rebuilds the underlying Telethon client for each job, and
separate commands can touch the same saved session file. Decide and test a
resource-lifetime and mutual-exclusion approach that works for the worker,
login, channel discovery, and inline troubleshooting paths.

## Source revisions and older Telegram edits (Milestone 10)

When edited content is fetched, its changed content produces a new raw document,
extraction, and candidate observation that now enters matching and
canonicalization. Normal Telegram retrieval revisits only a bounded overlap, so
edits older than that window may not be observed. Broader edit-discovery cadence
belongs to personal-use hardening.

## Django 6 URL form transition (dependency upgrade)

The current Admin tests pass with `RemovedInDjango60Warning` messages because
Django 6 will change the default scheme assumed by form URL fields. Review the
existing URL-entry behavior and opt into the intended scheme explicitly before
upgrading.
