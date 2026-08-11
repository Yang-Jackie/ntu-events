from __future__ import annotations

import os


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is missing. Copy .env.example to .env and set it locally; "
            "do not paste credentials into chat or commit them."
        )
    return value
