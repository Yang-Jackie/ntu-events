# 1. Telethon client is rebuilt per job
Fix: Lazy-initialize the Telethon client, and store the client once it is initialized

# 2. Telethon clients would touch the same session file

# 3. IngestionJob vs CrawlRun
They're basically a 1:1 map
Fix: Drop CrawlRun cleanly

# 4. Edited messages are re-screened but never re-extracted
```MessageScreening``` has ```UniqueConstraint(("job", "source_representation"))```

When a job had already created a row in ```MessageScreening``` but then became stale $\rightarrow$ the job is re-queued. On re-execution of that job, the worker will re-queue a new ```MessageScreening``` with same ```job``` and ```source_representation```, violating ```MessageScreening```'s unique constraint.

# 5. Edited messages are re-screened but never re-extracted

# 6. The candidate contract and validator cannot safely drive canonicalization
Several domain states are either lost or incorrectly accepted:

```start_date``` and at least one occurrence are mandatory, although the specification says date-less candidates must be retained for review.

An occurrence-scoped registration has no occurrence index or other owner reference.

Classification codes are unrestricted strings.

Registration ordering and date/time consistency are not validated.

```UNKNOWN``` occurrence status has no canonical-domain equivalent.

Keyword matching marks "Microsoft Teams" as a physical VALID event, while a real hybrid location containing "LT19A and Zoom" would be rejected as online-only.

A focused check accepted an invented format code, a reversed registration window, and Microsoft Teams, then returned VALID. Resolve this before Milestone 4, likely with a versioned candidate schema, explicit modality/eligibility, controlled classification enums, occurrence-owner references, and semantic validators.