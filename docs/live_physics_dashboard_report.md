# Live physics cards on Transformer monitoring

Decision: **LIVE PHYSICS CARDS NOT VERIFIED — BLOCKERS LISTED**

Recorded 2026-10-11. The requested dashboard placement is implemented and focused
frontend/model tests pass. Actual current-source backend/browser acceptance is
unfinished because the local PostgreSQL service is unavailable and Docker's Linux
engine is not running. No live dashboard completion is claimed.

This is a follow-up to the canonical physics-first plan and completed reports,
not another phase or replacement plan. Historical Phase 0–7 and live simulation
reports are preserved. No screenshot attachment was accessible in this task;
the existing six cards and their CSS were used as the visual reference.

## Implementation and exact changed files

Changes relative to the 743-file SHA-256 snapshot taken at this task's entry:

| File | Change |
| --- | --- |
| `frontend/src/components/console/MonitoringConsole.tsx` | Append ten physics cards to Transformer monitoring; activate the existing physics hook in monitoring as well as thermal when demo is enabled; Refresh retries that hook. |
| `frontend/src/components/console/TelemetryPanels.tsx` | Allow children and a region label on the existing feature grid; retain all six existing feature definitions/rendering. |
| `frontend/src/components/console/PhysicsFeatureCards.tsx` | New ten-card presentation of typed demo components, per-component status, units, provenance, model details and timestamps. No calculations or fetching. |
| `frontend/src/components/console/console.css` | Scoped wrapping, badge and footer rules; retain existing 3/2/1-column breakpoints. |
| `frontend/src/hooks/usePhysics.ts` | Document both active views; accept bounded opt-in polling interval (1–10 s, default 4 s). Existing cancellation, asset and event-order guards remain. |
| `frontend/scripts/live-physics-vite.cjs` | Pass the isolated launcher's cadence into the existing Vite environment configuration. |
| `backend/scripts/live_physics_demo.py` | Select monitoring browser verification; pass interval to frontend; support disabled-backend verification by restarting only its owned local backend. |
| `frontend/scripts/verify-physics-dashboard.cjs` | New actual-backend browser acceptance procedure for the sixteen-card grid. Written but not executed successfully. |
| `frontend/scripts/verify-live-physics.cjs` | Adjust old thermal helper's no-polling checks to use overview/system, since monitoring now legitimately polls. Not rerun in this task. |
| `frontend/tests/physics-dashboard.test.tsx` | Card values/units/timestamps/provenance, independent readiness, disabled/loading/error/missing/stale cases and retry. |
| `frontend/tests/console.test.tsx` | Expect the monitoring grid to contain sixteen cards. |
| `frontend/tests/live-physics.test.tsx` | Test configured cadence and invalid/out-of-range fallback; clean up stubbed environment. |
| `frontend/README.md` | Document both views, cadence and current verification limitation. |
| `docs/live_physics_dashboard_report.md` | This report. |

The hash comparison before the documentation edits found exactly the twelve
implementation/test files above changed or added, with no deleted baseline
files. The prior uncommitted work was not reset, stashed or overwritten. Frozen
production contracts, schema/unit registries, API implementation, migrations,
estimator and FEM source remain byte-identical to task entry.

## Data path and behavior

`MonitoringConsole` owns one `usePhysics` instance. In opt-in demo mode it calls
the existing API client and strict demo decoder for
`GET /api/v1/demo/transformers/{id}/physics`. `PhysicsFeatureCards` consumes that
state directly. The ordinary production endpoint/schema is unchanged.

The first six cards remain in their original order. The ten appended cards are:
simulated oil sensor temperature (°C), top-oil estimate (°C), winding hot-spot
estimate (°C), oil-node rise (K), winding-to-oil gradient (K), total losses (W),
illustrative ageing factor (1), illustrative equivalent hours (h), FEM reference
temperature (°C), and estimator-minus-FEM difference (K).

Each has its own status, LIVE SIMULATION badge when demo is enabled, explicit
synthetic provenance, event/evaluation/last-successful-update times, asset and
sequence. Sensor provenance is SIMULATED SENSOR, never MEASURED. Explanations
identify the winding mean proxy and illustrative ageing. Expandable details show
the received model, target, reference, case and run identifiers.

Disabled builds show unavailable demo cards without starting a demo request.
Explicit refresh clears numeric values. Loading, transport/decoding errors,
missing results, initialization and stale events withhold values. Component
readiness is independent. Asset switches cancel prior requests and key guards
hide prior-asset values; event watermarks reject older results. Polling stops
outside monitoring/thermal and on unmount. A single Retry physics control is
available on error. No new write endpoint or request-triggered database writes
were introduced.

## Existing synthetic models reused

No simulation engine, physics calculation or synthetic parameter was added or
changed. Full definitions and applicability remain in
[the existing model document](live_physics_demo_model.md); its original
thermal-only polling description is superseded by the UI scope above.

All parameters below are fictional demo definitions, not equipment data:

- Ambient and initial nodes: 300 K. `Ro=0.35 K/W`, `Rw=0.2 K/W`,
  `Co=80 J/K`, `Cw=40 J/K`.
- `I(t)=10[0.55+0.25 sin(t/20)] A`; `t` is elapsed seconds.
  `P=6+30(I/10)^2 W`, `Po=6 W`, `Pw=P−6 W`.
- Unchanged estimator: `Co dTo/dt=Po+(Tw−To)/Rw−(To−Ta)/Ro`;
  `Cw dTw/dt=Pw−(Tw−To)/Rw`. Exact affine time advance with previous-event
  forcing and explicit supported history.
- Simulated sensor: `Ts_new=To_previous+(Ts_previous−To_previous)exp(−dt/5)`.
- Illustrative ageing: `F=exp[(Tw−310 K)/(20 K)]`, unit 1;
  `H_new=H_previous+(F_previous+F_current)dt/(2×3600)`, unit h.
  This is not standards-based ageing or insulation life.
- Independent FEM uses two fictional 0.5×0.5 m sheets, thickness 0.02 m,
  conductivity 2 W/(m K), insulated lateral edges, distributed inter-sheet and
  ambient exchange, and normalized `1+0.15 cos(πx/Lx)cos(πy/Ly)` heat shape.
  Its area-average winding temperature is the common RC/FEM target. It is not a
  real winding geometry or a spatial hot-spot maximum. The earlier manufactured
  rectangle benchmark is not reused as transformer data.
- Difference is RC winding mean minus FEM winding mean in K. Conservation makes
  it near numerical zero; changing nonzero error is not manufactured. Absolute
  K converts to °C by subtracting 273.15; differences receive no offset.

All outputs remain synthetic/simulated. Production ageing, RUL and failure
probabilities remain unavailable. No IEEE/IEC compliance or field accuracy is
claimed. No standards equations were newly introduced.

## Local startup, stop and current environment blocker

Prerequisites: existing repository Python/Node dependencies and an available
local PostgreSQL service with permission to create disposable databases. Supply
`TEST_DATABASE_URL` securely in the shell; no credentials belong in source or
this report. Its original database is not migrated or seeded.

From repository root, once that prerequisite is restored:

```powershell
.venv/Scripts/python.exe backend/scripts/live_physics_demo.py --interval 4 --backend-port 8002 --frontend-port 5177
```

The launcher creates `live_physics_demo_<32 hex>` and applies migrations only
there; starts owned current-source native Python backend, separate producer and
Vite; sets local demo flags, disables MQTT/reset activity, and configures exact
CORS and API origin. No image rebuild is needed for this native source path.
Expected URLs are `http://127.0.0.1:8002` and `http://127.0.0.1:5177`; occupied
ports are skipped and actual selected URLs printed. Navigate to a LIVE-DEMO asset
and **Transformer monitoring**. Stop with Ctrl+C in the launcher's terminal;
normal cleanup stops only its children and drops only its new database.

Frontend process environment is explicit:
`VITE_API_BASE_URL=<printed backend origin>` (no `/api/v1` suffix),
`VITE_LIVE_PHYSICS_DEMO_ENABLED=true`, and
`VITE_LIVE_PHYSICS_POLL_INTERVAL_MS=4000` at the default interval.
These are not retained/deployed environment edits.

The attempted acceptance command was:

```powershell
.venv/Scripts/python.exe backend/scripts/live_physics_demo.py --verify --verification-view monitoring --browser-module 'C:/Users/Sukhleen Singh Virk/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright' --browser-executable 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
```

This invocation did **not** reach backend, producer or frontend startup. The
documented PostgreSQL port `55433` had no listener. Read-only `docker ps --format
'{{.Names}} {{.Ports}}'` failed because named pipe
`//./pipe/dockerDesktopLinuxEngine` was absent. The launcher waited connecting to
PostgreSQL; only its verified Python process IDs 7112 and 11012 were stopped.
Its output directory `live-physics-demo-mxch4do3` contained no service logs or
verification report. The command ended with exit 1 after that stop. No migration,
database creation or service startup was observed; no database cleanup success
is claimed because PostgreSQL could not be queried. No unrelated service was
stopped or started to work around the blocker.

An earlier automatic approval review also reported a workspace spending cap;
after the user's instruction to continue, normal approved tool calls resumed.
No approval bypass was attempted. The remaining blocker is service availability.

## Actual test commands and results

| Working directory / command | Actual result |
| --- | --- |
| `frontend`: `npm test -- tests/physics-dashboard.test.tsx tests/console.test.tsx tests/live-physics.test.tsx tests/physics.test.tsx` | Final run: **80 passed**, 4 files, 7.60 s. Earlier pre-cadence run: 76 passed. |
| Root: `.venv/Scripts/python.exe -m pytest ml/tests/test_live_physics_demo.py -q --tb=short` | **21 passed**, 2.60 s. |
| Root: `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | PASS: 9 unit rules; 18 vectors/inverses; 13 unit rejections; 6 result fixtures; 31 result rejections; 3 JSON rejections; 98 links. |
| Root: `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | PASS: 15 JSON files; 10 schemas; 57 examples; 13 RUL/energy cases; 10 ingestion traces; 3 hashes; bounded queries and 17 links. |
| `frontend`: `npm run build` | Passed after initial card integration: TypeScript and Vite, 2011 modules. Not rerun after the later polling-cadence change; final-source build remains outstanding. |
| Root: `.venv/Scripts/python.exe -m ruff format backend/scripts/live_physics_demo.py` | One file reformatted. |
| Root: `.venv/Scripts/python.exe -m ruff check backend/scripts/live_physics_demo.py` | All checks passed. |
| Root: `git diff --check` | Passed, including the final report/README edits; only a README line-ending notice. A separate check of new files also found no trailing whitespace. |
| Frontend lint | Not run in this task before stopping at the environment blocker. |
| PostgreSQL API/persistence integration tests | Not run: required local PostgreSQL unavailable. |
| Actual dashboard browser verification | Not reached; no passing result. |

No broad legacy suites or Phase 0–7 audit was repeated. Historical baseline
failures were not changed. The completed focused checks have no observed test
failures; unrun checks are not passing evidence.

## Live evidence and outstanding acceptance

There is **no new actual HTTP response sample, pair of changing live events,
or rendered-browser evidence for this dashboard placement**. Historical thermal
panel evidence in `docs/evidence/live_physics/` is not substituted for it.
Component tests use test fixtures only; runtime cards use the API client.

The new browser procedure is intended to verify all sixteen cards, compare all
ten rendered values/statuses/times to two successive real API responses, check
3/2/1 columns with no overflow, exercise details/refresh/retry, asset cancellation,
navigation, malformed/replayed response rejection and expiration after producer
stop. The launcher then disables only its owned backend's demo flag to verify
real disabled-mode 404s. It also checks OpenAPI routes, unchanged production
unavailable values, exact CORS and isolation table counts. These are **pending**,
not executed acceptance results. Fault-injection steps would be distinguished
from genuine success responses in the produced evidence.

Remaining work: restore the local database prerequisite through the user's
normal environment setup; run and, if necessary, correct the focused acceptance
procedure; run PostgreSQL integration tests and final frontend build/lint;
inspect actual desktop/mobile screenshots; record actual successive
responses and cleanup evidence. No operational release or rollout is approved.

No retained backend container, retained database, production feature flag or
deployed frontend configuration was changed by this task. Docker's current state
prevented a final independent container-identity check, so uninterrupted retained
service availability is not asserted. No commit, push, deployment, profile
publication or retained-data migration was performed.
