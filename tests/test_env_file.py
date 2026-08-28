from pathlib import Path

from backups.env_file import load_env_file


def test_loads_simple_dotenv_values(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# ignored\n"
        "BACKUPS_CONFIG_GLOB=config/*.json\n"
        "BACKUPS_SERVER_MAIN_PASSWORD='secret value'\n",
        encoding="utf-8",
    )

    assert load_env_file(path) == {
        "BACKUPS_CONFIG_GLOB": "config/*.json",
        "BACKUPS_SERVER_MAIN_PASSWORD": "secret value",
    }
