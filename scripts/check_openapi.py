"""Fail when the committed OpenAPI schema differs from Django's current schema."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANAGE_PY = REPOSITORY_ROOT / "apps" / "backend" / "manage.py"
COMMITTED_SCHEMA = REPOSITORY_ROOT / "packages" / "api-client" / "openapi.json"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ntu-events-openapi-") as temporary_directory:
        generated_schema = Path(temporary_directory) / "openapi.json"
        subprocess.run(
            [
                sys.executable,
                str(MANAGE_PY),
                "spectacular",
                "--file",
                str(generated_schema),
                "--format",
                "openapi-json",
                "--validate",
                "--fail-on-warn",
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )

        if load_json(generated_schema) != load_json(COMMITTED_SCHEMA):
            print("OpenAPI schema is stale. Run: pnpm api:generate", file=sys.stderr)
            return 1

    print("OpenAPI schema is current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
