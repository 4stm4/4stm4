# GitHub Traffic Collection

`tools/github_traffic_collector.py` collects repository traffic from the GitHub REST API and stores it in `data/github_traffic.sqlite3`.

GitHub only exposes repository traffic for the last 14 days. Run the collector daily if you want a longer history.

## Repositories

Default repositories:

- `4stm4`
- `nanodhcp`
- `tinyWiFi`
- `nervum`
- `testum`
- `pyjobkit`
- `ehatrom`
- `ocultum`

## Token

Use a fine-grained GitHub personal access token.

1. Open GitHub settings.
2. Go to Developer settings.
3. Open Personal access tokens.
4. Choose Fine-grained tokens.
5. Generate a new token.
6. Select the `4stm4` owner and the repositories listed above.
7. Set repository permissions:
   - Administration: Read-only
8. Create the token and store it outside the repository.

The token user must have push access to each repository. Without that access, GitHub returns `403 Forbidden` for traffic endpoints.

## Run

```sh
export GITHUB_TOKEN=github_pat_...
export GITHUB_OWNER=4stm4
python3 tools/github_traffic_collector.py
```

The default database path is:

```text
data/github_traffic.sqlite3
```

Collect only selected repositories:

```sh
python3 tools/github_traffic_collector.py --repo nanodhcp --repo tinyWiFi
```

Use a custom database path:

```sh
python3 tools/github_traffic_collector.py --database data/github_traffic.sqlite3
```

## Cron

Edit the crontab:

```sh
crontab -e
```

Example daily run:

```cron
GITHUB_TOKEN=github_pat_...
GITHUB_OWNER=4stm4

15 3 * * * cd /path/to/4stm4 && /usr/bin/python3 tools/github_traffic_collector.py >> data/github_traffic.log 2>&1
```

Keep the token out of committed files.

## SQLite Tables

- `collector_runs`: one row per collector run.
- `repo_views`: daily views and unique visitors per repository.
- `repo_clones`: daily clones and unique cloners per repository.
- `repo_referrers`: daily snapshots of top referrers.
- `repo_paths`: daily snapshots of popular content paths.

Inspect the database:

```sh
sqlite3 data/github_traffic.sqlite3 '.tables'
sqlite3 data/github_traffic.sqlite3 'select owner, repo, timestamp, count, uniques from repo_views order by timestamp desc limit 20;'
```

## Metric Interpretation

Views and unique visitors are usually the strongest traffic signal.

Referrers show where attention is coming from.

Popular paths show which README pages, source files, releases, or docs people open.

Do not treat clones as strong human interest. Clones can be noisy and bot-like.

Better signals:

- views
- unique visitors
- referrers
- popular content
- stars
- issues
- forks

## Manual Testing

There is no project test setup in this repository. Basic local checks:

```sh
python3 -m py_compile tools/github_traffic_collector.py
python3 tools/github_traffic_collector.py --help
```

With a valid token, run the collector and inspect the resulting SQLite tables.
