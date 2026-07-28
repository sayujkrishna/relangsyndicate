# Healthchecks in Go

This is an original Go implementation of the core HTTP contract of the
Healthchecks service. It intentionally uses only Go's standard library.

## Build and run on Ubuntu 24.04

```bash
sudo apt-get update
sudo apt-get install -y golang-go
cd target
source setup.sh
PORT=8000 ./healthchecks
```

The server listens on `127.0.0.1:8000` by default. Set `PORT` to change it.
It stores its durable state in `healthchecks-data.json`; set `HC_DATA_FILE` to
choose another state-file path.

For a fresh, deterministic local state, request `POST /__test/reset/` (or
`GET` while testing). It provisions an API key of 32 `X` characters, a
read-only key of 32 `R` characters, and a ping key of 22 `p` characters.

## Implemented HTTP functionality

- UUID and slug-based pings (`success`, `start`, `fail`, `log`, and numeric
  exit-status variants), including body storage and the ping history.
- API v1, v2, and v3 check listing, creation, update, deletion, pause/resume,
  ping history, flip history, CORS preflight, and key-based authorization.
- Simple timeout checks, five-field cron schedules (wildcards, lists, ranges,
  and steps), and daily `HH:MM` on-calendar schedules; checks become late/down
  based on their expected next run and grace interval.
- Status endpoint, metrics gate, project/check badge responses, and an
  original Go dashboard, check-detail pages, and a concurrent persisted store.

The original Django application also includes a web dashboard, accounts,
WebAuthn, database persistence, email SMTP ingestion, reports, and many
third-party notification providers. Those UI and provider-specific layers are
outside this standalone HTTP-monitoring implementation.
