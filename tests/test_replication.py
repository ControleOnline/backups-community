import json
from datetime import datetime
from zoneinfo import ZoneInfo

from backups.config import load_config
from backups.models import ReplicationAppConfig, ReplicationHealthSettings, ScheduleSettings
from backups.providers.mysql_replication import MySQLReplicationProvider
from backups.schedule import is_due


def test_loads_replication_configuration(tmp_path):
    path = tmp_path / "replication.json"
    path.write_text(
        json.dumps(
            {
                "type": "replication",
                "schedule": {"time": "00:05", "timezone": "America/Sao_Paulo"},
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
    assert config.schedule.time == "00:05"


def test_replication_schedule_is_checked_in_configured_timezone():
    schedule = ScheduleSettings("00:05", "America/Sao_Paulo")
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    assert is_due(schedule, datetime(2026, 9, 3, 0, 5, tzinfo=sao_paulo))
    assert not is_due(schedule, datetime(2026, 9, 3, 0, 6, tzinfo=sao_paulo))


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
