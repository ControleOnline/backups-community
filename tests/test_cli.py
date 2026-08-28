from backups import cli


def test_cli_prints_created_artifact(monkeypatch, app_config, capsys) -> None:
    artifact = app_config.backup.directory / "created.sql.gz"
    monkeypatch.setattr(cli, "load_config", lambda _: app_config)
    monkeypatch.setattr(cli.BackupService, "run", lambda _: artifact)
    assert cli.main(["config.toml"]) == 0
    assert capsys.readouterr().out.strip() == str(artifact)


def test_cli_reports_configuration_error(capsys) -> None:
    assert cli.main(["missing.toml"]) == 1
    assert "Configuration file not found" in capsys.readouterr().err


def test_cli_rejects_shell_action_parameters() -> None:
    parser = cli.build_parser()
    try:
        parser.parse_args(["config.toml", "backup"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Unexpected shell parameters must be rejected")
