from backups import maintenance_cli


def test_maintenance_cli_reports_counts(monkeypatch, app_config, capsys) -> None:
    monkeypatch.setattr(maintenance_cli, "load_config", lambda _: app_config)

    assert maintenance_cli.main(["config.json"]) == 0
    output = capsys.readouterr().out
    assert "backups_deleted=0" in output
    assert "log_rotated=false" in output


def test_maintenance_cli_reports_missing_config(capsys) -> None:
    assert maintenance_cli.main(["missing.json"]) == 1
    assert "Configuration file not found" in capsys.readouterr().err
