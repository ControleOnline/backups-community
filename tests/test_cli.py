from backups import cli


def test_cli_prints_created_artifact_and_runs_maintenance(monkeypatch, app_config, capsys) -> None:
    artifact = app_config.backup.directory / "created.sql.gz"
    maintained = []
    monkeypatch.setattr(cli, "discover_configs", lambda _: [app_config])
    monkeypatch.setattr(cli.BackupService, "run", lambda _: artifact)
    monkeypatch.setattr(cli, "run_maintenance", lambda config: maintained.append(config))

    assert cli.main(["config.json"]) == 0

    assert capsys.readouterr().out.strip() == str(artifact)
    assert maintained == [app_config]


def test_cli_reports_discovery_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "discover_configs",
        lambda _: (_ for _ in ()).throw(cli.BackupError("missing config")),
    )

    assert cli.main(["missing.json"]) == 1

    assert "missing config" in capsys.readouterr().err


def test_cli_runs_every_discovered_config_and_returns_failure_if_any_fail(
    monkeypatch, app_config, capsys
) -> None:
    calls = []

    class FakeService:
        def __init__(self, config) -> None:
            self.config = config

        def run(self):
            calls.append(self.config)
            if len(calls) == 1:
                raise cli.BackupError("first failed")
            return self.config.backup.directory / "ok.sql.gz"

    monkeypatch.setattr(cli, "discover_configs", lambda _: [app_config, app_config])
    monkeypatch.setattr(cli, "BackupService", FakeService)
    monkeypatch.setattr(cli, "run_maintenance", lambda config: None)

    assert cli.main([]) == 1

    assert len(calls) == 2
    captured = capsys.readouterr()
    assert "first failed" in captured.err
    assert "ok.sql.gz" in captured.out
