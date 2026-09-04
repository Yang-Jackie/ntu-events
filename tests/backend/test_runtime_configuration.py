from pathlib import Path


def test_compose_publishes_backend_and_database_on_loopback_only() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:${POSTGRES_PORT:-5432}:5432"' in compose
