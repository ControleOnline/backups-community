import json

from backups.config import load_config
from backups.models import ReplicationAppConfig, ReplicationHealthSettings
from backups.providers.mysql_replication import MySQLReplicationProvider


def test_loads_replication_configuration(tmp_path):
    path = tmp_path / "replication.json"
    path.write_text(
        json.dumps(
            {
                "type": "replication",
                "replication": {
                    "provider": "mysql",
                    "source": {"host": "source", "database": "app", "username": "dump", "password": "one"},
                    "source_status": {"host": "source", "database": "mysql", "username": "repl", "password": "two"},
                    "replica": {"host": "replica", "database": "mysql", "username": "root", "password": "three"},
                    "database": "app",
                    "repair": {"enabled": True, "actions": ["restart"]},
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert isinstance(config, ReplicationAppConfig)
    assert config.replication.source_status.username == "repl"
    assert config.replication.repair_actions[0].name == "restart"


class FakeProvider:
    def __init__(self, output):
        self.output = output

    def query_vertical(self, database, statement):
        return self.output


def test_mysql_replication_health_parses_status():
    provider = MySQLReplicationProvider(FakeProvider(
        "Replica_IO_Running: Yes\nReplica_SQL_Running: Yes\nSeconds_Behind_Source: 0\n"
    ))
    settings = type("Settings", (), {"replica": object(), "health": ReplicationHealthSettings(30, 0, 0)})
    assert provider.health(settings).healthy
