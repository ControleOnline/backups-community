from backups import cli


def test_cli_prints_created_artifact_and_runs_maintenance(monkeypatch, app_config, capsys) -> None:
    artifact = app_config.backup.directory / "created.sql.gz"
    maintained = []
    monkeypatch.setattr(cli, "load_config", lambda _: app_config)
    monkeypatch.setattr(cli.BackupService, "run", lambda _: artifact)
    monkeypatch.setattr(cli, "run_maintenance", lambda config: maintained.append(config))
    assert cli.main(["config.json"]) == 0
    assert capsys.readouterr().out.strip() == str(artifact)
    assert maintained == [app_config]


def test_cli_reports_configuration_error(capsys) -> None:
    assert cli.main(["missing.json"]) == 1
    assert "Configuration file not found" in capsys.readouterr().err


def test_cli_rejects_shell_action_parameters() -> None:
    parser = cli.build_parser()
    try:
        parser.parse_args(["config.json", "backup"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Unexpected shell parameters must be rejected")
