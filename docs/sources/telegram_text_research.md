# Telegram Text Ingestion Research Harness

This local harness collects public broadcast-channel text visible to the
owner's Telegram account and produces provisional event candidates. It tests
source-neutral shapes against unstructured club announcements; it is not the
production ingestion service and does not canonicalize or publish events.

## Setup and guided run

1. Create a Telegram API application at `my.telegram.org/apps`.
2. Copy `.env.example` to `.env` and fill in `TELEGRAM_API_ID`,
   `TELEGRAM_API_HASH`, and `OPENAI_API_KEY`. Never commit or share them.
3. Install with `python -m uv sync`.
4. Run `python -m uv run telegram-ingestion`.

The first run prompts for Telegram login and saves authorization under ignored
`storage/telegram/sessions/`. Later runs reuse it. The guided entry point lists
up to 20 recent broadcast channels, accepts multiple comma-separated choices,
asks for message count, preserves raw text, confirms the maximum OpenAI calls,
extracts candidates, and reports the output directory.

Useful alternatives:

```powershell
python -m uv run telegram-ingestion login
python -m uv run telegram-ingestion channels
python -m uv run telegram-ingestion run --messages 30 --max-calls 200
python -m uv run telegram-ingestion run --force
```

`gpt-5-nano` is the low-cost default. Up to 200 new requests are allowed per
run, with up to 10 processed concurrently. One message is processed per request
with minimal reasoning effort, low output verbosity and one retry. A cache keyed
by content, model, prompt and schema versions avoids repeat calls; `--force`
bypasses it. Override concurrency with `--concurrency`.

## Output and limits

Each run writes standard JSON—not JSONL—under
`storage/telegram/runs/<UTC timestamp>/`: `raw_messages.json`,
`extraction_results.json`, `event_candidates.json`, `failures.json`, and, after
model processing, `run_manifest.json`.

Text and media captions are retained. Media-only posts are skipped and media is
not downloaded. Only broadcast channels are listed; groups and private chats
are excluded. Access is limited to what Telegram shows the authorized account.
Runtime content and sessions are ignored by Git. Candidate fields remain
provisional until results from Telegram and other sources are compared.

## Production-path ingestion

The Django production path is separate from the research harness but reuses its
validated source assumptions. One registered `Source` represents one public
broadcast channel and one `SourceRepresentation` represents one channel message.
Groups, private chats, media-only posts, and media downloads remain excluded.

Configure and authenticate once:

```powershell
corepack pnpm telegram:login
corepack pnpm telegram:channels -- --limit 20 --register 1 3
corepack pnpm db:migrate
```

Queue registered channels and run the worker in another terminal:

```powershell
corepack pnpm ingest:telegram -- --all-active
corepack pnpm dev:worker
```

For direct troubleshooting without the sustained worker:

```powershell
corepack pnpm ingest:telegram -- --source 1 --inline
```

The source Admin action, commands, and external scheduled invocation all create
the same durable request/job records. Each job processes one channel. Screening
uses `gpt-5-nano` in batches of 20; `EVENT` and `UNCERTAIN` messages proceed to
`gpt-5-mini` extraction in batches of five. At most ten OpenAI requests run
concurrently. The worker reuses one OpenAI client for connection pooling.

Full content is retained under ignored `var/raw/` only for relevant, uncertain,
or failed messages. Confirmed non-event bodies are discarded after screening,
while their Telegram identity, content hash, screening result, prompt/schema
versions, and model invocation remain in PostgreSQL. Extraction produces
reviewable candidates only; it does not canonicalize or publish events.
