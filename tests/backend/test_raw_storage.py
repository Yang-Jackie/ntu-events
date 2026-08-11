from pathlib import Path

from ingestion.raw_storage import LocalRawContentStorage


def test_raw_storage_never_overwrites_an_observation(tmp_path: Path) -> None:
    storage = LocalRawContentStorage(tmp_path)
    first = storage.save(b"same content", suffix=".html")
    second = storage.save(b"same content", suffix=".html")

    assert first.content_hash == second.content_hash
    assert first.storage_key != second.storage_key
    assert (tmp_path / first.storage_key).read_bytes() == b"same content"
    assert (tmp_path / second.storage_key).read_bytes() == b"same content"
