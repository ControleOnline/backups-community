# Backups Community

Extensible Python CLI for backup, restore, post-restore hooks, and retention
maintenance. The first provider supports MySQL; providers for PostgreSQL and
file storage can be added without changing the root entrypoint.

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

Copy `examples/mysql.json` to a local file under `config/` and put the database
passwords in that local JSON file:

```bash
cp examples/mysql.json config/production.json
```

The `destination` object is optional. Use `destinations` when the same source
dump must be restored into more than one target database. When no destination is
configured, the workflow only creates a backup. When one or more destinations
are present, the workflow creates one backup artifact and restores that same
artifact into each destination using its configured restore strategy. Paths in
the JSON file are resolved relative to that file.

## Run

The root command receives only the configuration file. All operational values
come from that file:

```bash
python backup.py config/production.json
```

The timestamped artifact name is generated internally. When `destination` or
`destinations` is configured, that exact artifact is restored without a dynamic
shell argument.

To run every configured backup in one cron entry, omit the JSON argument:

```bash
python backup.py
```

In this mode the project reads `.env` from the repository root. `BACKUPS_CONFIG_GLOB`
selects local JSON files, and `BACKUPS_SERVER_CATALOGS` names one or more MySQL
catalog databases that contain a multi-tenancy `servers` table:

```dotenv
BACKUPS_CONFIG_GLOB=config/*.json
BACKUPS_SERVER_CATALOGS=main,legacy
BACKUPS_SERVER_MAIN_HOST=127.0.0.1
BACKUPS_SERVER_MAIN_PORT=3306
BACKUPS_SERVER_MAIN_DATABASE=controleonline
BACKUPS_SERVER_MAIN_USERNAME=backup_catalog
BACKUPS_SERVER_MAIN_PASSWORD=change-me
```

Each catalog is read from `servers.backup_config`. That column must contain the
same JSON object accepted by file configs, including source credentials,
destination credentials, restore strategy, hooks, logging, and retention. The
catalog connection also uses a temporary MySQL option file, so its password is
not exposed in the process list.

The workflow accepts command hooks in four stages:

- `pre_backup.commands`: before the dump is generated.
- `pre_restore.commands`: before restoring into the configured target.
- `post_restore.commands`: after restore and before promotion when using
  `validated_swap`.
- `post_backup.commands`: after each destination restore, including promotion
  when configured. With no destination, it runs once after the dump.

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

Safe template variables are available in command arguments, directories,
environment values, and candidate database names:

- `{source.database}`
- `{destination.database}`
- `{candidate.database}`
- `{artifact}`
- `{timestamp}`

## Restore strategies

`destination.restore_strategy` defaults to `direct`, which restores the newly
created backup directly into the configured destination database. The same
setting is accepted by every item in `destinations`.

Use `validated_swap` when the destination must not be touched until the restored
data has been validated. The workflow:

1. creates a compressed source dump;
2. restores it into a candidate database from `candidate_database_pattern`;
3. runs `post_restore.commands` against the candidate context;
4. validates `required_tables` and optionally compares source/candidate objects
   from `information_schema.TABLES`;
5. dumps the candidate and promotes that dump into the final destination;
6. drops the candidate in a `finally` block when `drop_candidate_on_exit` is
   true.

For Frethical-style refreshes, see `examples/mysql.json`. The example creates a
single dump from `gestaoTechlog` and restores it into `frethical_staging` and
`frethical_dev` through validated candidate databases, validates required
objects, then runs commands such as password updates and Doctrine migrations
with no shell wrapper.

## Scheduling

```cron
0 4 * * * cd /opt/backups-community && /usr/bin/python3 backup.py
```

Log rotation and old-backup retention run automatically at the end of every
successful backup round; no separate maintenance cron entry is required.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

The tests use fakes for MySQL processes and never connect to a real database.
