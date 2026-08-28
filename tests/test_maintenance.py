import os
from pathlib import Path

from backups.maintenance_service import prune_old_files, rotate_log, run_maintenance


def test_prunes_only_old_matching_files(tmp_path: Path) -> None:
    old = tmp_path / "db_old.sql.gz"
    recent = tmp_path / "db_recent.sql.gz"
    unrelated = tmp_path / "keep.txt"
    for path in (old, recent, unrelated):
        path.write_text("data", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(recent, (900_000, 900_000))
    deleted = prune_old_files(tmp_path, 5, 1_000_000, "db_*.sql*")
    assert deleted == 1
    assert not old.exists()
    assert recent.exists()
    assert unrelated.exists()


def test_rotates_oversized_log_and_respects_keep_count(tmp_path: Path) -> None:
    log = tmp_path / "backup.log"
    log.write_text("12345", encoding="utf-8")
    (tmp_path / "backup.log.1").write_text("previous", encoding="utf-8")
    assert rotate_log(log, max_bytes=4, keep_files=2) is True
    assert log.read_text(encoding="utf-8") == ""
    assert (tmp_path / "backup.log.1").read_text(encoding="utf-8") == "12345"
    assert (tmp_path / "backup.log.2").read_text(encoding="utf-8") == "previous"


def test_run_maintenance_reports_actions(app_config) -> None:
    app_config.backup.directory.mkdir()
    app_config.logging.file.parent.mkdir()
    backup = app_config.backup.directory / "source_db_old.sql.gz"
    backup.touch()
    os.utime(backup, (100, 100))
    app_config.logging.file.write_text("x" * 2048, encoding="utf-8")
    result = run_maintenance(app_config, now=4_000_000)
    assert result.backups_deleted == 1
    assert result.log_rotated is True
