from __future__ import annotations

import gzip
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO

from backups.errors import ProcessError


class ProcessRunner:
    def dump(self, command: list[str], output: Path, compressed: bool) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.partial")
        try:
            with tempfile.TemporaryFile() as errors, _writer(temporary, compressed) as writer:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
                assert process.stdout is not None
                shutil.copyfileobj(process.stdout, writer, length=1024 * 1024)
                process.stdout.close()
                return_code = process.wait()
                if return_code:
                    raise ProcessError(_process_message("mysqldump", return_code, errors))
            temporary.replace(output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def restore(self, command: list[str], artifact: Path) -> None:
        with tempfile.TemporaryFile() as errors, _reader(artifact) as reader:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
            assert process.stdin is not None
            try:
                shutil.copyfileobj(reader, process.stdin, length=1024 * 1024)
            except BrokenPipeError:
                pass
            finally:
                process.stdin.close()
            return_code = process.wait()
            if return_code:
                raise ProcessError(_process_message("mysql", return_code, errors))

    def query(self, command: list[str], statement: str) -> list[tuple[str, ...]]:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.run(
                command,
                input=statement.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=errors,
                check=False,
            )
            if process.returncode:
                raise ProcessError(_process_message("mysql", process.returncode, errors))
        output = process.stdout.decode("utf-8", errors="strict")
        return [tuple(line.split("\t")) for line in output.splitlines() if line]


def _writer(path: Path, compressed: bool) -> BinaryIO:
    return gzip.open(path, "wb") if compressed else path.open("wb")


def _reader(path: Path) -> BinaryIO:
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def _process_message(program: str, return_code: int, errors: BinaryIO) -> str:
    errors.seek(0)
    detail = errors.read(4096).decode("utf-8", errors="replace").strip()
    return f"{program} exited with status {return_code}" + (f": {detail}" if detail else "")
