# Transformer Digital Twin — Operations Console

React/Vite/TypeScript monitoring UI. The application opens directly to the
registry-backed asset overview. Historical marketing/educational components
remain preserved, but the production entry point does not mount or import them.
All monitoring values come from FastAPI. There is no local analytics or sample fallback.

## Run locally

Use the existing lockfile and Node version compatible with Vite 8 (tested Node 22.17).
With dependencies already installed, `npm run dev` from this directory starts Vite.
On a fresh installation use `npm ci --ignore-scripts`. Vite binds to loopback.
`.env.example` documents `VITE_API_BASE_URL`, selected polling and demo staleness.
The direct API default is `http://127.0.0.1:8001`; this origin must allow the
frontend through CORS. Do not include `/api/v1` in that setting.

The existing Docker UI can remain running at 5173. To inspect current source on
Windows PowerShell without rebuilding any container:

```powershell
cd frontend
$env:VITE_API_BASE_URL = '/'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort
```

Open `http://127.0.0.1:5174`. In this same-origin development mode Vite forwards
`/api` to the established backend at `http://127.0.0.1:8001`; it returns actual
responses/errors. The proxy is development-only. Production builds still use
the configured API origin and existing CORS/deployment conventions. Ctrl+C
stops only this development server. No backend, source or database reset is needed.
The ten-transformer change also served the current build from the existing Docker
frontend at 5173 without rebuilding its image. See the
[ten-transformer report](../docs/hackathon_readiness/execution/TEN_TRANSFORMER_FLEET.md)
for the current runtime and verified browser evidence.

## Navigation and request budget

Overview fetches active backend registry pages (50 rows/request), deduplicates IDs,
supports ID/name search and shows five cards/page. The backend supplies the ordered
ten-transformer fleet: Page 1 of 2 / Page 2 of 2, without a frontend ID list.
Historical identities remain available through scope=all and individual APIs.
Removed active identities stop supplying detail data. Status/alarm filters apply to
the visible page; other pages are not silently assessed. Latest card requests
have at most3 concurrent calls, repeat15 seconds after completion and never fetch
portfolio history. Every asset has its own response/error/last-success state.
Selecting an asset stops overview polling and opens the equipment-centred view.

Selected latest polls every2–5 seconds (configured default3); registry refreshes
60 seconds, MQTT diagnostics15 seconds. Active monitoring/thermal tabs request
only the newest300 telemetry/analytics rows in an explicit one-hour event-time
window every15 seconds. Rows are restored to chronological display order; partial
coverage is disclosed. Alarms/maintenance retrieve the most recent30 records
inside a24-hour event-time window using the actual ascending API's offset pages.
No alarm acknowledgement/control is sent. Maintenance-only RUL polls15 seconds;
projection and one-hour energy poll30 seconds. These intervals do not restart
whenever telemetry event time changes. Superseded requests abort/ignore their
results; unmount cancels timers. HTTP requests time out after10 seconds.

## Supported inputs and limitations

| Panel | Existing backend input | Honest limitation |
|---|---|---|
| Asset overview | `/api/v1/transformers`, `/{id}/latest` | Null/error is not healthy; registry values do not establish verification. |
| Equipment / electrical | Latest canonical voltage/current/power, contacts and analytics | A temperature trip or generic anomaly is not a confirmed short circuit. WTI status is not temperature. |
| Oil leak | `oil_level`, gauge contact; telemetry history | No dedicated leak/depletion-rate result exists. A decline does not establish leakage. Units remain source-defined. |
| Pressure / DGA | No canonical source field/resource | Explicitly unavailable. No pressure/gas values or thresholds generated. |
| Thermal | Backend model, residual, component readiness/units and history | Residual is displayed only when readiness and observed/model units agree; no inferred headroom. |
| Overload | Backend `loading_percent`, reason codes and asset nameplate metadata | No browser rating division, overload-duration model or invented capacity. |
| Maintenance | Health/anomaly/recommendation metadata; maintenance records | Unreleased risk/confidence remain unavailable. |
| RUL / energy | Existing `/{id}/rul`, `/rul/projection`, `/energy?window=1h&anchor=latest` | Synthetic scenario labelled; no lifetime claim. Missing loss/efficiency remains null. |
| System health | `/api/v1/ingest/mqtt/status` | Broker connection/PUBACK does not prove a per-snapshot SQL receipt. |

All asset paths above are under `/api/v1/transformers`. Charts use actual bounded
`/{id}/telemetry` and `/analytics` responses. Gaps/nulls/unit mismatches break
lines; missing observations are never zero-filled. No backend SSE/WebSocket
route is supplied, so the UI uses bounded polling.

Source kind, lineage, units, verification, measurement and analytics times,
configuration and bundle identity remain visible. Display times use the browser's
local timezone (the reviewed machine uses IST); ISO source times remain in time
attributes/tooltips and API evidence. Replay event time remains historical.
The10-second staleness threshold is a demo configuration, not a universal limit.
Current simulator event clocks can be historical even while transport updates.

## Verification

```powershell
npm test
npm run build
npm run lint
```

The existing Vitest/jsdom runner now includes console behavior tests. Controlled
fixtures are imported only by tests. Live browser evidence is in `screenshots/`:
`overview.png`, `transformer-detail.png`, `mobile-detail.png`, `api-outage.png`
and `live-verification.json`. See [CONSOLE_REPORT.md](CONSOLE_REPORT.md) for actual
results and intermediate failures. Build success alone is not integration proof.
`node scripts/verify-console.mjs` is the exercised local browser verification;
it uses the already available Playwright-core installation in
`$env:TEMP/h06-browser` and installed Edge. On another machine supply an equivalent
Playwright/browser setup before running it; this helper is not a runtime dependency.
It interrupts browser requests only, leaving services and data untouched.

For current ten-asset browser verification use `node scripts/verify-ten.mjs`.
It reads the authoritative shared roster and the running backend, saves both
five-card pages plus detail under `screenshots/operational-ten/`, and verifies
TX10/TX01 isolation and actual telemetry advancement. The older verify-console
script and screenshots remain historical 93-asset evidence, not current acceptance.

## Physics read integration (Phase 6)

The existing **Thermal & loading** view now includes a Physics results panel
below the observed-oil/backend-model chart. It calls the separate
`GET /api/v1/transformers/{id}/physics` resource through the existing API client,
base URL and ten-second timeout. No historical cutoff is supplied. Selection,
view entry, the existing Refresh button and the error-only Retry physics button
trigger reads; physics has no recurring timer. Other console views retain their
existing requests and displays.

All ten version 1.0.0 components are validated, with independent status, null,
unit and provenance handling. Loading, errors, asset/view changes and refreshes
withhold old values. If the latest telemetry advances past the returned physics
event, numbers are withheld until an explicit refresh. Selected event and server
evaluation times are distinct and displayed in the browser timezone, retaining
UTC ISO attributes. The panel describes a read snapshot, not continuous readiness.

Controlled RC temperatures and rises are **controlled-simulation estimates /
simplified node proxies**. They are not equipment top-oil or winding hot-spot
measurements. Operational thermal, ageing, FEM hot-spot/comparison, real RUL and
failure probability remain unavailable in this physics release. Current-squared
loss displays only an eligible READY component; no values are inferred from fleet
ratings. Existing scenario RUL and empirical analytics are separate, unchanged
resources. Component and identity disclosures show supplied references, coverage,
assumptions and warnings; they do not retrieve evidence bodies.

Deploy the approved Phase 5 backend before expecting this route to exist. Physics
remains disabled by default and requires operator-managed migration/profile
publication and documented input evidence. This frontend neither enables it nor
installs any profile. The currently running older backend returns 404 for this
route; the panel surfaces that error with a retry. Deployment was not changed.
See [integration prerequisites](../docs/physics_integration.md) and
[Phase 6 results](../docs/phase6_report.md).

`npm test -- tests/physics.test.tsx` runs focused contract/state/interaction tests.
`tests/physics-controlled.json` is test-only: generated from the approved Phase 4
synthetic manifest by the unchanged estimator and serialized/validated by the
backend response schema. Other status/zero/measured fixtures are hypothetical
UI cases, not equipment data. Application code never imports them. No standards
compliance, operational accuracy or end-to-end deployment validation is claimed.

## Phase 7 release verification

[Phase 7](../docs/phase7_report.md) confirmed that the retained port-8001 Docker
image contains no physics module/router entry; its 404 persists until a separately
authorized rollout. The current checkout's route is registered even with
PHYSICS_ENABLED=false. An isolated source backend and actual browser passed
disabled/no-profile unavailable responses, retry/error, identity, cancellation,
disclosure and mobile checks. This is not a successful equipment thermal result.

The reproducible [backend verifier](../backend/scripts/verify_physics_release.py)
optionally invokes [verify-physics-release.cjs](scripts/verify-physics-release.cjs)
using supplied existing Playwright/browser paths. It owns a new disposable DB and
temporary processes; it does not modify the retained deployment. For a backend
on 8002 use a direct VITE_API_BASE_URL origin and exact frontend CORS origin;
the existing same-origin dev proxy still targets 8001. Production API configuration
is embedded at build time. See [safe setup](../README.md) and
[model limitations](../docs/model_limitations.md). Release decision: NOT READY.
# Opt-in live synthetic physics demonstration

The Transformer monitoring grid (six existing cards plus ten physics cards) and
the Thermal & loading panel can display the separate live demo API when
`VITE_LIVE_PHYSICS_DEMO_ENABLED=true`. The default is false/unset; normal builds
retain the production physics contract. Set `VITE_API_BASE_URL` explicitly to
the isolated backend origin (no `/api/v1` suffix), with backend CORS matching the
exact frontend origin. The [safe local launcher](../docs/live_physics_simulation_report.md)
sets these variables only for its separately owned Vite process.

While either selected view is active, one shared demo hook polls every 4 s by
default. `VITE_LIVE_PHYSICS_POLL_INTERVAL_MS` accepts 1000–10000 ms; invalid or
unset values use 4000 ms. The launcher sets it from its `--interval` option.
The hook cancels on asset
changes/navigation, rejects older event watermarks and withholds values on
errors or stale events. All ten rows display numeric demo quantities after
initialization, units, readiness, synthetic provenance and model evidence. The
LIVE SIMULATION indicator and event/publication/latest-update times distinguish
this case from equipment readings. FEM uses a shared winding **mean** proxy;
illustrative ageing is not insulation life. No production environment files,
deployed frontend configuration or operational eligibility are changed. The
additional cards reuse the existing responsive grid and card styles, with scoped
rules for wrapping provenance and long titles. See the
[dashboard implementation and verification status](../docs/live_physics_dashboard_report.md)
before treating this placement as verified against a running backend.

For a running local demo, use the single PowerShell command from repository root:

```powershell
./backend/scripts/Start-LivePhysicsDemo.ps1
```

If `TEST_DATABASE_URL` is not supplied securely, this prompts for the local
PostgreSQL port/user/password. It creates and migrates a new disposable database,
starts the backend and producer, and supplies the frontend configuration explicitly.
Open the **printed frontend URL** (normally `http://127.0.0.1:5177`) and select
any of the ten fictional fleet assets (the PowerShell wrapper's defaults).
The Python launcher can use repeated `--asset` options and retains its old
fleet defaults. An already open ordinary frontend keeps its default
disabled flag; no page reload can replace its build/process environment.
Ctrl+C performs owned-resource cleanup. `-VerifyApi` performs browser-free API/
database verification and cleans up automatically. See the
[actual pipeline results and current manual-demo details](../docs/live_physics_data_pipeline_report.md).
For the current known-asset demo session and preferred `ENABLE_PHYSICS_DEMO`
backend flag, see [enablement and numeric API evidence](../docs/physics_demo_enablement_report.md).

The complete opt-in Docker stack is now started with
`./backend/scripts/Start-TenTransformerDemo.ps1` from repository root.
Its frontend build sets `VITE_API_BASE_URL=/`, demo flag `true`, and 5000 ms polling.
The existing API client resolves `/` to the same origin; the profile-only Nginx
configuration proxies `/api/` to `backend:8000`. No browser uses Docker hostnames.
Ordinary Docker builds retain the demo-disabled default. Use the launcher's
printed frontend URL and session-file stop command, not an older frontend tab.
See [full-stack automated verification and manual checklist](../docs/full_stack_ten_transformer_integration_report.md).
