# Ten-transformer full-stack integration

Recorded 2026-10-11. This extends the approved work and canonical plan; it does
not rename phases or replace earlier reports. No browser or dashboard was opened.

**CODEBASE AND AUTOMATED CHECKS COMPLETE — MANUAL RUNTIME VERIFICATION PENDING**

## Root causes fixed

1. The native physics launcher defaulted to only two assets, and its producer
   generated an independent operating stream. MQTT/Modbus already referenced the
   shared ten-asset fleet, but accepted canonical telemetry did not drive the demo.
2. The production frontend Dockerfile accepted only the API base build argument;
   it could not compile the opt-in demo flag/polling configuration. An old image
   or ordinary frontend build therefore continued to show disabled cards.
3. The standalone writer required its special registry name, incompatible with
   the existing fictional fleet registration. The new explicitly selected
   telemetry adapter verifies the shared fleet's synthetic registry/configuration
   and canonical source metadata instead; standalone writer restrictions remain.
4. A per-asset simulator/producer exception could terminate the multi-asset loop.
   Asset-level failure isolation now keeps other independent streams running.
5. A failed calculation could leave the last valid result visible. The telemetry
   mode reader now compares its persisted source watermark against the latest
   accepted telemetry and withholds older values if the new event failed.

The retained deployment's old configuration/image issue is documented in previous
reports. It was not repaired in place. This work supplies a new isolated local
Compose environment and newly tagged source builds.

## Final fleet and single data flow

The sole identity/configuration manifest remains
`simulator/config/operational-fleet.json`. Its task-entry bytes were preserved.
The simulator and native physics defaults share the validated loader in
`ml/demo_physics/fleet.py`; no competing runtime asset list was introduced.

| Asset | Modbus unit | Deterministic seed |
| --- | --- | --- |
| KA-BLR-KOR-TX01 | 1 | 42 |
| KA-BLR-KOR-TX02 | 2 | 43 |
| KA-BLR-KOR-TX03 | 3 | 44 |
| KA-BLR-KOR-TX04 | 4 | 45 |
| KA-BLR-HSR-TX05 | 5 | 46 |
| KA-BLR-HSR-TX06 | 6 | 47 |
| KA-BLR-HSR-TX07 | 7 | 48 |
| KA-BLR-HSR-TX08 | 8 | 49 |
| KA-BLR-BTM-TX09 | 9 | 50 |
| KA-BLR-BTM-TX10 | 10 | 51 |

```text
Shared fleet → existing Scheduler/SyntheticGenerator (one clock/RNG per asset)
 → atomic, read-only Modbus FC04 snapshot per unit
 → existing SnapshotPoller/register-map decoder
 → existing bridge spool + QoS1 publisher
 → transformer/{transformer_id}/telemetry
 → existing FastAPI MQTT consumer/schema/topic identity validation
 → canonical ingest_record: asset lock, raw SQL row, ML/alerts/receipts
 → opt-in accepted-telemetry demo adapter in the same transaction/savepoint
 → existing DemoRun/PhysicsEstimator/SheetFEM + SQL-restored per-asset state
 → existing live_physics_demo_events ledger, source ID/hash and checkpoint
 → read-only demo GET → existing typed client/usePhysics → existing cards/panel
```

There is no new MQTT publisher, solver, HTTP write route, worker service or
frontend polling loop. The full-stack profile does **not** run the standalone
physics producer. GET never advances numerical state. Existing bridge reconnect,
snapshot consistency checks, QoS1 PUBACK and canonical commit receipts are kept;
PUBACK alone is not SQL acceptance. Exact retries do not advance demo state.
Late canonical observations do not advance it either.

Each asset gets a separate run ID, event sequence, checkpoint, thermal state and
FEM field vector. No common mutable estimator state is shared between assets.
The reference FEM matrices can be reused, while evolving fields remain separate.
An invalid input/solver error rolls back only the demo savepoint, preserving raw
telemetry and other assets. API status is UNAVAILABLE with null components when
the latest accepted source lacks a valid result, or 503 for an invalid checkpoint.
The first supported event is INITIALIZING. A >30 s source gap explicitly starts
a new run/history and resets illustrative hours; old continuity is not fabricated.

## Synthetic equations, inputs and limits

The full definitions and units are in [the existing demo model](live_physics_demo_model.md).
The new `physics-demo-server.json` references the same fleet and selects only a
local correlated signal profile; the ordinary server profile stays unchanged.

- Fleet ratings: fictional 30 kVA, 400 V line-line, 43.30127018922193 A LV.
  The ten IDs do not imply real nameplates.
- Five-second cadence; load `clip(0.55+0.25*sin(2π*t/120+2π*index/10)+n,0.15,1)`.
  Seeded noise per channel uses `ρ=exp(−dt/30)` and
  `n_new=ρ*n_old+sqrt(1−ρ²)*N(0,σ)`, bounded to ±3σ.
  Ambient is `32+6*sin(π*(UTC_hour−6)/12)+n` °C.
- Existing voltage/current/PF/power/contact/oil-level generation remains in its
  original generator. The oil sensor starts at 42 °C and follows the existing
  1200 s lag toward `ambient+25*apparent_power_loading²` °C. It is a simulated
  input, with independent sensor/model assumptions, not the thermal-node truth.
- Adapter: `L=(I1+I2+I3)/(3*fictional_LV_rating)`, `I_demo=10*L A`.
  This is a dimensionless synthetic load mapping to the existing 10 A reference,
  **not a real HV/LV current conversion**. Loss `P=6+30*L² W`, Po=6 W, Pw=30*L² W.
- Existing RC: `Co*dTo/dt=Po+(Tw−To)/Rw−(To−Ta)/Ro`,
  `Cw*dTw/dt=Pw−(Tw−To)/Rw`; Ro=0.35 K/W, Rw=0.2 K/W,
  Co=80 J/K, Cw=40 J/K, initial nodes 300 K. Exact affine advance uses previous
  sample-held heat and ambient. Both demo FEM and RC use that same ambient.
- Existing two-sheet FEM uses 0.5×0.5 m synthetic sheets, conductivity×thickness
  0.04 W/K, distributed coupling/rejection and matching capacities. Compatible
  target remains **area-average winding mean**, not spatial hot-spot maximum.
  The manufactured rectangle benchmark is never presented as equipment data.
  Variable-ambient tests preserve mean agreement within 1e−8 K.
- Existing illustrative factor `exp((Tw−310 K)/(20 K))`, unit 1; trapezoidal
  equivalent hours `(F_previous+F_current)*dt/7200`, unit h. No IEEE/IEC ageing,
  insulation life, equipment FEM accuracy, operational RUL or failure probability
  is claimed. The sensor is labelled SIMULATED SENSOR and every output synthetic.
- Absolute sensor/ambient °C becomes K via +273.15, and absolute model K becomes
  °C via −273.15. Rises/gradients/differences stay K with no offset.
- Adapter requires accepted SIMULATED/origin SIMULATED, declared UTC, SYNTHETIC
  A/DEG_C metadata, matching source hash/map/configuration, finite required values,
  0≤L≤1.5, 250–350 K ambient, 250–400 K sensor, age 0–15 s. No missing value is zero.

All ten numeric features were calculated and retrieved in automated PostgreSQL
and ASGI API tests for every asset. [Complete responses](evidence/ten_transformer/postgres-asgi-results.json)
are explicitly labelled **AUTOMATED_POSTGRES_ASGI_TEST_NOT_RUNNING_COMPOSE**.
These records are test evidence, not responses from a running dashboard stack.
Symmetric initial forcing may produce equal temperatures for different assets;
identity, source IDs, independent run IDs and histories establish isolation.

## Compose services, flags and ports

Use only `docker-compose.physics-demo.yml --profile physics-demo`, launched with
a unique `physicsdemo-<UUID>` project. Do not combine it with retained Compose
files or `docker-compose.operational-existing.yml`.

| Service | Internal address / role | Preferred loopback host port |
| --- | --- | --- |
| db | db:5432; fresh `live_physics_demo_<UUID>` database | 55434 |
| mqtt | mqtt:1883; existing broker config | 51886 |
| backend | backend:8000; current-source FastAPI + MQTT consumer + demo adapter | 8002 |
| frontend | frontend:80; current-source Nginx/Vite build | 5177 |
| modbus-simulator | modbus-simulator:1502; ten read-only units | 1503 |
| modbus-bridge | existing poller/spool/publisher/receipt process | none |

The launcher chooses free local ports and prints authoritative URLs. It does not
kill services occupying a preferred port. DB/broker/server health checks gate
dependent startup. Backend uses its existing readiness health check, one worker
and existing MQTT subscriber lifecycle. Child processes use init and bounded stop
grace periods. No automatic application restart policy is introduced.

Explicit profile settings: `ENV=local-demo`, `PHYSICS_ENABLED=true`,
`ENABLE_PHYSICS_DEMO=true`, `PHYSICS_DEMO_INPUT_MODE=accepted-telemetry`,
`OPERATIONAL_FLEET_FILE=/config/operational-fleet.json`, MQTT_ENABLED=true,
MQTT_HOST=mqtt, MQTT_PORT=1883, MQTT_TOPIC=transformer/+/telemetry, MQTT_QOS=1,
ML_BACKEND=python, ML_PYTHON_ENTRYPOINT=ml.pipeline:analyze,
ML_RUNTIME_MODE=DEMO_UNVERIFIED_CONFIG, WEB_CONCURRENCY=1, SCHEMA_VERSION=1.1.0,
DEMO_RESET_ENABLED=false. Policy/artifact mounts remain read-only.

Frontend build args: VITE_API_BASE_URL=/, VITE_LIVE_PHYSICS_DEMO_ENABLED=true,
VITE_LIVE_PHYSICS_POLL_INTERVAL_MS=5000. The existing client resolves `/` to the
same origin; profile-only Nginx proxies `/api/` to backend:8000. CORS permits exactly
the printed 127.0.0.1 frontend origin. No machine-specific address is added to
production React code. Ordinary builds/settings retain demo-disabled defaults.

Typed setting precedence stays constructor > process environment > working-dir
`.env` > defaults. ENABLE_PHYSICS_DEMO wins over its legacy alias within a source.
The launcher temporarily pins its generated Compose interpolation values, then
restores inherited process variables so old shell overrides cannot target another
DB/tag. Invalid input mode or an enabled telemetry mode without a valid explicit
fleet fails configuration. Container flags are not changed by editing host `.env`.

DB, broker data and bridge spool use **tmpfs** in this disposable profile. No
retained/named volume is mounted or deleted. Stop loses synthetic history; new
start creates a new empty DB. This profile does not promise outage durability
across container destruction/recreation. No restart/replay of old data is hidden.
Backend entrypoint waits for its new DB and applies existing migrations 0001–0006
there only; no new migration or schema change is introduced.

## Exact files changed

Relative to the 761-file task-entry snapshot; previous uncommitted work is retained.

| Existing file | Reason |
| --- | --- |
| backend/app/core/config.py | Typed input mode and explicit fleet validation. |
| backend/app/services/ingestion_service.py | Invoke opted-in demo preparation in canonical ingestion. |
| backend/app/services/live_physics_demo.py | Reuse persistence primitive; variable-ambient checkpoint; source watermark check. |
| backend/.env.example | Document input mode default and isolation. |
| backend/scripts/live_physics_demo.py | Default to shared ten-asset fleet; explicitly select standalone mode. |
| backend/scripts/live_physics_producer.py | Shared ten defaults and per-asset failure isolation. |
| backend/scripts/Start-LivePhysicsDemo.ps1 | Delegate default asset selection to shared manifest. |
| ml/demo_physics/scenario.py | Explicit variable-ambient/source-input mode; keep standalone validation and estimator equations. |
| ml/demo_physics/fem.py | Explicit held ambient forcing with existing 300 K default. |
| simulator/simulator/fleet.py | Share fleet validation, pass optional signal profile. |
| simulator/simulator/generator.py | Opt-in correlated input noise and gradual demo load profile. |
| simulator/simulator/scheduler.py | Pass profile/asset phase into existing generator. |
| simulator/simulator/modbus_server.py | Isolate failing asset register updates. |
| frontend/Dockerfile | Opt-in demo/polling build arguments, false default. |
| frontend/src/components/console/PhysicsFeatureCards.tsx | Accurate sensor description and full-stack setup diagnostic; layout unchanged. |
| frontend/src/hooks/usePhysics.ts | Full-stack setup/same-origin diagnostic; existing polling/identity logic retained. |
| backend/README.md, frontend/README.md | Current ten-asset/full-stack launch documentation. |
| docs/live_physics_demo_model.md | Document source mapping, variable ambient and correlated profile. |

| New file | Reason |
| --- | --- |
| ml/demo_physics/fleet.py | Validated loader of the existing shared manifest. |
| backend/app/services/demo_telemetry.py | Isolated synthetic source adapter/savepoint calculation. |
| simulator/config/physics-demo-server.json | Profile-only scenario referencing the shared fleet. |
| docker-compose.physics-demo.yml | Independent opt-in disposable six-service environment. |
| frontend/docker/physics-demo.conf | Same-origin API proxy and existing SPA navigation. |
| backend/scripts/Start-TenTransformerDemo.ps1 | Unique project/DB/tag, credentials, ports, validation/build/start. |
| backend/scripts/Stop-TenTransformerDemo.ps1 | Guarded stop of owned project; no volume deletion. |
| backend/scripts/check_ten_transformer_integration.py | Reproducible focused checks on an owned ephemeral test DB. |
| backend/scripts/check_physics_demo_image.py | Network-disabled source/import/default-flag image inspection. |
| backend/tests/test_ten_transformer_demo.py | All-ten publisher/map/parser/input/calculation/isolation checks. |
| backend/tests/test_ten_transformer_persistence.py | Real DB ingestion/GET, retries, invalid input, solver failure, gap reset. |
| backend/tests/test_physics_demo_compose.py | Compose/source/host/flag/settings verification. |
| simulator/tests/test_physics_demo_stream.py | Smooth reproducible ten-stream and nine-survivor tests. |
| frontend/tests/ten-transformer-data.test.tsx | All-ten same-origin typed client/identity checks. |
| docs/full_stack_ten_transformer_integration_report.md | This report. |
| docs/evidence/ten_transformer/{focused.xml,focused-run.json,cleanup.json,postgres-asgi-results.json,image-source-check.json,preservation.json} | Actual automated results, explicit test-only responses, cleanup/source/preservation evidence. |

No frozen production schema/unit registry, production numerical estimator/FEM,
ORM model, migration, original Compose/deployment file or historical report changed.

## Test commands and actual outcomes

Commands are from repository root except npm commands, which run in `frontend`.

| Exact command | Final actual result |
| --- | --- |
| `.venv/Scripts/python.exe backend/scripts/check_ten_transformer_integration.py` | **242 passed**, 22.68 s, one inherited Starlette/httpx warning, no skips. The script lists all 16 focused test files; it supplies source/tests paths and creates only a new ephemeral PostgreSQL container/UUID test databases. Owned container cleanup true. |
| `npm test -- tests/ten-transformer-data.test.tsx tests/live-physics.test.tsx tests/physics.test.tsx tests/physics-dashboard.test.tsx tests/console.test.tsx` | **96 passed**, 5 files, 9.56 s; mocked client/component/hook tests, not browser acceptance. |
| `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | PASS: 9 units, 18 vectors/inverses, 13 unit rejections, 6 fixtures, 31 result rejections, 3 JSON rejections, 98 links. |
| `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | PASS: 15 JSON files, 10 schemas, 57 examples, 13 arithmetic/eligibility cases, 10 traces, 3 hashes, bounded queries, 17 links. |
| `npm run lint` | Exit 0; same 16 pre-existing warnings, no new warning. |
| `npm run build` | Exit 0; TypeScript/Vite, 2011 modules, 774 ms. Ordinary build remains demo-disabled. |
| `./backend/scripts/Start-TenTransformerDemo.ps1 -CheckOnly` | Exit 0; Docker Compose validation, no services started. |
| `./backend/scripts/Start-TenTransformerDemo.ps1 -BuildOnly` | Exit 0; all four newly tagged images built, no application services started. Final inspected tag `4054e9ebf69d4838b624fd1830c36bf7`; earlier intermediate tag `995ca44ae66c4e1eb71b7c292cbb4644` also built. |
| `.venv/Scripts/python.exe backend/scripts/check_physics_demo_image.py --tag 4054e9ebf69d4838b624fd1830c36bf7` | Exit 0; seven relevant runtime source hashes match checkout; ten fleet IDs and both physics routes present in generated OpenAPI; both flags false by default; demo ML configuration UNVERIFIED. One-off network-disabled import process, no API/DB/stack start. |
| Focused Ruff commands below | PASS checks/format. |
| PowerShell AST parsing of Start/Stop-TenTransformerDemo.ps1 and Start-LivePhysicsDemo.ps1 | PASS, 3 scripts. |
| `git diff --check` + task-entry preservation review | PASS; no task-entry file missing; only documented source/doc changes. |

Focused lint/format commands:

```powershell
.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend/app/core/config.py backend/app/services/live_physics_demo.py backend/app/services/demo_telemetry.py backend/scripts/check_ten_transformer_integration.py backend/scripts/check_physics_demo_image.py backend/scripts/live_physics_demo.py backend/scripts/live_physics_producer.py backend/tests/test_ten_transformer_demo.py backend/tests/test_ten_transformer_persistence.py backend/tests/test_physics_demo_compose.py ml/demo_physics/fleet.py ml/demo_physics/fem.py ml/demo_physics/scenario.py simulator/tests/test_physics_demo_stream.py
.venv/Scripts/python.exe -m ruff format --check --config backend/pyproject.toml backend/app/core/config.py backend/app/services/live_physics_demo.py backend/app/services/demo_telemetry.py backend/scripts/check_ten_transformer_integration.py backend/scripts/check_physics_demo_image.py backend/scripts/live_physics_demo.py backend/scripts/live_physics_producer.py backend/tests/test_ten_transformer_demo.py backend/tests/test_ten_transformer_persistence.py backend/tests/test_physics_demo_compose.py ml/demo_physics/fleet.py ml/demo_physics/fem.py ml/demo_physics/scenario.py simulator/tests/test_physics_demo_stream.py
```

Intermediate results were not hidden: an early unit/model run passed 56 cases;
mixed backend/simulator collection then failed due to their shared `tests` package
name and missing declared pymodbus dependency. `.venv/Scripts/python.exe -m pip
install pymodbus==3.6.9` installed the already-declared dependency. A subsequent
run passed 93 cases with two loopback fixture setup errors because child Python
resolved a namespace/resource path incorrectly. The new runner supplies the same
explicit source PYTHONPATH to children and separate test namespace paths; final
242 cases execute those loopback tests successfully. Initial new-code Ruff
style/import errors were corrected, not suppressed. No legacy assertion was
changed for a green suite. Earlier broad Phase 7 failures were not rerun or fixed.

## Existing feature routes and remaining limits

| Existing feature | Retained data path / limitation |
| --- | --- |
| Registry/selection/overview | GET /api/v1/transformers, latest per asset; existing active fleet filtering/pagination. |
| Raw telemetry/charts | GET /transformers/{id}/latest and /telemetry; canonical MQTT SQL rows, preserved provenance. |
| Analytics/health/thermal/overload | /latest, /analytics, /health, /trends; existing Python transactional ML, history/warm-up and component readiness. No replacement with static responses. |
| Oil-leak/electrical cards | Existing oil-level/protection contacts and analytics; contacts remain contact evidence, not fabricated diagnoses. |
| Pressure monitoring | Canonical source has no pressure channel. Existing card stays unavailable; no invented field/default. |
| Alerts | /alerts and existing ingestion hooks; depends on genuine contacts/available model outputs. Healthy scenarios need not fabricate alerts. |
| Maintenance | /maintenance and persisted existing ML/hook outputs; unavailable prerequisites remain explicit. |
| Energy | /energy plus fleet's explicit POWER/import/max-gap policy; needs a supported contiguous interval, not a first-row fake total. |
| RUL/projection/forecast/failure probabilities | Existing /rul and /rul/projection and analytics remain gated. This fleet supplies no real degradation model/equipment history; strict fitted artifacts remain missing. No physics ageing index substitutes for RUL. |
| Physics cards/panel | Separate versioned /demo/transformers/{id}/physics, all ten computed in tests; standard /transformers/{id}/physics remains subject to unchanged operational eligibility and no profile was published. |

DEMO_UNVERIFIED_CONFIG keeps existing empirical analytics as explicitly unverified
demo configuration. A successful readiness check means imports/DB/migrations are
ready; it does not validate fitted models or every dashboard feature. Existing
Phase 7 broad ML/backend failures and strict fitted-artifact/standards/equipment
limitations remain documented in [Phase 7](phase7_report.md). Nothing here
establishes operational thermal accuracy or standards compliance. Dependency
ranges in existing Dockerfiles are not lockfiles; future builds may resolve new
versions and require the same focused checks. No runtime full-stack success is
claimed solely from Compose validation, image builds or TestClient results.

## Manual startup and verification checklist (not executed here)

Docker Desktop must be running. From PowerShell in `C:\Transformer-DigitalTwin`:

```powershell
Set-Location C:\Transformer-DigitalTwin
./backend/scripts/Start-TenTransformerDemo.ps1
```

No passwords or manual source edits are required; the launcher generates temporary
local credentials, DB name, project/tag and ports. It prints a session JSON path
containing no password. Its matching `.env` under your temp directory contains
only this disposable stack's credentials; do not share that file or resolved
Compose environment output. Cold image builds require registry/package access.
Only start the new profile; do not restart the retained backend as a shortcut.

Use the **printed** session path and URLs, substituting actual ports below:

```powershell
$session = Get-Content -LiteralPath 'PASTE_PRINTED_SESSION_JSON_PATH' -Raw | ConvertFrom-Json
$api = $session.backend
Invoke-RestMethod "$api/health/ready"
$openapi = Invoke-RestMethod "$api/openapi.json"
$openapi.paths.PSObject.Properties.Name | Select-String 'physics'
$fleet = Get-Content ./simulator/config/operational-fleet.json -Raw | ConvertFrom-Json
foreach ($asset in $fleet.assets) {
    $id = $asset.transformer_id
    $result = Invoke-RestMethod "$api/api/v1/demo/transformers/$id/physics"
    $result | ConvertTo-Json -Depth 12
}
Start-Sleep -Seconds 6
# Repeat the foreach block; verify newer events and changing appropriate values.
Invoke-RestMethod "$api/api/v1/ingest/mqtt/status" | ConvertTo-Json -Depth 8

docker compose --project-name $session.project --env-file $session.env_file `
  -f ./docker-compose.physics-demo.yml --profile physics-demo ps
docker compose --project-name $session.project --env-file $session.env_file `
  -f ./docker-compose.physics-demo.yml --profile physics-demo logs --tail 40 modbus-bridge backend
docker compose --project-name $session.project --env-file $session.env_file `
  -f ./docker-compose.physics-demo.yml --profile physics-demo exec mqtt `
  mosquitto_sub -h mqtt -p 1883 -t 'transformer/+/telemetry' -C 10 -W 20

# Stop ONLY this disposable project, without deleting Docker volumes:
./backend/scripts/Stop-TenTransformerDemo.ps1 -SessionFile 'PASTE_PRINTED_SESSION_JSON_PATH'
```

1. Check six services healthy/running, subscriber connected, bridge receipts
   committed and all ten topic/payload identities correct. Raw timestamps/current/
   ambient/oil channels should advance. Ten messages alone do not prove all ten
   identities: compare observed IDs against the manifest.
2. Check every demo API response after at least two source intervals: correct ID,
   all ten numeric READY features, units/provenance, event/evaluation times and
   increasing sequences/illustrative hours. Initializing/missing data is expected
   during startup; persistent nulls/disabled/errors fail manual acceptance.
3. Open the printed frontend, select each asset (including later registry pages),
   and check the original six cards plus ten physics cards and Thermal & loading
   panel. Verify SIMULATED SENSOR/LIVE SIMULATION labels and times; do not mistake
   missing pressure, strict fitted analytics, operational RUL or standard physics
   for a successful numeric feature.
4. Verify refresh/retry, rapid asset switching/cancellation, navigation stopping
   physics polling, network-error withholding and desktop/mobile wrapping. Compare
   displayed values to the corresponding API response. No rendering test was run
   here because runtime acceptance is assigned to you.
5. Optionally pause/stop only this project's Modbus source to check stale values
   after 15 s, then start a new disposable session for clean continuity. Do not
   use retained services/data for failure tests. Stop with the guarded script;
   ephemeral history is intentionally lost, retained stacks/volumes are untouched.

## Preservation and cleanup

No retained stack start/stop/rebuild, database migration, reset, seeding, profile
publication or configuration activation was performed. Only owned ephemeral test
PostgreSQL containers and UUID test databases were created and cleaned up; existing
tests also launched/cleaned up their own loopback Modbus subprocesses. The
network-disabled image inspection process removed itself. No application Compose
stack was started, and no browser automation/screenshot/manual dashboard check
was performed. New local image tags/build cache remain available; nothing was
pushed, deployed or committed. No Docker volume was deleted. Existing unrelated
containers and the user's native demo were not managed by this task.

The final preservation evidence compares the 761 task-entry files and records
only the documented changes, with zero missing files. Canonical plan, historical
reports, production contracts/units/models, migrations, original deployment files
and the authoritative fleet manifest retain task-entry bytes. Manual full-stack
runtime acceptance and field/standards/model prerequisites remain outstanding.
