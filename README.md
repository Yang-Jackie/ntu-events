# NTU Events

NTU Events is a personal-first event ingestion and discovery application. The
repository contains a Django API, a Next.js web application, a generated
TypeScript API contract, and the existing Telegram ingestion research harness.

## Prerequisites

- Python 3.13
- `uv`
- Node.js 24 LTS, provisioned from the repository declaration by pnpm 11
- Corepack with pnpm 11
- Docker with Docker Compose

## Initial setup

1. Copy `.env.example` to `.env` and replace local secrets.
2. Install Python dependencies:

   ```powershell
   uv sync
   ```

3. Enable pnpm through Corepack and install JavaScript dependencies:

   ```powershell
   corepack enable
   pnpm install
   ```

   If enabling the global Corepack shims requires administrator access, commands
   can be run as `corepack pnpm <command>`.

4. Start PostgreSQL/PostGIS:

   ```powershell
   docker compose up -d database
   ```

5. Apply migrations:

   ```powershell
   uv run python apps/backend/manage.py migrate
   ```

6. Generate the OpenAPI schema and TypeScript contract:

   ```powershell
   pnpm api:generate
   ```

## Development

Run the applications in separate terminals:

```powershell
pnpm dev:backend
pnpm dev:web
```

- Django health: `http://localhost:8000/api/v1/health/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Next.js: `http://localhost:3000/`
- Next.js health: `http://localhost:3000/api/health`

Run all non-mutating checks with:

```powershell
pnpm check
```

The Telegram research entry point remains:

```powershell
uv run telegram-ingestion
```

Runtime Telegram content remains under ignored `storage/`. Future application
raw content uses ignored `var/raw/`.
