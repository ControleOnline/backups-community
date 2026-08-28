# Backups Community

Extensible Python CLI for backup, restore, and retention maintenance. The first
provider supports MySQL; providers for PostgreSQL and file storage can be added
without changing the root entrypoints.

## Requirements

- Python 3.11+
- `mysqldump` and `mysql` available in `PATH`

No Python runtime dependency is required.

The root scripts run directly from a checkout. An optional system installation
also exposes the `controle-backup` commands:

```bash
python -m pip install .
```

## Configuration

Copy `examples/mysql.toml` to a local file under `config/` and set the password
environment variable referenced by `password_env`:

```bash
cp examples/mysql.toml config/production.toml
export BACKUP_SOURCE_PASSWORD='source-secret'
export BACKUP_DESTINATION_PASSWORD='destination-secret'
```

The `[destination]` section is optional. When it is absent, the workflow only
creates a backup. When it is present, the workflow creates the backup and then
restores that newly created artifact into the configured destination. Paths in
the TOML file are resolved relative to that file.

## Run

The root command receives only the configuration file. All operational values
come from that file:

```bash
python backup.py config/production.toml
python maintenance.py config/production.toml
```

The timestamped artifact name is generated internally. When `[destination]` is
configured, that exact artifact is restored without a dynamic shell argument.

## Scheduling

```cron
0 2 * * * cd /opt/backups-community && /usr/bin/python3 backup.py config/production.toml
30 3 * * * cd /opt/backups-community && /usr/bin/python3 maintenance.py config/production.toml
```

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

The tests use fakes for MySQL processes and never connect to a real database.
