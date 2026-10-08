# NTU Events

An owner-operated, map-first event discovery product for NTU. Django owns event
data, ingestion, review, and publication; Next.js presents published events.

Start with the [development guide](docs/DEVELOPMENT.md) for local setup and
commands. The [implementation plan](docs/IMPLEMENTATION_PLAN.md) records current
progress and the next delivery goal.

| Directory              | Purpose                                                  |
| ---------------------- | -------------------------------------------------------- |
| `apps/backend/`        | Django domains, API, Admin, and workers                  |
| `apps/web/`            | Next.js discovery interface                              |
| `packages/api-client/` | Generated API contract and TypeScript client             |
| `tools/`               | Telegram research and ingestion evaluation               |
| `scripts/`             | Small development and operational commands               |
| `tests/`               | Python tests grouped by backend domain or tool           |
| `fixtures/`            | Version-controlled regression inputs                     |
| `docs/`                | Product scope, architecture, behavior, and development   |
| `var/`                 | Ignored raw evidence, evaluation runs, and audit reports |
| `storage/`             | Ignored research output and Telegram sessions            |

See [architecture](docs/ARCHITECTURE.md) for ownership boundaries. Codex and
Claude Code share [AGENTS.md](AGENTS.md); [CLAUDE.md](CLAUDE.md) imports it.
