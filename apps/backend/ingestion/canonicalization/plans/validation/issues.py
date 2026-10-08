from typing import Any


def hard_issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "message": message,
        "severity": "ERROR",
        "blocks_application": True,
    }
