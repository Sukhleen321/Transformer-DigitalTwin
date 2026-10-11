# Transformer Digital Twin

**A telemetry-to-monitoring platform for transformer assets.** The repository brings together a React operations console, a FastAPI and PostgreSQL backend, an ML runtime, and a Python simulator that can generate, replay, and deliver telemetry over Modbus and MQTT.


## What the system does

- Accepts telemetry through HTTP, historical replay, or an MQTT stream bridged from a Modbus simulator.
- Validates and normalizes incoming records, preserving missing values and source context instead of filling gaps with invented measurements.
- Persists observations and derived analytics in PostgreSQL; the existing ML runtime provides empirical analytics such as anomaly, health, and maintenance outputs, subject to the availability of compatible configuration and artifacts.
- Serves bounded, versioned read APIs for transformer status, history, trends, alerts, maintenance, and optional physics results.
- Displays asset status, telemetry, charts, alarms, maintenance, and physics-component availability in a React monitoring console.
- Keeps physics estimates, their evidence, units, provenance, and availability status explicit. Unsupported values remain unavailable.

## Architecture

The primary path carries simulator or external telemetry into the shared ingestion service. HTTP and replay use that same service, as does MQTT. The simulator's Modbus bridge retains uncommitted messages in a spool and checks the backend receipt resource before removing them.

## Architecture

The primary path carries simulator or external telemetry into the shared ingestion service. HTTP and replay use that same service, as does MQTT. The simulator's Modbus bridge retains uncommitted messages in a spool and checks the backend receipt resource before removing them.

```text
TELEMETRY SOURCES
=================

 Python Simulator
 (generation/replay)
        |
        v
 Modbus Server
 (FC04 register map)
        |
        v
 Modbus Bridge
 (durable message spool)
        |
        v
 Mosquitto MQTT Broker ----------------------+
                                              |
 HTTP Telemetry and Batch API ---------------+----> SHARED INGESTION
                                              |     FastAPI: validation,
 Historical Replay API ----------------------+     normalization, idempotency
                                                    |
                         +--------------------------+------------------+
                         |                                             |
                         v                                             v
                  ML Adapter and                              PostgreSQL
              Transactional Pipeline                          Database
                         |                                             |
                         +---------------------> PostgreSQL <---------+
                                                       |
                                                       v
                                               Versioned REST
                                                  Read APIs
                                                       |
                                                       v
                                         React + TypeScript Console

Reliability acknowledgement:
PostgreSQL committed receipt - - - - - - - -> Modbus Bridge
(The bridge removes a spooled message only after confirming backend receipt.)
```

### Physics result path

Physics is an optional extension of ingestion and persistence. Its read resource is separate from the regular analytics endpoints. It reports component-level units, status, coverage, provenance, assumptions, and reasons; a missing or unsupported result is represented as unavailable rather than a fabricated temperature.

### Physics result path

Physics is an optional extension of ingestion and persistence. Its read resource is separate from the regular analytics endpoints. It reports component-level units, status, coverage, provenance, assumptions, and reasons; a missing or unsupported result is represented as unavailable rather than a fabricated temperature.

```text
ACCEPTED TELEMETRY EVENT
          |
          v
  Physics processing enabled
  and inputs/config eligible?
          |
      +---+---+
      |       |
     NO      YES
      |       |
      v       v
 Typed      Physics estimator
 unavailable (controlled simulation
 components   only)
 with reasons       |
 and provenance     v
      |       Versioned component results
      |       (values OR explicit unavailable states)
      |               |
      +-------+-------+
              |
              v
     Shared database transaction
              |
              v
  Physics events + asset-owned checkpoints
              |
              v
       Physics Read API
 (GET transformer physics endpoint)
              |
              v
   Thermal and loading console view
```


## Components

| Area | Implementation | Role |
|---|---|---|
| **Frontend** | React 19, TypeScript, Vite | Monitoring console with asset selection, bounded polling, telemetry and trend views, alerts, maintenance, and physics status. |
| **Backend** | FastAPI, Pydantic, synchronous SQLAlchemy, psycopg, PostgreSQL | HTTP API, input validation, shared ingestion, persistence, read queries, MQTT consumer, and transactional ML integration. |
| **ML runtime** | NumPy, pandas, SciPy, scikit-learn | Existing empirical analytics and stateful pipeline; separate controlled-simulation physics estimator; independent FEM and validation packages. |
| **Simulator** | Python, pymodbus, Paho MQTT | Synthetic telemetry, scenarios, replay, Modbus server and bridge, streaming, and durable message spool. |
| **Local stack** | Docker Compose | PostgreSQL, Mosquitto, backend, frontend, and opt-in simulator services. |

### Monitoring console

This captured overview shows the console layout with synthetic demo telemetry. It is a UI example, not live equipment data.

![Transformer Digital Twin monitoring console overview with synthetic demo telemetry](frontend/screenshots/overview.png)

### Main data flow

1. The simulator can generate synthetic observations or replay available records. Its Modbus server exposes a declared register map; the bridge reads registers, translates them into telemetry, and publishes to MQTT.
2. The backend accepts MQTT, HTTP, batch, and replay input through the same ingestion service. It validates contracts and event identity, records the observation, and invokes the configured ML adapter.
3. Telemetry and eligible analytics are persisted in PostgreSQL. Stateful Python ML uses asset-owned checkpoints and participates in the database transaction. MQTT receipts let the bridge confirm backend commit before acknowledging/removing a spooled message.
4. The read APIs expose bounded asset state, history, trends, alerts, maintenance, and physics resources. The frontend requests these resources and presents their values, errors, and missing-data states.

## Repository map

```text
backend/       FastAPI app, API routes, services, repositories, schemas, migrations
frontend/      React console, API contracts, hooks, components, styles, UI tests
ml/            Analytics pipeline, physics estimator, FEM benchmark, validation
simulator/     Telemetry generation, replay, Modbus/MQTT, spool, scenarios, runbooks
docs/          Architecture, contracts, model limits, integration and release evidence
tests/         Shared fixtures and validation tools
docker-compose*.yml
```

Useful entry points and references:

- Backend application: [`backend/app/main.py`](backend/app/main.py); setup and API details: [`backend/README.md`](backend/README.md).
- Frontend entry: [`frontend/src/main.tsx`](frontend/src/main.tsx); setup: [`frontend/README.md`](frontend/README.md).
- ML pipeline: [`ml/pipeline/orchestrator.py`](ml/pipeline/orchestrator.py); physics estimator: [`ml/physics/estimator.py`](ml/physics/estimator.py); synthetic FEM benchmark: [`ml/fem/`](ml/fem/).
- Simulator CLI: [`simulator/simulator/cli.py`](simulator/simulator/cli.py); operating instructions: [`simulator/simulator_README.md`](simulator/simulator_README.md).
- Current code and release boundaries: [architecture baseline](docs/architecture_current.md), [physics contract](docs/physics_contract.md), [model limitations](docs/model_limitations.md), [Phase 7 report](docs/phase7_report.md).

## Contracts and model boundaries

- **Telemetry and analytics:** values may be nullable; absent data stays absent. Event identity, timestamps, schema versions, and source context are explicit.
- **Physics contract:** version `1.0.0`; the ten physics components have independent units, statuses, provenance, and nullable values. The contract can describe future capabilities that this release does not provide.
- **Database schema:** backend schema version `1.1.0` is separate from the physics contract version. Migrations are required for the API readiness check.
- **Operational readiness:** setting `PHYSICS_ENABLED=true` only enables processing; it does not create valid inputs, publish a supported profile, or make an operational prediction eligible.
- **ML artifacts:** operational Python mode requires compatible artifacts and configuration. A stub is useful only for checking empty/unavailable-resource behavior and is not fitted analytics.
- **Simulator data:** the configured fleet and scenarios are synthetic. Demo ratings, register values, and traces are not evidence about connected equipment.
- **FEM and validation:** FEM is a synthetic steady-conduction reference. The validation harness checks explicit synthetic cases, not field accuracy or standards compliance.

## Local development

Use the package manifests and lock files already in the repository. The documented release-validation environment used Python 3.12.7, Node 24.14.1, and npm 11.11.0. A fresh setup needs the ML and backend Python packages, PostgreSQL, and the frontend dependencies. The following source-mode example expects an **explicitly provisioned disposable PostgreSQL database**; set its connection string in a dedicated shell and choose ports that are free.

From the repository root, in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ./ml -e ./backend
```

Then, from `backend/`, after setting `DATABASE_URL` to the disposable database:

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

In a second shell, from `frontend/`:

```powershell
npm ci --ignore-scripts
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8002'
npm run dev -- --host 127.0.0.1 --port 5177 --strictPort
```

The frontend API origin is a build-time setting for production. Configure the production API origin and matching CORS allowlist, or provide a same-origin reverse proxy. The default Vite proxy targets port `8001`, so it does not match the source-mode backend command above.

Open `http://127.0.0.1:5177`. Check backend liveness/readiness at `/health` and `/health/ready`, and inspect `/openapi.json` for the active API contract. With physics disabled, the physics endpoint is expected to return unavailable components. This setup does not demonstrate a successful operational temperature prediction.


## Verification

The repository includes fixture validators, focused ML tests, frontend tests, and a backend physics release verifier. These checks do not certify field accuracy or operational readiness.

From the root, in the already configured project environment:

```powershell
.venv/Scripts/python.exe tests/fixtures/physics/validate.py
.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py
.venv/Scripts/python.exe -m ml.fem
.venv/Scripts/python.exe -m ml.validation
.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short
```

The backend release verifier requires a `TEST_DATABASE_URL` for an administrative PostgreSQL connection. It creates and drops a uniquely named disposable database; review [`backend/scripts/verify_physics_release.py`](backend/scripts/verify_physics_release.py) before using it. Frontend checks are `npm test -- --reporter=dot`, `npm run lint`, and `npm run build` from `frontend/`.

See the [Phase 7 report](docs/phase7_report.md) for exact release-validation results and known failures. The broad backend/ML suites remain failing in the documented environment, real broker tests need dedicated broker settings, and simulator test collection requires `pymodbus`. Do not present focused synthetic checks as a passing full-system or production validation.

## Further reading

- [Canonical physics-first implementation plan](Transformer_DigitalTwin_Physics_First_Implementation_Plan.md)
- [Current architecture baseline](docs/architecture_current.md)
- [Physics persistence and read integration](docs/physics_integration.md)
- [Physics contract 1.0.0](docs/physics_contract.md)
- [Physics source locators](docs/physics_references.md)
- [Model limitations](docs/model_limitations.md)
- [Phase 7 release report](docs/phase7_report.md)
- [Backend documentation](backend/README.md) · [Frontend documentation](frontend/README.md) · [Simulator runbooks](simulator/RUNBOOK.md)
