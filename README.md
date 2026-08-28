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

The `[destination]` section is optional for backup-only installations. It is
required for restore operations. Paths in the TOML file are resolved relative
to that file.

## Run

The root command receives the configuration file as its first argument:

```bash
python backup.py config/production.toml backup
python backup.py config/production.toml restore --artifact backups/mydb_20260828T120000Z.sql.gz
python backup.py config/production.toml restore --latest
python maintenance.py config/production.toml
```

`restore --latest` selects the newest artifact matching the configured prefix.
The command refuses to restore when no destination database is configured.

## Scheduling

```cron
0 2 * * * cd /opt/backups-community && /usr/bin/python3 backup.py config/production.toml backup
30 3 * * * cd /opt/backups-community && /usr/bin/python3 maintenance.py config/production.toml
```

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

The tests use fakes for MySQL processes and never connect to a real database.
