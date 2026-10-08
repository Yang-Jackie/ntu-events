# Development guide

NTU Events combines a Django backend, a Next.js discovery interface, and a
generated TypeScript API client. Docker Compose runs PostgreSQL/PostGIS and the
backend processes; the web app runs on the host. Telegram is the first implemented
ingestion source. Publication is controlled by the owner through Django Admin.

## Find the right document

| Need                                             | Document                                                   |
| ------------------------------------------------ | ---------------------------------------------------------- |
| Product purpose and scope                        | [Business requirements](BUSINESS_REQUIREMENTS.md)          |
| Current progress, next goal, and exit conditions | [Implementation plan](IMPLEMENTATION_PLAN.md)              |
| System behavior and guardrails                   | [Technical specification](TECHNICAL_SPECIFICATION.md)      |
| Code ownership and dependency boundaries         | [Architecture](ARCHITECTURE.md)                            |
| Known engineering issues                         | [Engineering concerns](TODO.md)                            |
| Venue data and maintenance                       | [NTU/NIE venue catalog](sources/ntu_campus_locations.md)   |
| Telegram source boundary and research harness    | [Telegram source notes](sources/telegram_text_research.md) |
| Future official-site ingestion research          | [CCDS source research](sources/ntu_ccds_events.md)         |

## Work with Codex or Claude Code

Start either tool from the repository root. [AGENTS.md](../AGENTS.md) contains
the shared working rules and directs the agent to task-relevant docs.
[CLAUDE.md](../CLAUDE.md) imports that file so Claude Code uses the same rules
without a second copy to maintain. This follows the supported
[Codex instruction convention](https://developers.openai.com/codex/guides/agents-md/)
and [Claude Code import mechanism](https://code.claude.com/docs/en/memory#import-additional-files).

After changing instructions, start a new Codex session. In Claude Code, use
`/context` to confirm the memory files loaded. A useful first task is to summarize
the active milestone, applicable constraints, and verification commands.

Keep machine-specific preferences in user-level configuration or ignored
`CLAUDE.local.md` and `.claude/settings.local.json` files. Project decisions and
progress belong in the shared docs so both tools can find them. No repository
hooks, custom skills, or agent-specific permissions are required for this setup.

## Prerequisites

- Node.js 24 and Corepack. The root `package.json` pins pnpm and declares the
  Node runtime provisioned by pnpm.
- Docker with Docker Compose; Docker Desktop is the usual Windows setup.
- Python 3.13 and `uv` only for the optional host-operated research harness.

Run the commands below from the repository root. Examples use PowerShell.

## Set up locally

1. If `.env` does not exist, copy `.env.example` to `.env` and set a local
   `DJANGO_SECRET_KEY`. Keep credentials in the ignored `.env`.
2. For custom web settings, create ignored `apps/web/.env.local` with:

   ```dotenv
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_BASEMAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
   ```

   Django reads the root `.env`; Next.js reads env files under `apps/web`.
   The web defaults already work locally, so this step is optional. Never place
   secrets in `NEXT_PUBLIC_*` variables because they can reach browser code.

3. Install dependencies, build the backend image, and apply migrations:

   ```powershell
   corepack pnpm install --frozen-lockfile
   corepack pnpm backend:build
   corepack pnpm db:migrate
   ```

   Compose starts PostgreSQL/PostGIS as needed. Migrations also load the reviewed
   venue catalog and building points. A fresh database contains no ingested Events.

4. Create your local Admin account and check the API contract:

   ```powershell
   docker compose run --rm backend python apps/backend/manage.py createsuperuser
   corepack pnpm api:check
   ```

## Run the applications

Run the backend and web app in separate terminals:

```powershell
corepack pnpm dev:backend
corepack pnpm dev:web
```

Start workers when processing queued ingestion or canonicalization:

```powershell
corepack pnpm dev:worker
corepack pnpm dev:canonicalization
```

| Service              | Local URL                            |
| -------------------- | ------------------------------------ |
| Web discovery        | http://localhost:3000/               |
| Django Admin         | http://localhost:8000/admin/         |
| Published Event API  | http://localhost:8000/api/v1/events/ |
| Interactive API docs | http://localhost:8000/api/docs/      |
| OpenAPI schema       | http://localhost:8000/api/schema/    |
| Backend health       | http://localhost:8000/api/v1/health/ |
| Web health           | http://localhost:3000/api/health     |

Compose binds backend and database host ports to loopback. For a local-only web
session, use `corepack pnpm dev:web --hostname 127.0.0.1`; the default web command
does not explicitly restrict its listening address.

The map defaults to OpenFreeMap Liberty. Its on-map switch or
`?basemap=openstreetmap` selects the local OpenStreetMap raster comparison.
Current basemap limitations are in the technical specification.

## Ingest Telegram events

1. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `OPENAI_API_KEY` in `.env`.
   Authenticate in an interactive terminal:

   ```powershell
   corepack pnpm telegram:login
   ```

2. List public broadcast channels, then register the selected list indexes:

   ```powershell
   corepack pnpm telegram:channels --limit 20
   corepack pnpm telegram:channels --limit 20 --register 1 3
   ```

   Replace `1 3` with your selections from the current listing.

3. With both workers running, queue active sources:

   ```powershell
   corepack pnpm ingest:telegram --all-active
   ```

   Use repeated `--source <database-id>` options instead of `--all-active` for
   specific sources. `--inline` runs ingestion in the command process for
   troubleshooting; canonicalization still runs separately.

4. Inspect jobs, candidates, plans, and Events in Admin. Ingestion stops at
   candidates; canonicalization processes READY candidates. Set an Event's
   publication status to PUBLISHED when you want it visible in local discovery.
   Neither worker publishes Events automatically.

Avoid running login, channel discovery, and ingestion concurrently against the
same saved Telegram session; session coordination remains a known issue.
`corepack pnpm ingest:schedule` enqueues due registered sources when invoked;
Compose does not install a recurring scheduler.

All three model stages are configured independently in `.env`. Defaults and
retry behavior are documented in the technical specification. Recreate the
backend and worker containers after changing their environment configuration.
Relevant, uncertain, and failed source bodies are stored under ignored `var/raw/`;
authorization sessions are stored under ignored `storage/telegram/sessions/`.

## Verify changes

Choose checks that cover the change. `package.json` is the command reference.

| Change                              | Commands                                                                                                                                                              |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python formatting and lint          | `docker compose run --rm backend ruff format --check apps/backend tools scripts tests`; `docker compose run --rm backend ruff check apps/backend tools scripts tests` |
| Focused Python tests                | `docker compose run --rm backend pytest tests/backend/ingestion/candidates/`                                                                                          |
| Django configuration and migrations | `corepack pnpm django:check`; `corepack pnpm migrations:check`                                                                                                        |
| Web lint, types, and tests          | `corepack pnpm --filter @ntu-events/web lint`; `corepack pnpm typecheck`; `corepack pnpm --filter @ntu-events/web test`                                               |
| Web build                           | `corepack pnpm build`                                                                                                                                                 |
| API changes                         | `corepack pnpm api:generate`, then `corepack pnpm api:check`                                                                                                          |
| Documentation formatting            | `corepack pnpm exec prettier --check README.md AGENTS.md CLAUDE.md "docs/**/*.md" "tools/**/*.md" packages/api-client/README.md`                                      |
| Full application checks             | `corepack pnpm check`                                                                                                                                                 |

Full checks include Python and web formatting, lint, types, Django and migration
checks, API drift checks, and tests. They require Docker and a test database;
ordinary tests use saved or mocked provider inputs. Documentation formatting and
the web build are separate checks. Format only intended files when making a
small change. Do not edit generated API files by hand.

For venue catalog or geography updates, use the maintenance commands in the
venue source notes. `venues:update` fetches live NTU directories and writes the
catalog and facilities snapshot. `venues:check` also fetches live directories
and compares the regenerated result, including its generation date; it is not
an offline regression check.

## Offline ingestion evaluation summaries

For owner-approved model experiments, keep source evidence, reference answers,
provider responses, and result rows under ignored
`var/evaluations/ingestion/<run>/`. Freeze the inputs and grading rules before paid requests. Replay plan application only in a separate,
explicitly named disposable database; never reuse the working database as an
evaluation sandbox. Benchmark-only instructions do not change production policy.

The reusable evaluation package in `tools/ingestion-evaluation/` grades saved results:

```powershell
docker compose run --rm --no-deps backend python -m ntu_events_evaluation.scoring --results var/evaluations/ingestion/<run>/progress.json --references var/evaluations/ingestion/<run>/reference_answers.json
```

This command is offline: it does not select evidence, call a model, or write to
the database. The reference manifest must be APPROVED and linked to the same
dataset hash as the results. Saved results must also match the frozen reference
hash. Each reference case must be READY. Reference files
define expected event counts or allowed canonicalization actions and targets,
plus checks on selected source-grounded fields in the resulting Event graph.
The summary keeps model/effort combinations, stages, and sampling groups separate.
Passing those checks is not proof that every factual detail is correct; review
ambiguous facts and synthesized prose independently.

The helper also supplies a conservative serial-request budget ledger. A live
experiment must reserve its maximum output and all possible HTTP attempts before
generation, record reasoning tokens as part of total output rather than billing
them twice, and retain an upper-cost allowance for attempts with unknown usage.
Its price table covers Standard API Luna 6 and Luna 5.6 rates verified on
8 October 2026. Recheck provider pricing and processing-tier assumptions before
future paid runs; token-derived costs are estimates, not invoice reconciliation.

For preparation, replay, and runner options, see the
[evaluation tool guide](../tools/ingestion-evaluation/README.md). Local audit reports
belong in ignored `var/audits/`. For a read-only ingestion-session summary, run
`docker compose run --rm backend python scripts/monitor_ingestion_session.py --request-id <id>`.
Summarize timestamped worker logs with:

```powershell
docker compose logs --no-color --timestamps ingestion-worker canonicalization-worker | python scripts/summarize_worker_logs.py
```

`scripts/check_map_markers.cjs` accepts JSON on stdin with
`all_events_for_markers` and `all_canonical_map_inputs` arrays of API-shaped Events.
It uses the web marker builder to report coordinate collisions and requires the
installed web dependencies.

## Optional research harness

The Telegram harness lives in `tools/telegram-research/src/ntu_events_ingestion/`
and explores source material without canonicalizing or publishing Events:

```powershell
uv sync --frozen
uv run telegram-ingestion
```

Its outputs go to ignored `storage/telegram/runs/`. See the Telegram source notes
for its source boundary. Application development uses the container commands above.
