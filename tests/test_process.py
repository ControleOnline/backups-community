import gzip
import sys
from pathlib import Path

import pytest

from backups.errors import ProcessError
from backups.process import ProcessRunner


def test_dump_streams_and_compresses_process_output(tmp_path: Path) -> None:
    script = tmp_path / "dump.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write(b'CREATE TABLE test;')\n", encoding="utf-8"
    )
    artifact = tmp_path / "backup.sql.gz"

    ProcessRunner().dump([sys.executable, str(script)], artifact, compressed=True)

    with gzip.open(artifact, "rb") as handle:
        assert handle.read() == b"CREATE TABLE test;"
    assert not (tmp_path / ".backup.sql.gz.partial").exists()


def test_restore_streams_decompressed_input_to_process(tmp_path: Path) -> None:
    script = tmp_path / "restore.py"
    output = tmp_path / "received.sql"
    script.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    artifact = tmp_path / "backup.sql.gz"
    with gzip.open(artifact, "wb") as handle:
        handle.write(b"INSERT INTO test VALUES (1);")

    ProcessRunner().restore([sys.executable, str(script), str(output)], artifact)

    assert output.read_bytes() == b"INSERT INTO test VALUES (1);"


def test_query_sends_statement_and_parses_tab_separated_rows(tmp_path: Path) -> None:
    script = tmp_path / "query.py"
    script.write_text(
        "import sys\n"
        "assert sys.stdin.read() == 'SELECT 1;'\n"
        "sys.stdout.write('whatsapp\\tBASE TABLE\\nview_a\\tVIEW\\n')\n",
        encoding="utf-8",
    )

    rows = ProcessRunner().query([sys.executable, str(script)], "SELECT 1;")

    assert rows == [("whatsapp", "BASE TABLE"), ("view_a", "VIEW")]


def test_failed_dump_removes_partial_artifact(tmp_path: Path) -> None:
    script = tmp_path / "fail.py"
    script.write_text("import sys\nsys.stderr.write('failure')\nsys.exit(7)\n", encoding="utf-8")
    artifact = tmp_path / "backup.sql"

    with pytest.raises(ProcessError, match="status 7: failure"):
        ProcessRunner().dump([sys.executable, str(script)], artifact, compressed=False)

    assert not artifact.exists()
    assert not (tmp_path / ".backup.sql.partial").exists()
