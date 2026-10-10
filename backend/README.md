# Transformer Digital Twin backend

FastAPI + synchronous SQLAlchemy 2.0/psycopg 3 + PostgreSQL 16.
All project changes are under `backend/` on `feature/backend-api`.
Read `docs/CONTEXT.md` first when continuing this project.

## Backend setup

Prerequisites: Python 3.11+ (3.12 for Docker), PostgreSQL 16, and PowerShell.
Docker Desktop/Compose supplies PostgreSQL and persistent Mosquitto for the complete demo.
All commands below run in backend/. Local development examples use the existing database
on 55432 and uvicorn on 8002, avoiding the service already using port 8000 on this machine.

```powershell
cd C:\Transformer-backend\backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
$env:DATABASE_URL = "postgresql+psycopg://transformer:transformer@127.0.0.1:55432/transformer"
$env:ML_BACKEND = "stub"
$env:MQTT_ENABLED = "false"
# If the existing dev database container is stopped:
docker start transformer-backend-phase1-pg
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe scripts/seed_demo.py
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

On a new machine, use the Compose demo below to provision the database/broker, or create
a PostgreSQL database/account and set DATABASE_URL appropriately. Do not run migration
downgrades against retained demo/production data. Shell variables override .env settings;
copying the example alone does not point a local process at the database's host port.
No nameplate rating is provided by default. Optional --rated-power-kva, --rated-voltage-hv,
--rated-voltage-lv, --rated-current-a, --cooling-class and --oil-type configure supplied values.
--rows defaults 2000; --transformer-id defaults TX-001; --no-ml skips analytics/hooks.
Seed is idempotent. Seed --reset requires --yes; reset scripts refuse ENV=production.

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/health
Invoke-RestMethod http://127.0.0.1:8002/health/ready
Invoke-RestMethod http://127.0.0.1:8002/api/v1/transformers/TX-001/latest
```

/health is liveness/connectivity and returns 200 even when degraded. /health/ready checks
startup, database/schema head and ML reachability/importability and returns 503 on failure.
OpenAPI is at /docs, /redoc and /openapi.json. Errors use the shared error envelope and
all responses carry X-Request-ID. UTC times, nullable measurements, versions and proxy
risk wording are covered in [docs/api.md](docs/api.md).

### Complete Docker demo

```powershell
./scripts/demo.ps1 up
./scripts/demo.ps1 seed
Invoke-RestMethod http://127.0.0.1:8001/api/v1/transformers/TX-001/latest
./scripts/demo.ps1 reset -Yes
./scripts/demo.ps1 seed
./scripts/demo.ps1 down
```

Default host ports: HTTP 8001, PostgreSQL 55433, MQTT 51885. They coexist with earlier dev
containers; named volumes retain data across down/up. Set DEMO_HTTP_PORT/DEMO_DB_PORT/
DEMO_MQTT_PORT in .env to override. The image runs as non-root with runtime dependencies
only; entrypoint waits for DB and migrates before uvicorn. See [docs/docker.md](docs/docker.md)
for exact direct Compose/log commands, HTTP seed/reset, MQTT and merging into the team stack.

### Troubleshooting

- PowerShell JSON quoting: native docker/mosquitto arguments can lose JSON quotes. Prefer
  Invoke-RestMethod with a PowerShell object converted to JSON, or pipe a JSON file to
  `docker compose ... exec -T mqtt mosquitto_pub ... -s`. Python paho publishing also avoids
  shell quoting. A valid small HTTP example:

```powershell
$demoPayload = @{ transformer_id='TX-HTTP'; timestamp='2026-01-01T00:00:00Z'; oil_temperature=42; oil_level=8; source_name='simulator'; scenario_id='SCN_HEALTHY' }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8002/api/v1/telemetry -ContentType 'application/json' -Body ($demoPayload | ConvertTo-Json -Compress)
```

- Stale-server 404: check the base URL, process and /openapi.json; the process on port 8000
  may be a different service or an older backend. Restart uvicorn from backend/ or rebuild
  and recreate the Compose backend. Demo reset 404 is expected while disabled.
- Empty historical charts: request anchor=latest or explicit aware UTC from/to. The seed
  uses fixed January 2026 timestamps, so anchor=now can return no rows.
- Database/readiness failure: check DATABASE_URL, pg_isready, alembic current/upgrade head,
  and container logs. /health 200 alone does not confirm migrations are applied.
- MQTT absent: check /api/v1/ingest/mqtt/status, enabled flag, host/port/topic, unique client
  IDs and broker health. Acknowledgement is not database commit; monitor errors/drops.
- API reset 403: set DEMO_RESET_ENABLED=true, non-empty DEMO_ADMIN_TOKEN, send matching
  X-Admin-Token, and use a non-production environment. CLI still requires --yes.
- Need a fresh seed: pause publishers/replays, run scripts/reset_demo.py --yes (optionally
  --include-transformers), then seed again. Reset is global and does not clear MQTT counters.

## Verify

```powershell
cd C:\Transformer-backend\backend
$env:DATABASE_URL = "postgresql+psycopg://transformer:transformer@127.0.0.1:55432/transformer"
$env:TEST_DATABASE_URL = $env:DATABASE_URL
$env:MQTT_TEST_HOST = "127.0.0.1"
$env:MQTT_TEST_PORT = "51883"
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m alembic check
```

For a new machine using the running demo Compose stack, set DATABASE_URL/TEST_DATABASE_URL
to postgresql+psycopg://transformer:transformer@127.0.0.1:55433/transformer and
MQTT_TEST_PORT=51885 instead. The earlier dev setup uses 55432/51883. The offline-broker
regression reserves 51884, so keep it unused during tests.

Integration fixtures create a uniquely named disposable database and drop it afterward;
the test account needs CREATEDB. Unit tests still run without `TEST_DATABASE_URL`, but
PostgreSQL tests will be skipped. Acceptance requires a configured server with no skips.

To exercise the migration CLI on a fresh disposable database (downgrade removes its tables):

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade base
.venv/Scripts/python.exe -m alembic upgrade head
```

## Database decisions

- Six tables: transformers, telemetry, analytics, alerts, maintenance_records, ingestion_runs.
- All timestamps use TIMESTAMPTZ; application and migration connections set timezone to UTC.
- Canonical numeric telemetry and protection fields remain nullable; missing values stay missing.
- Protection uses nullable SmallInteger with binary CHECK constraints.
- Telemetry has a unique asset/timestamp key; analytics has a unique telemetry reference.
- Telemetry, analytics and alerts use asset/timestamp DESC indexes; alerts also indexes status.
- Analytic scores have the required range checks. All analytic outputs are nullable.
- Version metadata on analytics is required. Optional JSON values store SQL NULL for Python None.
- Status and severity values use VARCHAR + CHECK. Ingestion lifecycle is RUNNING/COMPLETED/FAILED.
- No transformer nameplate ratings are supplied by defaults.
- Fault predictions refer to proxy alarm/trip targets, not confirmed physical failures.
- The initial migration was autogenerated then reviewed for constraints, indexes, TIMESTAMPTZ,
  JSONB, BIGSERIAL keys, nullability and foreign-key-safe downgrade order.

## Files created

See `docs/FILES.md` for the complete tracked deliverable list.

## Phase 2 schema contracts

- `TelemetryIn` accepts canonical fields plus optional `source_name` and `scenario_id` metadata.
  `TelemetryInput` remains a compatibility alias. `TelemetryOut` supports ORM conversion.
- Batch validation reads `MAX_BATCH_SIZE` from settings (default 5000); records must be a list.
- Shared validators reject extra/excluded fields, naive timestamps and non-finite floats.
  Valid timestamps normalize to UTC; protection booleans normalize to integer binary values.
- Unverified thermal/oil measurements have no unit conversions or numeric range constraints.
  Power factors use [-1, 1], probability scores use [0, 1], and health index uses [0, 100].
- `MLResultIn` and `AnalyticsOut` require schema/feature/model versions; all analytic outputs
  can be null. Health component names and reason codes follow `docs/CONTEXT.md`.
- Transformer nameplate fields have no rating defaults. Patch `exclude_unset=True`
  distinguishes omitted configuration from explicitly supplied nulls.
- `LatestStateOut` can represent an asset with no telemetry or analytics yet; feature and model
  versions remain null until available. All Out schemas accept SQLAlchemy attributes.
- Completeness helpers count each non-null measurement, including zero, out of 21 fields.
  Identity and metadata are excluded. Missing any of the seven critical fields sets the flag.
- Shared error handlers use the typed `ErrorResponse` envelope and omit tracebacks from responses.

Phase 2 validation: 311 tests passed, with no skips, against PostgreSQL 16. Ruff check and
format check passed. This includes every Phase 1 regression and ORM conversion for the new
schemas. The existing Starlette/httpx dependency deprecation warning remains.
Production endpoints are unchanged; validation endpoints exist only in test applications.

## Phase 3 ML integration

`app/ml_client/` defines the protocol, deterministic stub, lazy Python adapter, HTTP
adapter, safe failure wrapper and cached factory. Set ML_BACKEND to select an adapter;
ML_TIMEOUT_SECONDS and ML_MAX_RETRIES configure HTTP behavior. httpx is now a runtime
dependency; pandas is not required. No endpoints or persistence were added in this phase.

See `docs/ml-integration-notes.md` for the exact interface, full HTTP JSON examples,
history-window contract, stub rules and open questions for Person 1.

Phase 3 verification: 403 tests passed with no skips, including all prior PostgreSQL
regressions. Ruff and format checks passed; all new files were checked for raw source
column names, and ML client imports were checked for database/dataframe dependencies.
The existing Starlette/httpx dependency deprecation warning remains.

## Phase 4 ingestion

Live, batch and replay endpoints share the single telemetry-ingestion service. Telemetry
and analytics persist together, duplicates are idempotent, and ingestion runs record
quality statistics and replay progress. Chunks contain 1000 valid rows; MAX_BATCH_SIZE
remains 5000 by default. ML and alert-hook failures are isolated.

See `docs/ingestion.md` for endpoint contracts, error classification, history/deque
semantics, replay behavior and verification commands. The MQTT transport is described in docs/mqtt.md.
The app now closes its cached HTTP ML client on shutdown.

Phase 4 verification: 435 tests passed with no skips; Ruff and formatting passed.
The 10,000-row stub load took 44.977 seconds; its duplicate reload took 30.158 seconds.
See `docs/phase4-acceptance.md` for every acceptance result and both summaries.

## Phase 5 MQTT

MQTT_ENABLED remains false by default. Enabling it starts a non-blocking paho v2
consumer with a bounded queue and one ingestion worker. MQTT telemetry uses the
same ingest_record service, idempotency and ML failure behavior as HTTP/replay.
GET /api/v1/ingest/mqtt/status exposes connection state, counters and a rejection ring.
See docs/mqtt.md for simulator payloads, Docker broker setup, publishing and tests.

Phase 5 verification: 486 tests passed with no skips against real PostgreSQL and
Docker Mosquitto; Ruff and formatting passed. See docs/phase5-acceptance.md for
acceptance coverage, operational limits and reproduction commands.

## Phase 6 dashboard read API

Transformer configuration, latest state, paged telemetry/health/analytics, alerts,
maintenance, scenarios and bounded SQL trends now serve the Streamlit dashboard.
Use anchor=latest for old demo/replay data. Latest state includes demo_mode and
data_source; null gaps and insufficient analytics remain visible. CORS defaults to
both localhost Streamlit origins. See docs/read-api-notes.md for all contracts and limits.
Migration 0002 adds the missing maintenance transformer/timestamp index; run
.venv/Scripts/python.exe -m alembic upgrade head before maintenance window reads.

Phase 6 verification: 557 tests passed with no skips against real PostgreSQL and
Mosquitto; Ruff, formatting, migration round-trip/check and the natural 20,000-row
index plan passed. See docs/phase6-acceptance.md for the detailed results.

## Phase 7 alerts and maintenance

Ingestion now evaluates protection and ML alert candidates, refreshes active alerts,
escalates severity and resolves them after configurable clear records. PLAN/URGENT analytics
persist deduplicated maintenance records. Lifecycle endpoints support acknowledgement,
resolution, completion and dismissal with the shared error envelope. Apply migration 0003
with `alembic upgrade head` before running this version. See [docs/alerts.md](docs/alerts.md)
for rules, JSON severity configuration, concurrency ordering, endpoints and examples, and
[docs/phase7-acceptance.md](docs/phase7-acceptance.md) for verification results.

## Phase 8 performance and hardening

Batch ingestion now prefilters duplicates and uses chunked bulk telemetry/analytics
insertion, cached lifecycle evaluation and one transformer lock per chunk. Single HTTP,
MQTT and replay still use ingest_record. The measured paired benchmarks and SQL stage
profiles are in [docs/performance.md](docs/performance.md). No migration is introduced.

GET `/health/ready` checks startup, database/schema and the configured ML integration;
`/health` remains unchanged. Every HTTP response carries X-Request-ID. See
[docs/hardening.md](docs/hardening.md) for readiness semantics, error correlation,
OpenAPI snapshot regeneration, source/wording guards and per-package coverage checks.
The Phase 8 acceptance results are in [docs/phase8-acceptance.md](docs/phase8-acceptance.md).

## Final demo and handoff phase

Deterministic seed/reset scripts, Docker packaging, real captured examples and team handoff
are complete. See [docs/handoff.md](docs/handoff.md), [docs/known-limitations.md](docs/known-limitations.md),
[examples/client.py](examples/client.py), [examples/requests.http](examples/requests.http) and
[docs/phase9-acceptance.md](docs/phase9-acceptance.md). No canonical schema, migrations,
ingestion, alert rules or ML behavior changed. The optional demo reset is disabled by
default and refuses production. The earlier snapshot remains intact, allowing the new
admin endpoint as an additive API change.


## Physics persistence and read resource (unified plan Phase 5)

This is the physics project's Phase 5, separate from the earlier MQTT work
above. See [physics integration](../docs/physics_integration.md) and the
[Phase 5 report](../docs/phase5_report.md). No frontend changes are included.

Install the existing local ML package and backend dependencies using the
repository setup. From this backend directory, using that configured interpreter:

```powershell
python -m alembic upgrade head
# Optional only after an explicit supported profile is published:
$env:PHYSICS_ENABLED = "true"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
Invoke-RestMethod http://127.0.0.1:8002/health/ready
Invoke-RestMethod http://127.0.0.1:8002/api/v1/transformers/TX-001/physics
```

PHYSICS_ENABLED defaults false. Migration 0005 adds empty isolated tables,
without installing fixture parameters. Keep DATABASE_URL in the existing
environment configuration; migrate before enabling the hook. With the flag off,
the read resource returns all ten unavailable components. There is no HTTP
profile-write endpoint. Trusted operator code can call
`app.services.physics_service.publish_profile(session, explicit_snapshot,
source_name="documented-source")` and `session.commit()`. It requires a registered
asset, explicit inputs and immutable version/source/evidence identities. The
operator must establish actual units, applicability and provenance. Synthetic
cases must retain their synthetic labels; records are not automatically verified.

Use `?at=<aware ISO timestamp>` for a controlled historical cutoff. The 31-day
selector returns the selected event or a complete unavailable envelope and
never carries an older READY value forward. Controlled thermal values are
idealized node proxies. Operational standards thermal, ageing, FEM hot-spot,
comparisons, RUL and failure probability are unsupported.

On corruption/incompatible state, publish a new configuration activation and
matching initial temperatures with `recover=True`. Old seeds are not moved.
Exact retries never advance state; late events never replay history. Immutable
records stay resolvable, subject to explicit size/count caps. Downgrading 0005
destroys physics storage; use only on disposable databases or with separately
authorized backup/release procedures.
# Opt-in live synthetic physics demonstration

See [live demo model](../docs/live_physics_demo_model.md) and
[local report/start-stop instructions](../docs/live_physics_simulation_report.md).
From the repository root, with `TEST_DATABASE_URL` supplied securely for a local
PostgreSQL administrator and frontend dependencies already installed:

```powershell
.venv/Scripts/python.exe backend/scripts/live_physics_demo.py --backend-port 8002 --frontend-port 5177 --interval 4
```

This creates a uniquely named disposable database, migrates only it, and starts
the current-source API, separate producer and opt-in current frontend. Ctrl+C
stops the owned children and drops that new database. Occupied ports select the
next available port; the launcher prints the actual URLs. No retained container
is rebuilt/restarted. `ENABLE_PHYSICS_DEMO` (legacy alias
`LIVE_PHYSICS_DEMO_ENABLED`) defaults false and also requires
`PHYSICS_ENABLED`, `ENV=local-demo` and a matching disposable database name.
The demo GET is `/api/v1/demo/transformers/{id}/physics`; the ordinary endpoint,
frozen physics schema and operational restrictions are unchanged. Demo writes
go only into `live_physics_demo_events`, never canonical telemetry or profiles.
Do not run migration `0006` against retained data without a future approved plan.

The single-command PowerShell wrapper `./backend/scripts/Start-LivePhysicsDemo.ps1`
(from repository root) prompts securely for local PostgreSQL access when
`TEST_DATABASE_URL` is absent, then starts this same launcher. `-VerifyApi` tests
the real raw-event/persistence/API path without a browser and cleans up.
`-StopFile <absolute-path>` lets a second terminal request normal owned-resource
cleanup by creating that file. The file must not already exist at startup.
The wrapper registers/simulates all ten IDs from `simulator/config/operational-fleet.json` by default.
Use `-Asset @('ID-A','ID-B')` for other explicitly fictional identities; the same
list is passed to registration, producer and verification. The native Python
launcher uses that same fleet by default and accepts repeated
`--asset` options. Asset identity does not supply a real equipment nameplate.
Raw events are validated and retained inside each demo checkpoint JSON; no new
migration or production telemetry write is needed. See
[data pipeline report](../docs/live_physics_data_pipeline_report.md).
Current configuration/asset verification and exact response samples:
[demo enablement report](../docs/physics_demo_enablement_report.md).
The preferred flag wins over its legacy alias within one settings source.
Constructor values override process environment, which overrides the working
directory's `.env`; settings are cached for the lifetime of the process.
Changing a local `.env` never updates an already running container's environment.

For the complete disposable MQTT/Modbus/analytics/physics stack, from the root:

```powershell
./backend/scripts/Start-TenTransformerDemo.ps1
```

This builds new uniquely tagged images and starts a unique Compose project using
`docker-compose.physics-demo.yml --profile physics-demo`. It enables the
`accepted-telemetry` physics input mode; the existing ingestion transaction
calculates demo results from accepted synthetic MQTT snapshots. It does not run
the standalone producer or write to retained data. PostgreSQL/broker/spool state
uses disposable tmpfs, with no retained volumes. Docker Desktop must be running.
`-CheckOnly` validates Compose without starting services; `-BuildOnly` builds
images without starting services. Stop using `Stop-TenTransformerDemo.ps1
-SessionFile <printed-path>`, which targets only that unique project.
See [ten-transformer integration report](../docs/full_stack_ten_transformer_integration_report.md)
for actual automated results, limitations and manual verification.

