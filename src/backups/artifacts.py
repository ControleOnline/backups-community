import gzip
from pathlib import Path
from typing import BinaryIO


def rewrite_schema_references(
    source: Path, destination: Path, old_schema: str, new_schema: str
) -> None:
    old = f"`{old_schema}`.".encode()
    new = f"`{new_schema}`.".encode()
    with _reader(source) as reader, _writer(destination) as writer:
        _replace_stream(reader, writer, old, new)


def _replace_stream(reader: BinaryIO, writer: BinaryIO, old: bytes, new: bytes) -> None:
    carry = b""
    while chunk := reader.read(1024 * 1024):
        data = carry + chunk
        safe_end = max(0, len(data) - len(old) + 1)
        position = 0
        while (index := data.find(old, position)) >= 0 and index < safe_end:
            writer.write(data[position:index])
            writer.write(new)
            position = index + len(old)
        writer.write(data[position:safe_end])
        carry = data[max(position, safe_end) :]
    writer.write(carry.replace(old, new))


def _reader(path: Path) -> BinaryIO:
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def _writer(path: Path) -> BinaryIO:
    return gzip.open(path, "wb") if path.suffix == ".gz" else path.open("wb")
