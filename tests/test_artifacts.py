import gzip
from pathlib import Path

from backups.artifacts import _replace_stream, rewrite_schema_references


class ChunkedReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def read(self, size: int = -1) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


class CollectingWriter:
    def __init__(self) -> None:
        self.data = b""

    def write(self, value: bytes) -> None:
        self.data += value


def test_replace_stream_handles_schema_reference_across_chunk_boundary() -> None:
    reader = ChunkedReader([b"CREATE VIEW v AS SELECT * FROM `old", b"_db`.users;"])
    writer = CollectingWriter()

    _replace_stream(reader, writer, b"`old_db`.", b"`new_db`.")

    assert writer.data == b"CREATE VIEW v AS SELECT * FROM `new_db`.users;"


def test_rewrites_compressed_schema_references(tmp_path: Path) -> None:
    source = tmp_path / "backup.sql.gz"
    destination = tmp_path / "rewritten.sql.gz"
    with gzip.open(source, "wb") as handle:
        handle.write(b"CREATE VIEW v AS SELECT * FROM `gestaoTechlog`.whatsapp;")

    rewrite_schema_references(source, destination, "gestaoTechlog", "frethical_staging")

    with gzip.open(destination, "rb") as handle:
        assert handle.read() == (b"CREATE VIEW v AS SELECT * FROM `frethical_staging`.whatsapp;")
