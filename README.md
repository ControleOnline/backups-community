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

Copy `examples/mysql.json` to a local file under `config/` and set the password
environment variable referenced by `password_env`:

```bash
cp examples/mysql.json config/production.json
export BACKUP_SOURCE_PASSWORD='source-secret'
export BACKUP_DESTINATION_PASSWORD='destination-secret'
```

The `destination` object is optional. When it is absent, the workflow only
creates a backup. When it is present, the workflow creates the backup and then
restores that newly created artifact into the configured destination. Paths in
the JSON file are resolved relative to that file.

## Run

The root command receives only the configuration file. All operational values
come from that file:

```bash
python backup.py config/production.json
```

The timestamped artifact name is generated internally. When `destination` is
configured, that exact artifact is restored without a dynamic shell argument.

After the optional restore, every entry in `post_backup.commands` runs in order.
Commands are argument arrays and are executed directly, without a shell:

```json
"post_backup": {
  "commands": [
    {
      "command": ["php", "bin/console", "doctrine:migrations:migrate", "--no-interaction"],
      "directory": "../api-community",
      "environment": {"APP_ENV": "staging"}
    },
    {
      "command": ["php", "bin/console", "app:sanitize-environment"],
      "directory": "../api-community"
    }
  ]
}
```

Directories are resolved relative to the JSON file. The process environment is
inherited and the configured `environment` values override it for that command.
A failing command stops the workflow with a non-zero exit code.

## Scheduling

```cron
0 2 * * * cd /opt/backups-community && /usr/bin/python3 backup.py config/production.json
```

Log rotation and old-backup retention run automatically at the end of every
successful backup round; no separate maintenance cron entry is required.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

The tests use fakes for MySQL processes and never connect to a real database.
