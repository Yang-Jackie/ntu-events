# NTU Events

NTU Events is a personal-first event ingestion and discovery application. The
repository contains a Django API, a Next.js web application, a generated
TypeScript API contract, and the existing Telegram ingestion research harness.

## Prerequisites

- Node.js 24 LTS, provisioned from the repository declaration by pnpm 11
- Corepack with pnpm 11
- Docker Desktop with Docker Compose
- Python 3.13 and `uv` only when running the Telegram research harness on the host

## Initial setup

1. Copy `.env.example` to `.env` and replace local secrets.
2. Install JavaScript dependencies through Corepack:

   ```powershell
   corepack pnpm install
   ```

3. Build the GeoDjango backend image:

   ```powershell
   corepack pnpm backend:build
   ```

4. Apply migrations. Docker Compose starts PostgreSQL/PostGIS automatically:

   ```powershell
   corepack pnpm db:migrate
   ```

5. Create a local Django Admin account:

   ```powershell
   docker compose run --rm backend python apps/backend/manage.py createsuperuser
   ```

6. Verify the generated OpenAPI schema and TypeScript contract:

   ```powershell
   corepack pnpm api:check
   ```

## Development

Run the applications in separate terminals:

```powershell
corepack pnpm dev:backend
corepack pnpm dev:web
```

- Django Admin: `http://localhost:8000/admin/`
- Django health: `http://localhost:8000/api/v1/health/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Next.js: `http://localhost:3000/`
- Next.js health: `http://localhost:3000/api/health`

Run all non-mutating checks with:

```powershell
corepack pnpm check
```

Run Django management commands inside the backend container:

```powershell
docker compose run --rm backend python apps/backend/manage.py <command>
```

The Telegram research entry point remains host-operated. Install its Python
environment when needed:

```powershell
python -m uv sync
python -m uv run telegram-ingestion
```

If `uv` is available directly on `PATH`, the shorter equivalent is:

```powershell
uv run telegram-ingestion
```

Runtime Telegram content remains under ignored `storage/`. Future application
raw content uses ignored `var/raw/`.
