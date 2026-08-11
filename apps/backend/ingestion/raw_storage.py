from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class StoredRawObject:
    storage_key: str
    content_hash: str


class RawContentStorage(Protocol):
    def save(self, content: bytes, *, suffix: str) -> StoredRawObject: ...


class LocalRawContentStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def save(self, content: bytes, *, suffix: str = ".bin") -> StoredRawObject:
        normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        content_hash = hashlib.sha256(content).hexdigest()
        now = datetime.now(UTC)
        relative = Path(f"{now:%Y/%m/%d}/{now:%Y%m%dT%H%M%S%fZ}-{uuid4().hex}{normalized_suffix}")
        destination = (self.root / relative).resolve()
        if self.root not in destination.parents:
            raise ValueError("raw storage destination escaped its configured root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        return StoredRawObject(storage_key=relative.as_posix(), content_hash=content_hash)
