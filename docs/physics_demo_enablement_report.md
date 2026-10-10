# Physics demo enablement and numeric API verification

**DEMO ENABLED — NUMERIC API RESULTS VERIFIED**

Recorded 2026-10-11 local time. The isolated current-source endpoint returned
all ten calculated numeric components for **KA-BLR-KOR-TX01**, with changing
successive events. No browser automation, screenshots, retained deployment
activation, commit, push or remote deployment was performed.

## Exact root cause and source/image trace

The literal is present at `backend/app/services/live_physics_demo.py` in `read()`.
The endpoint is registered by `backend/app/api/v1/live_physics_demo.py`, included
in the v1 router and mounted under `/api/v1` by `app/main.py`.
Its `enabled(settings, session)` guard requires:

1. `settings.physics_enabled` true;
2. `settings.live_physics_demo_enabled` true;
3. explicit `settings.env == "local-demo"`;
4. configured database matching `live_physics_demo_<32 hex>`;
5. that configured database matching the SQLAlchemy session's bound database.

This is a service guard, not a missing route. The checkout contains the literal
and its service file is untracked in the existing working tree; a search limited
to tracked files would omit it. The user's search method is unknown, so that
search limitation is not asserted as its definitive cause.

Read-only inspection of the running retained container located the same guard
at **`/app/app/services/live_physics_demo.py`**. Its service SHA-256 at task entry
was `462bc921b60cc74c10baba343132dcd92a5798834ce9b0a636ed84e93769ac0e`, exactly
matching the checkout's task-entry service. Its effective settings were
**physics false, demo false, environment development**; the relevant environment
variables were all unset. Actual retained request:

```text
GET http://127.0.0.1:8001/api/v1/demo/transformers/KA-BLR-KOR-TX01/physics
404
{"error":{"code":"HTTP_ERROR","message":"Request failed",
 "details":{"message":"Live physics demo is disabled for this environment",...}}}
```

Both routes were present in its OpenAPI. `backend/.env` declared only
`ENV=development` among the relevant settings. Compose does not enable these
demo flags. Local `.env` changes cannot change an existing container's environment
or image. No retained settings were changed here.

A second cause prevented the known ID from producing a successful isolated
result: the old launcher/producer registered only LIVE-DEMO-A/B. Merely enabling
its flag would not generate KA-BLR-KOR-TX01 events. The asset list is now explicit
and passed consistently through registration, producer and verification.

## One typed flag and precedence

The existing boolean field `Settings.live_physics_demo_enabled` is reused; there
is no competing second field. Preferred environment name:
**`ENABLE_PHYSICS_DEMO`**. Backward-compatible alias:
`LIVE_PHYSICS_DEMO_ENABLED`. Pydantic `AliasChoices` and `populate_by_name` preserve
existing typed constructor calls and internal property names.

- Default is **false**, including explicit `local-demo`, production, development,
  empty or missing environment names. No ambiguous environment enables it.
- Accepted booleans: true/false, 1/0, yes/no, on/off, case-insensitive with
  surrounding whitespace stripped. Invalid/empty effective values raise a
  configuration ValidationError naming ENABLE_PHYSICS_DEMO; they do not silently
  become false or true.
- Constructor values override process environment; process environment overrides
  `.env`; then defaults apply. `.env` is relative to the process working directory.
  Within one source the preferred name wins if both aliases are supplied.
  A legacy process variable still overrides a preferred variable from `.env`,
  because source priority takes precedence over alias priority.
- `get_settings()` is process-cached. App creation/startup, session factories,
  and the route dependency use that same provider in normal operation. The route
  now passes its dependency-resolved Settings object explicitly to `read()`;
  the service cannot substitute a separate lookup for a dependency override.
  Tests exercise this previously unsupported injection case.

In the explicit isolated profile, ENABLE_PHYSICS_DEMO=true enables the typed flag
and endpoint **with the other required gates configured**. PHYSICS_ENABLED=true,
ENV=local-demo and the matching disposable DB remain mandatory; the new spelling
does not bypass isolation or production eligibility. The launcher supplies all
of these, removes the inherited legacy alias, and records the effective typed
settings from a subprocess using exactly the backend's environment/working
directory. Changing flags on disk requires a new current-source process.

## Files changed

Relative to this task's 755-file entry hash snapshot:

| File | Change |
| --- | --- |
| `backend/app/core/config.py` | Preferred alias on existing field, strict documented boolean parsing, constructor-name compatibility. |
| `backend/app/api/v1/live_physics_demo.py` | Inject the shared settings dependency and pass it to the service. |
| `backend/app/services/live_physics_demo.py` | Accept that resolved settings object for reads; all isolation/eligibility gates unchanged. |
| `backend/scripts/live_physics_demo.py` | Repeated `--asset` options drive registration, producer and HTTP verification; use preferred flag and record effective typed settings. |
| `backend/scripts/live_physics_producer.py` | Consume the passed asset list; retain historical default assets for direct invocation. |
| `backend/scripts/verify_live_physics_pipeline.py` | Verify requested primary/secondary identities, raw events and HTTP error/stale paths rather than fixed LIVE-DEMO IDs. |
| `backend/scripts/Start-LivePhysicsDemo.ps1` | Defaults to KA-BLR-KOR-TX01/TX02, with an explicit `-Asset` override. |
| `backend/.env.example` | Document disabled physics/demo defaults, preferred name and isolation prerequisites; actual `.env` untouched. |
| `backend/tests/test_physics_demo_config.py` | New default/boolean/invalid/alias/source precedence and cached-instance tests. |
| `backend/tests/test_live_physics_demo.py` | Use settings override in the router; test authoritative injection and known fictional asset numeric output. |
| `frontend/src/hooks/usePhysics.ts` | Diagnostic refers to the requested/registered synthetic asset rather than fixed A/B identities. |
| `frontend/src/components/console/PhysicsFeatureCards.tsx` | Disabled instructions name the one-command PowerShell wrapper and its registered assets. No layout change. |
| `backend/README.md`, `frontend/README.md` | Preferred flag, known-asset startup, precedence and current report link. |
| `docs/live_physics_demo_model.md` | Document preferred alias and roster identity versus independent synthetic thermal parameters. |
| `docs/physics_demo_enablement_report.md` | This report. |
| `docs/evidence/physics_demo_enablement/api-samples.json` | Complete actual successive primary-asset responses. |
| `docs/evidence/physics_demo_enablement/api-verification.json` | Effective configuration, raw/state persistence, second asset, error paths, table counts and cleanup. |
| `docs/evidence/physics_demo_enablement/manual-session.json` | Identity/configuration and actual numeric response from the intentionally running manual session. |
| `docs/evidence/physics_demo_enablement/preservation-audit.json` | Task-entry hash comparison: 14 deliberately modified existing files, zero missing files. |

No numerical model, production response contract, unit registry, database schema
or migration was changed. Existing uncommitted work was preserved.

## Synthetic calculation and limits

The existing [live case definition](live_physics_demo_model.md) is reused.
KA-BLR-KOR-TX01/TX02 are fictional identities from
`simulator/config/operational-fleet.json`. The isolated physics case uses its own
explicit documented **10 A synthetic HV reference**, not the roster's separate
fictional LV ratings or a real transformer nameplate. No extra thermal/material
parameter is inferred from those identifiers.

- Ambient and initial oil/winding nodes 300 K; `Ro=0.35 K/W`, `Rw=0.2 K/W`,
  `Co=80 J/K`, `Cw=40 J/K`.
- `I(t)=10[0.55+0.25 sin(t/20)] A`, elapsed seconds; load fraction `I/10`.
  `P_loss=6+30(I/10)^2 W`; oil heat 6 W, winding heat `P_loss−6 W`.
- Existing estimator advances `Co dTo/dt=Po+(Tw−To)/Rw−(To−Ta)/Ro` and
  `Cw dTw/dt=Pw−(Tw−To)/Rw`, with exact affine advance and previous-event forcing.
  Raw operating events are validated before calculation and atomically persisted
  with results and complete checkpoints in `live_physics_demo_events`.
- Simulated sensor has a 5 s first-order lag:
  `Ts_new=To_previous+(Ts_previous−To_previous)exp(−dt/5)`.
  Absolute K becomes °C by subtracting 273.15; rises/gradients retain K without
  offsets. Sensor provenance is synthetic, never measured equipment telemetry.
- Illustrative factor `F=exp[(Tw−310 K)/(20 K)]`, unit 1;
  illustrative hours use `(F_previous+F_current)dt/(2×3600)`, unit h.
  Neither is standards-based insulation ageing or remaining life.
- Existing independent fictional two-sheet FEM uses 0.5×0.5 m sheets, thickness
  0.02 m, conductivity 2 W/(m K), insulated sides, distributed exchange and
  normalized cosine source. The common target is the area-average winding
  temperature, not a spatial hot spot or real transformer FEM geometry.
  Difference is estimator winding mean minus FEM winding mean in K. Conservation
  explains near-zero differences; nonzero changing error is not manufactured.

Positive event intervals must be at most 30 s; first event initializes, subsequent
supported events populate all ten values. Freshness is 15 s. Missing/invalid/
nonfinite inputs, incompatible units/source identity, unsupported gaps/state or
corruption fail closed. Ambient 300 K/oil heat 6 W are fixed case prerequisites;
no new defaults substitute for missing equipment data. GET remains read-only;
requests do not initialize, simulate, persist or control state.
Production operational thermal/ageing/RUL/failure probability remain unsupported;
no IEEE/IEC compliance, operational accuracy or real-world validation is claimed.

## Actual API results for KA-BLR-KOR-TX01

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/v1/demo/transformers/KA-BLR-KOR-TX01/physics
```

Verification returned HTTP **200**, envelope **READY**, all ten components READY,
finite numeric values, explicit units and SYNTHETIC_SIMULATED provenance. Full
unabridged responses: [api-samples.json](evidence/physics_demo_enablement/api-samples.json).

| Feature | Sequence 3 | Sequence 4 | API unit |
| --- | ---: | ---: | --- |
| Simulated oil sensor | 27.029362983 | 27.321946181 | DEG_C |
| Top-oil/oil node | 27.561806881 | 27.976718326 | DEG_C |
| Winding/node proxy | 28.365238345 | 29.119447783 | DEG_C |
| Oil-node rise | 0.711806881 | 1.126718326 | K |
| Winding-to-oil gradient | 0.803431464 | 1.142729458 | K |
| Total losses | 18.512164271 | 20.268211241 | W |
| Illustrative ageing factor | 0.654268093 | 0.679411966 | 1 |
| Illustrative equivalent hours | 0.001377527 | 0.002116070 | h |
| FEM winding mean reference | 28.365238345 | 29.119447783 | DEG_C |
| Estimator minus FEM | −1.591615728e−12 | −2.557953849e−12 | K |

Run `e87f143097ca400d89e96a68a313734b`; identity KA-BLR-KOR-TX01; demo contract
1.0.0; case LIVE_SYNTHETIC_TWO_LAYER_V1. UTC event timestamps were
`2026-10-10T21:00:25.231345Z` and `2026-10-10T21:00:29.218441Z`.
Publication times `21:00:25.238190Z`/`21:00:29.224376Z`; actual GET evaluation
times `21:00:25.643458Z`/`21:00:29.710032Z`. These UTC events occur on Oct 11
in the user's timezone. Values were checked against the existing Pydantic demo
schema and persisted raw input/checkpoint/result records, not a fixture.

[Verification evidence](evidence/physics_demo_enablement/api-verification.json)
contains the full second-asset response and raw source identity for
KA-BLR-KOR-TX02. It checks distinct source IDs and correctly owned state, enabled
effective settings, OpenAPI routes, exact CORS and Vite API/flag/interval values.
The disabled replacement of only the owned local backend returned real HTTP 404.
Registered asset without an event returned 404; unknown asset 404; unsupported
query 422; deliberately corrupt stored digest 503; stopped producer eventually
returned UNAVAILABLE with ten null values and a stale reason. Those error checks
are separate from the successful numeric responses.

The ordinary endpoint returned its unchanged complete unavailable response for
the isolated asset: no operational eligibility was bypassed. GET row counts did
not change. Final counts were **8 demo event rows**, **0 canonical telemetry,
production physics profile/event/record/checkpoint and ML checkpoint rows**.
The verification DB was dropped and all its owned children stopped.

## One-command startup, isolated configuration and stopping

From `C:\Transformer-DigitalTwin`:

```powershell
./backend/scripts/Start-LivePhysicsDemo.ps1
```

Existing dependencies and local PostgreSQL are prerequisites. If
`TEST_DATABASE_URL` is not supplied securely, the wrapper prompts for local port,
username and password using a secure password prompt. Credentials are not printed
or stored in report/source. The launcher creates a unique disposable DB, migrates
only it through existing 0001–0006, registers the two requested identities and
starts current-source native uvicorn, the separate producer and opt-in Vite.
No new image build is needed for this native source path.

Flags are explicitly supplied to those child processes: ENABLE_PHYSICS_DEMO=true,
PHYSICS_ENABLED=true, ENV=local-demo, MQTT_ENABLED=false, DEMO_RESET_ENABLED=false,
ML_BACKEND=stub and one worker. The configured/new DB matches the binding. Vite
gets the printed backend origin via VITE_API_BASE_URL, demo flag true, and interval
4000 ms by default; CORS is exactly its printed frontend origin. Inherited legacy
demo alias/fleet-policy paths do not override the isolated profile.
Ports 8002/5177 select another free port when occupied; printed URLs are authoritative.
The existing source interval option is 1–10 s and is passed to both producer and hook.

Custom assets (only created in this new DB):

```powershell
./backend/scripts/Start-LivePhysicsDemo.ps1 -Asset @('KA-BLR-KOR-TX01','KA-BLR-KOR-TX02') -Interval 4
# Equivalent Python command, with TEST_DATABASE_URL supplied securely:
.venv/Scripts/python.exe backend/scripts/live_physics_demo.py --asset KA-BLR-KOR-TX01 --asset KA-BLR-KOR-TX02 --interval 4
```

Ctrl+C requests normal owned-resource cleanup. Alternatively use a new absolute
`-StopFile` path and create that file from another terminal. The supervisor stops
only its children and drops only the uniquely named DB. Existing stop files are
rejected at startup.

**Intentionally running for manual inspection:** frontend
`http://127.0.0.1:5177`, backend `http://127.0.0.1:8002`, both KA assets; database
`live_physics_demo_0f7fdec98874464d96f72c87bb4bc35e`, run
`9e9ce59de8da4d559c64579cac3ee34a`, output `%TEMP%/live-physics-demo-ngn8ojfv`.
Started using:

```powershell
./backend/scripts/Start-LivePhysicsDemo.ps1 -StopFile "$env:TEMP/physics-demo-enablement-e87f143.stop"
```

Stop from a second PowerShell terminal:

```powershell
New-Item -ItemType File -Path "$env:TEMP/physics-demo-enablement-e87f143.stop"
```

After cleanup, inspect its output `report.json`. No cleanup of this intentionally
running session is claimed yet. Open the printed frontend, select KA-BLR-KOR-TX01
and Transformer monitoring for manual inspection. The ordinary frontend and
retained port-8001 endpoint remain unchanged and disabled; editing/reloading their
local `.env` is not a supported way to activate this isolated demo.

The running manual session was checked again by HTTP: all ten components were
numeric and passed `LivePhysicsDemoResult` validation at sequences 70 and 71,
events `2026-10-10T21:06:25.882094Z` and `2026-10-10T21:06:29.876386Z`.
Calculated losses changed from 24.517814763280928 W to 25.081704320783647 W.
The actual served Vite hook module declared API base `http://127.0.0.1:8002`,
demo flag `true`, and polling interval `4000.0` ms. Its index and hook module
returned HTTP 200. This verifies served configuration, not browser rendering.
See [manual session evidence](evidence/physics_demo_enablement/manual-session.json).

Manual checklist (not executed here):

1. Open `http://127.0.0.1:5177`, select KA-BLR-KOR-TX01 and Transformer monitoring.
2. Check the original six cards and ten numeric physics cards, units, synthetic
   labels, event/update times and LIVE SIMULATION indicator. Wait several 4 s
   intervals and confirm changing events/readings.
3. Switch to KA-BLR-KOR-TX02; confirm identity and no prior-asset readings during
   loading. Test refresh, navigation away/back, and network-error retry.
4. Use the stop command after inspection. Confirm owned-process/database cleanup
   in its report; ordinary deployment remains demo-disabled.

## Exact focused commands and outcomes

| Command / working directory | Actual result |
| --- | --- |
| Backend combined command below | **98 passed**, 21.04 s, one inherited Starlette/httpx warning; no skips. Includes 21 new configuration cases and dependency/known-asset tests. |
| Root: `.venv/Scripts/python.exe -m pytest ml/tests/test_live_physics_demo.py -q --tb=short` | **39 passed**, 0.78 s, including raw inputs/intervals/state and existing independent FEM verification. |
| Root, local DB access supplied securely: `./backend/scripts/Start-LivePhysicsDemo.ps1 -VerifyApi` | Exit 0, real known-asset numeric/event/persistence/configuration/error-path checks passed; disposable DB dropped and owned children stopped. |
| Frontend: `npm test -- tests/live-physics.test.tsx tests/physics.test.tsx tests/physics-dashboard.test.tsx` | **74 passed**, 3 files, 13.00 s. |
| Root: `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | PASS: 9 unit rules, 18 vectors/inverses, 13 unit rejections, 6 fixtures, 31 result rejections, 3 JSON rejections, 98 links. |
| Root: `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | PASS: 15 JSON files, 10 schemas, 57 examples, 13 arithmetic/eligibility cases, 10 traces, 3 hashes, bounded queries, 17 links. |
| Frontend: `npm run lint` | Exit 0, 16 pre-existing warnings; no new-code warning. |
| Frontend: `npm run build` | Exit 0, TypeScript + Vite; 2011 modules, 1.71 s build. Ordinary production build remains demo-disabled. |
| Backend: focused Ruff check/format commands below | All checks passed; 8 affected Python files formatted. |
| Root: `git diff --check` and task-entry hash review | Passed; prior unrelated/uncommitted work preserved. |

Backend tests from `backend`, TEST_DATABASE_URL supplied securely:

```powershell
../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; sys.path.insert(0,str(pathlib.Path("..").resolve())); ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q","--tb=short","tests/test_physics_demo_config.py","tests/test_live_physics_demo.py","tests/test_physics_integration.py","tests/test_physics_codec.py"]))'
```

This retains the documented source-root/tests-namespace environment workaround.
An initial direct config-only pytest invocation failed during conftest collection
with `ModuleNotFoundError: ml` because the repository root was not on its path.
It is not reported as a passing run; the documented command above executed all
98 cases. Initial Ruff also reported two overlong new strings, which were fixed.
No failing test was suppressed/renamed and no legacy behavior was repaired to
obtain a green result. Broad prior failures were not rerun.

Ruff from `backend`:

```powershell
../.venv/Scripts/python.exe -m ruff check app/core/config.py app/api/v1/live_physics_demo.py app/services/live_physics_demo.py scripts/live_physics_demo.py scripts/live_physics_producer.py scripts/verify_live_physics_pipeline.py tests/test_physics_demo_config.py tests/test_live_physics_demo.py
../.venv/Scripts/python.exe -m ruff format --check app/core/config.py app/api/v1/live_physics_demo.py app/services/live_physics_demo.py scripts/live_physics_demo.py scripts/live_physics_producer.py scripts/verify_live_physics_pipeline.py tests/test_physics_demo_config.py tests/test_live_physics_demo.py
```

## Preservation and limitations

Retained backend entry identity: container
`eb81d6b021faa21a9c9b167b6c9ecf516ebbbcd6cf03c7a9118aec83690da838`, image
`sha256:519d233506fb95c42e6d842ddcb53d4ce6b5f542288f827d2718233f20371557`,
started `2026-10-10T20:40:49.680563039Z`. Only read-only inspection/HTTP requests
were performed there; no rebuild, restart, environment update or migration.
Local administrative access created/dropped only new demo/test databases.
No retained telemetry/profile/simulation writes, reset, data mount or worker
activation occurred. The manual isolated session is the only intentionally
retained resource from this verification.

Frozen production schemas/unit registry, numerical estimators/FEM sources,
operational eligibility, canonical plan, historical reports, deployment files and
unrelated uncommitted work retain their task-entry bytes. No data/model/standard
prerequisite for operational transformer accuracy was filled with a guessed
parameter. This remains a synthetic demonstration. Manual dashboard rendering
is pending by the user's choice; actual numeric API verification is complete.
The final hash review covered 755 existing files: only the 14 intended files in
the table changed, and none were missing; six new files contain tests, this
report, and the four evidence records. Final retained container ID, image and
start time matched task entry, and its demo GET remained disabled (404).
