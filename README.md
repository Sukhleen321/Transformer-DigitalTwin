# Transformer Digital Twin

React monitoring console, FastAPI/PostgreSQL telemetry backend, existing empirical
analytics, and separate physics/numerical-verification packages. The sole project
specification is [the canonical physics-first plan](Transformer_DigitalTwin_Physics_First_Implementation_Plan.md).
Approved Phase 0–6 work is preserved. [Phase 7 release validation](docs/phase7_report.md)
records the actual results and the **NOT READY** release decision.

The two-node thermal estimator supports controlled simulations only. FEM is an
independent synthetic steady-conduction benchmark, not a transformer model.
Operational hot-spot predictions, insulation ageing, real RUL, failure probabilities
and estimator–FEM comparison are unavailable. IEEE/IEC equation text remains
unverified; no standards compliance or field accuracy is established. See
[model limitations](docs/model_limitations.md) and [exact source locators](docs/physics_references.md).

## Architecture and contracts

Telemetry → existing ingestion/analytics → PostgreSQL → bounded read APIs → console.
Optional physics writes share the ingestion transaction and restore asset-owned
checkpoints. Its separate read route is
`GET /api/v1/transformers/{transformer_id}/physics`. No FEM solve runs in the API.
The console's Thermal & loading view reads that resource on entry, asset change,
Refresh or error Retry. All ten components retain independent units, provenance,
status and nullable values. Missing data never becomes an invented temperature.

- [Current architecture baseline](docs/architecture_current.md) and
  [physics persistence/read integration](docs/physics_integration.md).
- [Frozen physics contract 1.0.0](docs/physics_contract.md) and
  [existing 1.1.0 contract](docs/contracts/hackathon-v1.1.md).
- [Backend setup](backend/README.md), [frontend setup](frontend/README.md),
  [FEM benchmark](docs/fem_reference.md), [independent validation](docs/validation_reference.md).

Historical backend/ML phase numbers describe earlier work. Physics phases 0–7
follow the canonical root plan; these histories have not been renumbered.

## Local setup and release boundaries

Use the existing package dependency/lock files. This checkout was tested with
Python 3.12.7, Node 24.14.1 and npm 11.11.0; the Python environment uses user-site
packages and is not evidence of a clean production installation. A fresh setup
requires the local ML/backend packages and their declared dependencies, PostgreSQL,
and frontend `npm ci --ignore-scripts`. Phase 7 installed no dependencies.

| Setting | Required behavior |
|---|---|
| `DATABASE_URL` | Explicit `postgresql+psycopg` URL to the intended database; never rely on the default when migrating. Keep credentials out of source/logs. |
| `PHYSICS_ENABLED` | Defaults false. It gates processing/availability, not route registration. True alone cannot create an eligible result. |
| `MQTT_ENABLED` | False for isolated validation; prevent traffic from retained sources. |
| `ML_BACKEND` | `stub` for empty-resource verification only; this does not verify fitted analytics. Operational Python mode requires actual compatible artifacts/configuration. |
| `SCHEMA_VERSION` | `1.1.0` in the release verifier; distinct from physics contract `1.0.0`. |
| `WEB_CONCURRENCY` | One worker for the existing stateful Python integration; verifier uses one. |
| `DEMO_RESET_ENABLED` | Keep false. Reset is not physics recovery and has existing FK failures. |
| `CORS_ORIGINS` | Exact frontend origin(s), as a comma-separated or JSON list. Default historical port 8501 does not authorize the React origin. |
| `VITE_API_BASE_URL` | Backend origin without `/api/v1`; default `http://127.0.0.1:8001`. Build-time setting for production. |
| `OPERATIONAL_FLEET_FILE`, `ANALYTICS_POLICY_FILE` | Optional sourced files. Unset when unused; an empty fleet path is interpreted as a directory. Never substitute fleet demo ratings for physics evidence. |
| `TEST_DATABASE_URL` | Administrative test connection allowing CREATE/DROP of new disposable databases. The fixtures/verifier never migrate its retained database. |

For an explicitly provisioned disposable database, from `backend/`, after setting
`DATABASE_URL` and the settings above in a dedicated shell:

```powershell
$env:PHYSICS_ENABLED = 'false'
$env:MQTT_ENABLED = 'false'
$env:ML_BACKEND = 'stub'
$env:DEMO_RESET_ENABLED = 'false'
$env:SCHEMA_VERSION = '1.1.0'
$env:CORS_ORIGINS = 'http://127.0.0.1:5177'
../.venv/Scripts/python.exe -m alembic upgrade head
../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 1
```

Choose unused ports; do not stop an unrelated listener. Migration 0005 adds four
empty physics tables and readiness requires migration heads to match. Retained
data migration, backups, image rollout and profile publication need a separate
operator-approved procedure; none was performed in Phase 7. The Docker backend
entrypoint automatically runs migrations, so restarting/recreating that deployment
is not a harmless route-only check. Its application code is copied into the image:
restarting an old image cannot add a missing source module.

In a separate shell, from `frontend/`:

```powershell
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8002'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5177 --strictPort
```

Check `/health/ready` and `/openapi.json`. Register an empty test identity through
the existing POST `/api/v1/transformers` with only `id` and `name`; do not populate
nameplates/sensors from guesses. Open the card and Thermal & loading: HTTP 200
with ten unavailable values is the expected disabled response. With no eligible
event/profile the values also stay unavailable. Unknown identity returns 404.
No successful operational temperature can be demonstrated with this checkout's
available evidence.

The existing `VITE_API_BASE_URL=/` development proxy forwards `/api` to port 8001,
not 8002. Production has no Vite proxy: configure a real API origin plus CORS, or
an actual same-origin reverse proxy. Frontend API-origin changes require rebuilding
the production bundle. The retained port-8001 backend still uses an older image
without physics; the separate source verifier proves the route locally.

## Reproducible verification

From the root, in the configured existing environment:

```powershell
.venv/Scripts/python.exe tests/fixtures/physics/validate.py
.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py
.venv/Scripts/python.exe -m ml.fem
.venv/Scripts/python.exe -m ml.validation
.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short
.venv/Scripts/python.exe -m pytest ml/tests -q --tb=line -r f
# Set TEST_DATABASE_URL through your approved test environment first:
.venv/Scripts/python.exe backend/scripts/verify_physics_release.py
git diff --check
```

The last script creates a unique disposable PostgreSQL database, migrates only
that database, starts its own loopback backend, checks disabled/no-profile modes,
and stops its process/drops its database. It creates two identity-only assets;
no telemetry or profile is installed. To add actual browser checks, supply
`--browser-module <existing-playwright-module-path>` and
`--browser-executable <existing-chromium-or-edge-executable>` together. It uses
the already installed frontend dependencies and closes its own Vite/browser.
Results, actual JSON and screenshots go to a named temporary directory printed
by the script. Browser prerequisites are verification tools, not runtime dependencies.

From `frontend/`: `npm test -- --reporter=dot`, `npm run lint`, `npm run build`.
From `backend/`: use the process-only pytest namespace/source-path workaround in
[the Phase 7 command record](docs/phase7_report.md); the installed third-party
`tests` package otherwise shadows repository tests. Broad backend/ML suites
remain failing. Real broker tests are skipped without dedicated test-broker
settings, and simulator collection is blocked by missing pymodbus. Do not use
a demo ML mode or fabricate fitted files to disguise these failures.
