# Live physics data pipeline

**LIVE PHYSICS DATA PIPELINE VERIFIED — LOCAL DEMO RUNNING — NOT DEPLOYED.**

Recorded 2026-10-11 local time. The real producer, PostgreSQL ledger, current-source
API, shared frontend client and polling hook returned changing numeric simulation
results. No browser automation or screenshots were used. Manual dashboard
inspection is left to the user as requested.

## Root cause established before editing

1. `PhysicsFeatureCards.tsx` selects `DISABLED` when the frontend's explicit
   `VITE_LIVE_PHYSICS_DEMO_ENABLED` flag is not `true`. `MonitoringConsole.tsx`
   disables demo polling under that same condition. Therefore the reported
   disabled message is a frontend configuration decision, not a temperature
   calculation failure or an API response with ten null values.
2. `frontend/.env.example`, the ordinary frontend Docker build and compose
   configuration do not enable this opt-in flag. `client.ts` defaults to API
   port 8001. The isolated source launcher instead provides its own frontend
   origin, API URL, demo flag and polling interval. Opening an ordinary frontend
   does not start that launcher or its producer.
3. The existing producer only runs when explicitly launched. The previous
   dashboard task was blocked by unavailable Docker/PostgreSQL; it left no
   running isolated demo. These services are now available on local port 55433.
4. Backend eligibility deliberately requires both physics/demo flags, ENV
   `local-demo`, the correctly named disposable database and a matching bound
   connection. Only registered LIVE-DEMO assets receive this stream. Those
   restrictions are preserved.
5. The existing scenario generates inputs internally and the ledger stores
   derived results plus state and a four-field input summary. It does not yet
   persist the complete timestamped raw sensor event requested for this task.
   The existing launcher verification also requires browser automation; a
   separate browser-free mode is needed for the current acceptance request.
6. Actual HTTP verification exposed another diagnostic loss: the backend's
   stable error envelope says `error.message="Request failed"` and puts the
   useful disabled/no-event/unknown-asset reason in `error.details.message`.
   `frontend/src/api/client.ts` previously read only the generic message. The
   demo client now reads exactly three allowlisted public 404 diagnostics, without
   exposing arbitrary exception details or changing ordinary endpoint errors.

The running ordinary Vite frontend at port **5175** was inspected through an HTTP
module request, without opening a browser. Its served environment contained
`VITE_API_BASE_URL="/"`, demo flag **UNSET**, and physics polling interval **UNSET**.
The ordinary Vite proxy targets backend port 8001. That explains the frontend
DISABLED branch precisely; repeatedly refreshing that process cannot set its
missing environment flag.

At this task's entry the retained backend image was already different from the
old image documented in Phase 7. Its OpenAPI currently contains both physics
routes, but its `PHYSICS_ENABLED`, `LIVE_PHYSICS_DEMO_ENABLED`, and `ENV` variables
are unset. No retained restart or rollout was performed here. Earlier Phase 7
findings remain historical; the current missing readings are not attributed to a
still-missing route in that now-changed image.

The implementation uses the existing simulation engine, estimator, demo ledger
and versioned demo API. Operational schemas, thermal/FEM equations, equipment
defaults, production flags and the retained deployment were not changed.

## Exact files changed and fixes

Relative to the 747-file task-entry SHA-256 snapshot:

| File | Purpose |
| --- | --- |
| `ml/demo_physics/scenario.py` | Generate a raw sensor/operating event before calculation, validate it strictly, feed its current/loss inputs to the existing estimator, and retain unique source identity. Same synthetic equations and parameters. |
| `backend/app/services/live_physics_demo.py` | Store raw event inside the existing atomic checkpoint/result ledger; verify raw identity, input/result/sensor/state linkage during restore/read. |
| `backend/scripts/live_physics_producer.py` | Include changing synthetic current in nonsecret producer diagnostics. |
| `backend/scripts/live_physics_demo.py` | Add browser-free `--verify-api`, a controlled stop-file option and bounded PostgreSQL connection timeout; retain existing browser mode without invoking it. |
| `backend/scripts/verify_live_physics_pipeline.py` | New actual HTTP/DB verification procedure, including persisted raw inputs, checkpoint resume, served Vite flags, missing/invalid/stale/disabled states and read-only behavior. |
| `backend/scripts/Start-LivePhysicsDemo.ps1` | One-command opt-in launcher; securely prompt for local DB access if not supplied; forward interval/ports/stop-file/verification options. |
| `frontend/src/api/client.ts` | Preserve three specific public demo 404 reasons from the existing envelope. Other endpoints keep their established error handling. |
| `frontend/src/hooks/usePhysics.ts` | Actionable diagnostics identify disabled backend, missing producer, unknown asset or unavailable route/API origin. Existing polling/cancellation/watermarks remain. |
| `frontend/src/components/console/PhysicsFeatureCards.tsx` | Replace the generic disabled explanation with the exact launcher/frontend/asset instructions. Layout unchanged. |
| `frontend/src/components/console/LivePhysicsDemoPanel.tsx` | Correct a fixed four-second description to the configured cadence. Layout unchanged. |
| `frontend/.env.example` | Document explicit false demo default and interval; does not alter any running/deployed environment. |
| `ml/tests/test_live_physics_demo.py` | Raw input, deterministic stream, lag, irregular time, reset, rejection and actual estimator-input use checks. |
| `backend/tests/test_live_physics_demo.py` | Atomic raw persistence and invalid raw/result linkage rejection on isolated PostgreSQL. |
| `frontend/tests/live-physics.test.tsx` | Actual-envelope diagnostics, detail allowlist, unchanged production errors and cross-asset contract checks. |
| `frontend/tests/live-physics-api.test.tsx` | Explicit opt-in real HTTP client/hook integration test; no fixtures or browser. Skips when its live test URL is absent. |
| `docs/live_physics_demo_model.md` | Document raw-event format, fixed case applicability, deterministic/no-noise choice and both active frontend views. |
| `backend/README.md`, `frontend/README.md` | Single-command startup and browser-free verification instructions. |
| `docs/live_physics_data_pipeline_report.md` | This report. |
| `docs/evidence/live_physics_pipeline/api-samples.json` | Two complete actual API responses from the disposable verification run. |
| `docs/evidence/live_physics_pipeline/api-verification.json` | Raw events/checkpoints, error-path results, exact process configuration, table counts and cleanup evidence. |
| `docs/evidence/live_physics_pipeline/real-hook-samples.json` | Two real changing responses received through the frontend polling hook. |
| `docs/evidence/live_physics_pipeline/manual-session.json` | Running manual-demo identity, stop file and an actual ten-numeric-value response. |

No duplicate engine, new HTTP write/control endpoint, migration, production
schema or unit registry was introduced. Generated `raw_event` is retained in the
existing demo JSONB checkpoint; raw input, result and state are committed together.
The production canonical `telemetry` table is deliberately not used for this
demo, so synthetic sensor data cannot enter retained empirical analytics.

## Synthetic scenario, units and eligibility

Full model definition: [live_physics_demo_model.md](live_physics_demo_model.md).
All parameters are fictional project definitions, not real transformer ratings
or material properties, and no IEEE/IEC compliance is claimed.

- `I(t)=10[0.55+0.25 sin(t/20)] A`, elapsed seconds `t`; balanced RMS line current
  on a declared fictional HV side. Reference `Ir=10 A`; load fraction `I/Ir`.
  Generated current varies smoothly between 3 and 8 A (load 0.3–0.8).
- Ambient and explicit initial oil/winding temperatures: 300 K.
  `P0=6 W`, `Pk=30 W`; `P=6+30(I/10)^2 W`. Oil heat is 6 W;
  winding heat is `P−6 W`. These are explicit synthetic partitions.
- `Ro=0.35 K/W`, `Rw=0.2 K/W`, `Co=80 J/K`, `Cw=40 J/K`.
  The unchanged estimator advances `Co dTo/dt=Po+(Tw−To)/Rw−(To−Ta)/Ro` and
  `Cw dTw/dt=Pw−(Tw−To)/Rw` using exact affine advance and previous-event forcing.
  It receives typed SYNTHETIC quantities and unchanged eligibility evidence.
- Raw simulated oil sensor uses a 5 s first-order response:
  `Ts_new=To_previous+(Ts_previous−To_previous)exp(−dt/5)`. No noise is added;
  this deterministic lagged stream avoids arbitrary independent noise spikes.
  Raw sensor/ambient units are K; API absolute temperatures are DEG_C, displayed
  °C. Temperature differences retain K without absolute-temperature offsets.
- Illustrative factor `F=exp[(Tw−310 K)/(20 K)]`, unit 1;
  `H_new=H_previous+(F_previous+F_current)dt/(2×3600)`, unit h. This fictional
  index and trapezoidal exposure are not standards-based insulation ageing,
  insulation life, RUL or failure probability.
- Existing independent two-sheet FEM uses 0.5×0.5 m fictional sheets, 0.02 m
  thickness, 2 W/(m K) conductivity, insulated lateral edges and distributed
  ambient/inter-sheet exchange. Its normalized source shape is
  `1+0.15 cos(πx/Lx)cos(πy/Ly)`. The common target is area-average winding-sheet
  temperature. The difference is estimator winding mean minus FEM winding mean.
  The manufactured rectangular benchmark is not repurposed as a winding.
  Near-zero difference reflects conserved mean equations, not spatial hot-spot
  or real-world validation; it is not forced to show a changing significant error.

Raw event contract 1.0.0 explicitly retains event ID, run, asset, sequence,
UTC event timestamp, source, provenance, reference, and six value/unit pairs.
Ambient 300 K and oil heat 6 W are fixed applicability conditions for this
particular coherent FEM/RC case. Current bounds are 0–20 A, load 0–2, sensor
250–400 K, winding heat 0–100 W; unit/rating/loss consistency is checked.
The generated scenario remains within its narrower 3–8 A range. No required
input may become zero on missing/null/boolean/nonfinite data.

First event initializes state and legitimately reports INITIALIZING for thermal
nodes. All ten values become numeric after the first positive supported interval.
Events must advance strictly in UTC with `0 < dt <= 30 s`; freshness is 15 s.
Different source fingerprints/run ownership, invalid state or unsupported gaps
fail closed. Starting a new disposable run explicitly initializes fresh state;
old incompatible state is not silently reused. Producer cycles default to 4 s,
configurable 1–10 s; the frontend receives the same interval. GET does not generate
events or advance state. Ordinary production physics remains unavailable for
unsupported operational outputs.

## Exact startup and stop commands

From `C:\Transformer-DigitalTwin`, with existing repository dependencies and a
local PostgreSQL service available:

```powershell
./backend/scripts/Start-LivePhysicsDemo.ps1
```

If `TEST_DATABASE_URL` is not already supplied securely, the wrapper prompts for
local PostgreSQL port (default 55433), username and password. Password is a secure
prompt, not a source constant or log. The launcher uses the `postgres` administrative
database only to create/drop `live_physics_demo_<32 hex>`; the original database
named in the supplied URL is never migrated, seeded or reset.

It applies existing migrations 0001–0006 only to the new database and starts
native current-source uvicorn, a separate producer and current Vite frontend.
No backend image rebuild is required for this native-source instance. Ports
default to 8002/5177 and select another free port if occupied. Exact printed URLs
are authoritative; do not use the ordinary 5175 frontend or its proxy for this demo.

Backend process configuration: `PHYSICS_ENABLED=true`,
`LIVE_PHYSICS_DEMO_ENABLED=true`, `ENV=local-demo`, new `DATABASE_URL`,
`MQTT_ENABLED=false`, `DEMO_RESET_ENABLED=false`, `ML_BACKEND=stub`, one worker,
and `CORS_ORIGINS` equal to the exact printed frontend origin. Optional fleet/
policy environment paths are removed from these owned child processes.

Frontend process configuration: `VITE_API_BASE_URL=<printed API origin>`,
`VITE_LIVE_PHYSICS_DEMO_ENABLED=true`,
`VITE_LIVE_PHYSICS_POLL_INTERVAL_MS=4000` at the default interval. Ordinary defaults
remain false/unset. Flags must agree; enabling the frontend alone cannot enable
the backend or create a simulation event.

Ctrl+C in the launcher's terminal stops its owned processes and drops only the
new DB. Alternatively start with `-StopFile <absolute-path>` and create that file
from another terminal to request the same normal cleanup. An existing stop file
is rejected at startup.

**Intentionally left running for the user's manual test:**

- Frontend: `http://127.0.0.1:5177`
- Backend: `http://127.0.0.1:8002`
- Assets: `LIVE-DEMO-A`, `LIVE-DEMO-B`
- Database: `live_physics_demo_258781fc689649ac96596fbe0aa33e62`
- Run: `b1a6abfe94a5483db1332663ffaebe9b`
- Supervisor output: `%TEMP%/live-physics-demo-b90dd_xi`

This session was started with local DB access supplied securely:

```powershell
./backend/scripts/Start-LivePhysicsDemo.ps1 -StopFile "$env:TEMP/live-physics-pipeline-manual-3909e2.stop"
```

To stop it from a second PowerShell terminal on this machine:

```powershell
New-Item -ItemType File -Path "$env:TEMP/live-physics-pipeline-manual-3909e2.stop"
```

The supervisor checks that file, stops only its children and drops the named demo
database. Read its `report.json` afterward to confirm cleanup. The manual session
has not been stopped because it is intentionally available for the requested test.

## Actual API and persistence evidence

Actual request:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/v1/demo/transformers/LIVE-DEMO-A/physics
```

The disposable browser-free verification run produced these successive responses
([full JSON](evidence/live_physics_pipeline/api-samples.json)):

| Quantity | Sequence 3 | Sequence 4 | API unit |
| --- | ---: | ---: | --- |
| Simulated oil sensor | 27.030365624 | 27.323667476 | DEG_C |
| Oil-node/top-oil estimate | 27.563777075 | 27.979211143 | DEG_C |
| Winding node/hot-spot proxy | 28.368806994 | 29.123785659 | DEG_C |
| Oil-node rise | 0.713777075 | 1.129211143 | K |
| Winding-to-oil gradient | 0.805029919 | 1.144574516 | K |
| Total losses | 18.521226056 | 20.278568920 | W |
| Illustrative ageing factor | 0.654384846 | 0.679559342 | 1 |
| Illustrative equivalent hours | 0.001381192 | 0.002120602 | h |
| FEM winding mean reference | 28.368806994 | 29.123785659 | DEG_C |
| Estimator minus FEM | −1.648459147e−12 | −2.387423592e−12 | K |

Both envelopes and all ten components were READY, with SYNTHETIC_SIMULATED
provenance, asset LIVE-DEMO-A, demo contract 1.0.0 and run
`3909e2e13add4ef39ef50fdd34b88f03`. Event times were
`2026-10-10T20:18:54.136281Z` and `2026-10-10T20:18:58.127269Z` (UTC).
Publication times were `20:18:54.143516Z` and `20:18:58.135246Z`; actual GET
evaluation times were `20:18:54.633886Z` and `20:18:58.197019Z`.
These UTC dates correspond to 2026-10-11 locally.

Persisted raw currents changed from 6.460450463 to 6.898929608 A, load fractions
0.646045046 to 0.689892961, lagged sensor 300.180365624 to 300.473667476 K,
and winding heat 12.521226056 to 14.278568920 W. Raw IDs ended in `/LIVE-DEMO-A/3`
and `/LIVE-DEMO-A/4`. Checkpoint UTC timestamps matched the events; oil/winding
states advanced from 300.713777075/301.518806994 K to
301.129211143/302.273785659 K. Raw input, result, digest and restored checkpoint
were queried from the actual database and checked against those HTTP responses.

[API verification evidence](evidence/live_physics_pipeline/api-verification.json)
also records route presence, exact CORS/Vite configuration, asset B identity,
read-only GETs, no-event/invalid/stale/disabled responses and cleanup. Its final
counts were **8 demo ledger rows** and **0 rows** in canonical telemetry,
production physics profiles/events/records/checkpoints and ML checkpoints.
That verification database was dropped and all its children stopped.

The independent [real frontend-hook samples](evidence/live_physics_pipeline/real-hook-samples.json)
were obtained against the currently running manual demo through the actual shared
client and `usePhysics`, not a fixture or mocked fetch. The test verified two
changing responses with all ten populated fields, then changed to asset B,
disabled the hook on navigation state, checked an unknown asset diagnostic and
confirmed that the ordinary production response still had unavailable values.

At a subsequent manual-session check, HTTP returned **200 READY, sequence 42,
ten numeric components**, event `2026-10-10T20:25:01.053820Z`; both producer asset
logs continued advancing. This is preserved in
[manual session evidence](evidence/live_physics_pipeline/manual-session.json).
It is a sampled event, not a promise that sequence 42 remains the latest.

## Disabled, invalid and state behavior

- Ordinary frontend flag false/unset: DISABLED cards, no demo polling; specific
  text directs the user to the isolated launcher, printed frontend and demo asset.
- Frontend enabled/backend disabled: real HTTP 404; the allowlisted detail is
  surfaced as a backend configuration diagnostic with API origin and next steps.
- Registered asset without events: real HTTP 404 explains the missing producer
  event. Unknown asset is a separate 404; values are never borrowed from A/B.
- Missing/invalid/nonfinite raw input: rejected before state advance; no zero
  fallback. Persisted raw corruption/linkage mismatch remains unreadable even
  if a test deliberately recomputes a digest.
- Corrupt result/checkpoint: actual HTTP 503; no fallback. Arbitrary server error
  details remain masked. Stopping the producer made the latest event expire after
  15 s; real HTTP 200 UNAVAILABLE then withheld all ten values with a stale reason.
- Refresh clears numeric data; loading/errors remain unavailable. Polling is
  limited to monitoring/thermal; one hook owns it. Existing independent component
  readiness, cancellation, late-response guards and per-asset event watermarks
  are preserved and tested. Browser last update is the successful response receipt
  time; server evaluation and sensor event timestamps remain separate.

## Exact tests and results

No broad Phase 0–7 suites or visual audit was repeated.

| Command / working directory | Actual final result |
| --- | --- |
| Root: `.venv/Scripts/python.exe -m pytest ml/tests/test_live_physics_demo.py ml/tests/test_physics.py -q --tb=short` | **101 passed**, 4.90 s. Includes the demo numerical/reference and raw-input cases. |
| Backend integration command below | **75 passed**, 21.31 s, one inherited Starlette/httpx deprecation warning; no skips. Only newly created test databases were used. |
| `frontend`: `npm test -- tests/live-physics.test.tsx tests/physics.test.tsx tests/physics-dashboard.test.tsx` | **74 passed**, 3 files, 6.65 s. Earlier run before actual-envelope correction: 72 passed. |
| Root, DB access supplied securely: `./backend/scripts/Start-LivePhysicsDemo.ps1 -VerifyApi` | Exit 0. Real producer/DB/API/configuration/error checks passed; database dropped, owned children stopped. No browser flags were supplied. |
| Root: real-hook command below | Final run: **1 passed**, 11.05 s, using actual changing API events and call-through request counts confirming inactive polling stops. Earlier run: 1 passed, 10.46 s. No canned responses or browser. |
| Root: `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | PASS: 9 unit rules, 18 vectors/inverses, 13 unit rejections, 6 result fixtures, 31 result rejections, 3 JSON rejections, 98 links. |
| Root: `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | PASS: 15 JSON files, 10 schemas, 57 examples, 13 arithmetic/eligibility cases, 10 traces, 3 hashes, bounded queries and 17 links. |
| `frontend`: `npm run lint` | Exit 0; **16 pre-existing warnings**, no new-code warnings. |
| `frontend`: `npm run build` | Exit 0; TypeScript and Vite, 2011 modules; final build 690 ms. Ordinary build remains demo-disabled by default. |
| Backend: focused Ruff command below | All checks passed using repository backend configuration. Formatting applied only to affected Python files. |
| Root: `git diff --check` and changed-file/hash review | Passed; no deleted entry files; final preservation details below. |

Backend command (local `TEST_DATABASE_URL` supplied securely), from `backend`:

```powershell
../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; sys.path.insert(0,str(pathlib.Path("..").resolve())); ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q","--tb=short","tests/test_live_physics_demo.py","tests/test_physics_integration.py","tests/test_physics_codec.py"]))'
```

This retains the documented workaround for an installed package shadowing the
repository's `tests` namespace; it does not modify legacy tests or dependencies.

Real-hook command from root, while the isolated demo was running:

```powershell
$env:LIVE_PHYSICS_TEST_BASE_URL='http://127.0.0.1:8002'
$env:LIVE_PHYSICS_TEST_EVIDENCE='C:/Transformer-DigitalTwin/docs/evidence/live_physics_pipeline/real-hook-samples.json'
npm --prefix frontend test -- tests/live-physics-api.test.tsx
```

Focused Ruff command from `backend`:

```powershell
../.venv/Scripts/python.exe -m ruff check scripts/live_physics_demo.py scripts/verify_live_physics_pipeline.py scripts/live_physics_producer.py app/services/live_physics_demo.py tests/test_live_physics_demo.py ../ml/demo_physics/scenario.py ../ml/tests/test_live_physics_demo.py
```

Initial formatting checks exposed unsorted imports and long new verification
strings; these were corrected, not suppressed. A root-directory Ruff invocation
also selected extra comprehension-style rules on existing ML dict constructors;
the final focused command uses the repository's backend configuration, as in the
prior demo work. The first real HTTP run exposed the diagnostic-envelope issue
described above; synthetic test envelopes were then corrected to match the real
shape and the final frontend tests/build rerun. No failing test was renamed or
reported as passing. The documented broad legacy failures remain untouched.

## Preservation and release boundary

Retained backend entry and final identity remained:
`2be54d9fde4c086316020d6545221d202b7f366737baec378bf1a91d6e18bbf3`, image
`sha256:a3aa2e182f00b6a847a011daeef8b07e3360c35bf74cb67b9c811d8a2f0daf86`,
started `2026-10-10T19:59:02.370045828Z`. Its physics/demo/env variables remain
unset. No Docker build/restart/write command was issued. Other services were
not stopped or modified. Local DB administration created/dropped only uniquely
named demo/test databases; retained databases were not migrated, reset or seeded.

The final comparison checked all 747 entry files: exactly 23 files/evidence
changed or were added, with no deletions. Twenty explicitly checked canonical/
production contract and numerical files retain their hashes. Report/model local
documentation links and the final diff whitespace check pass.
The task-entry hashes preserve all unrelated uncommitted files, all prior reports,
the canonical plan, frozen schemas/unit rules, operational eligibility, production
estimator and FEM sources. Only the listed files/evidence changed; no entry file
was deleted. The six original cards, grid layout and existing empirical analytics
were not modified. In the fresh demo DB their existing readings can remain
unavailable because canonical telemetry is intentionally not fabricated.
No deployment, image push, commit, profile publication or production activation
was performed. Operational transformer parameters, source documentation,
standards applicability, model calibration and independent field validation
remain blockers for operational physics; this live demonstrator does not resolve
them.

## Manual dashboard checklist — not executed by Codex

1. Open **http://127.0.0.1:5177**, select **LIVE-DEMO-A**, then Transformer monitoring.
2. Confirm ten numeric physics cards alongside the original six, with LIVE
   SIMULATION/SYNTHETIC labels; oil channel says SIMULATED SENSOR.
3. Observe at least two four-second intervals. Check units, statuses, event and
   evaluation/update times; the common-mean difference should stay near zero.
4. Refresh and switch to LIVE-DEMO-B; confirm prior-asset numbers do not persist.
   Navigate away and back. Check retry/loading behavior if you temporarily
   disconnect this local API, without altering retained services.
5. Use the stop-file command when finished; confirm its cleanup report. The
   original ordinary frontend remains demo-disabled. To rerun, start a new
   disposable session with the one-command launcher.

There is no remaining code/API blocker observed in the focused checks. Manual
rendered-dashboard verification is pending by explicit user choice.
