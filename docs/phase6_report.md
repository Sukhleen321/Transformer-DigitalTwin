# Phase 6 report — frontend physics read integration

10 October 2026. Phase 6 only, following the sole
[canonical plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md),
[physics contract](physics_contract.md), [persistence boundary](physics_integration.md)
and approved [Phase 5 report](phase5_report.md). No backend deployment, database
enablement, physics changes, commit, push or Phase 7 work.

Implemented a separate physics read panel in the existing **Thermal & loading**
view, below the observed-oil/backend-model chart and above asset configuration.
Existing navigation, charts, six feature cards, legacy empirical analytics,
scenario RUL and frontend styles remain intact. Controlled thermal values are
explicitly **controlled-simulation estimates / simplified node proxies**.
They are not operational transformer top-oil or winding hot-spot predictions.

## Exact files and contract boundary

Modified frontend files:

- [src/api/client.ts](../frontend/src/api/client.ts): add one read operation using
  existing fetch, base URL, timeout, cancellation, error-envelope and identity checks.
- [MonitoringConsole.tsx](../frontend/src/components/console/MonitoringConsole.tsx):
  mount the panel in the thermal view and connect existing Refresh/asset selection.
- [README.md](../frontend/README.md): describe read behavior and deployment prerequisites.

Added frontend files:

- [src/api/physics.ts](../frontend/src/api/physics.ts): strict Zod response validation.
- [src/hooks/usePhysics.ts](../frontend/src/hooks/usePhysics.ts): one-shot read lifecycle.
- [PhysicsPanel.tsx](../frontend/src/components/console/PhysicsPanel.tsx): existing
  panel/table/badge/disclosure styles, per-component values and explanations.
- [tests/physics.test.tsx](../frontend/tests/physics.test.tsx): 45 focused tests.
- [tests/physics-fixtures.ts](../frontend/tests/physics-fixtures.ts): hypothetical UI
  variants, including status, null and genuine-zero handling.
- [tests/physics-controlled.json](../frontend/tests/physics-controlled.json): unchanged
  estimator output from the approved synthetic manifest, serialized and validated
  by the backend schema. This is not an HTTP capture or equipment data.

Added documentation: this report. No stylesheet, frontend dependency, lockfile,
Vite configuration, old API schema, existing test, backend or numerical source edits.
The exact intended frontend files and UI placement were listed before code edits;
the additional generated JSON test fixture was announced separately.

The new client follows
[the actual endpoint](../backend/app/api/v1/physics.py),
[runtime response schema](../backend/app/schemas/physics.py) and
[frozen JSON schema](contracts/physics-result-v1.schema.json).
It parses version 1.0.0, all ten exact keys, fixed units/kinds, finite/null values,
five statuses, diagnostics, assumptions, coverage, lineage and version identities.
Extra/missing members, bad dates, numeric strings/booleans, nonfinite values,
READY/null contradictions, missing READY evidence and cross-asset responses fail.
It also enforces the current backend release's eligibility restrictions: operational
thermal, ageing, FEM hot-spot and comparison cannot become READY. The structural
schema describes future possibilities; that does not enable them in this release.
No existing telemetry/analytics status or unit is repurposed.

## Placement and interpretation of all components

All entries appear as individual rows in the same bounded, scrollable table.
Each row has its own status, reason messages, fixed unit and expandable evidence,
warnings, missing-input paths, assumptions and coverage. No aggregate READY badge.

| Contract key | UI label / eligible display |
|---|---|
| measured_oil_temperature | Measured oil sensor, °C. Eligible sensor target is determined by supplied evidence, not inferred as top-oil. Synthetic input remains unavailable. |
| top_oil_temperature | Oil node temperature estimate, °C, controlled simulation only. |
| hot_spot_temperature | Winding node temperature estimate, °C, controlled simulation only; no physical hot-spot claim. |
| top_oil_rise | Oil node rise estimate, K, controlled simulation only. |
| winding_hot_spot_gradient | Winding–oil node gradient estimate, K, controlled simulation only. |
| total_loss | Current-squared loss estimate, W, only when independently READY and finite. No browser inference from current/rating/heat inputs. |
| ageing_acceleration_factor | Ageing acceleration factor, unit 1, unavailable in this release. |
| equivalent_ageing_hours | Equivalent ageing hours, h, unavailable in this release; never interpreted as RUL. |
| fem_hot_spot_temperature | FEM hot-spot reference, °C, unavailable. Preserves SIMULATED_REFERENCE kind; the independent rectangle benchmark is not transported as a transformer temperature. |
| hot_spot_difference | Estimator–FEM difference, K, unavailable; no compatible common target established. |

Absolute DEG_C is displayed with the °C glyph; K differences retain K, without
offsets or recalculation. Null stays “Unavailable”; zero is displayed only for a
valid READY component. The test-only zero-loss and measured-only cases are
hypothetical UI eligibility examples, not new equipment parameters or measurements.

The context/provenance strip displays source, origin, input verification, selected
event and server evaluation time. ISO UTC remains in time attributes/tooltips;
display uses browser local time. Version/model/equation/case/source references are
available in disclosures. No evidence bodies or additional endpoints are fetched.
Thermal forcing values are not in this result envelope: the UI shows supplied
input references and preserves existing telemetry displays rather than inferring
an ambient value or heat partition for the returned physics event.

## Request and control behavior

GET `/api/v1/transformers/{id}/physics` uses the existing API base URL and Accept
header, public-read conventions, server request-correlation/error conventions and
ten-second timeout. It supplies no `at` cutoff or invented query capability. Thus
the backend's normal event selection and freshness gates apply; historical samples
are not made eligible by a browser-selected cutoff.

There is one read on thermal-view entry, asset selection, existing Refresh, or
error-only Retry physics. No physics polling or simulation trigger. Other views
do not request physics. Requests cancel on asset/view changes and unmount; late
responses cannot replace the selected asset. Refresh changes the request key and
immediately withholds prior values. Loading, network failure, malformed response,
404/409/422/500, missing result and unavailable components never fall back to an
older READY result. Disabled integration and absent configuration retain backend
reasons rather than synthetic defaults.

The panel explicitly describes a read snapshot. If existing telemetry polling
advances beyond the physics event, all displayed numbers are withheld with
“Refresh required”; an explicit refresh is needed. This does not infer a physical
staleness threshold. Backend component freshness remains authoritative.

Tests exercised global Refresh, Retry physics, asset switch and late-response
suppression, thermal/system/overview navigation, chart channel selection, all ten
component disclosure open/close actions and identity disclosure. Existing 50 tests
remain passing, including registry pagination/search/removal, equipment selection,
history gaps, polling cancellation/timeouts and legacy resource controls.
Live read-only browser checks additionally exercised monitoring/thermal/alarms/
maintenance/system/overview, Refresh/Retry and mobile navigation. These checks are
not exhaustive release acceptance of every legacy feature.

## Exact commands and actual results

Environment: existing Node v24.14.1 / npm 11.11.0, installed Vite 8.3.3,
TypeScript/Vitest/Zod, existing Python virtualenv with user-site backend dependencies,
and existing PostgreSQL test access. No dependency install or configuration repair.

Frontend commands, from `frontend/`:

| Command | Actual outcome |
|---|---|
| `npm test` before edits | 6 files, 50 passed; 37.74 s. |
| `npm run lint` before edits | Exit 0; 16 existing warnings. |
| `npm run build` before edits | Exit 0; tsc/Vite pass, 2005 modules, 2.02 s Vite build; JS 372.88 kB. |
| `npm test -- tests/physics.test.tsx` | 1 file, 45 passed; 3.89 s. |
| `npm test -- --reporter=dot` | Final run: 7 files, 95 passed; 15.71 s. |
| `npm run lint` after changes | Exit 0; same 16 warnings, no new warnings/errors. |
| `npm run build` after changes | Final run exit 0; tsc/Vite pass, 2008 modules, 1.15 s Vite build; JS 383.56 kB, gzip 115.57 kB. |

Root commands:

```powershell
& .venv/Scripts/python.exe tests/fixtures/physics/validate.py
& .venv/Scripts/python.exe tests/fixtures/hackathon/validate.py
```

Both exit 0. Physics: 9 unit rules; 18 exact conversion vectors/inverses;
13 unit rejection cases; 6 result fixtures; 31 result rejection cases;
3 JSON rejection cases; 98 local links. Existing contract: 15 JSON files,
10 schemas, 57 examples, 13 arithmetic/eligibility cases, 10 ingestion traces,
3 semantic hashes, bounded event-time checks and 17 links. These are contract
checks, not standards or field validation.

Backend command, from `backend/`, using the existing documented local test URL:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://transformer:transformer@127.0.0.1:55433/transformer'
& ../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; sys.path.insert(0,str(pathlib.Path("..").resolve())); ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q","--tb=short","tests/test_physics_codec.py","tests/test_physics_integration.py"]))'
```

Exit 0: **57 passed, 1 pre-existing Starlette/httpx deprecation warning, 16.68 s**.
The process-only namespace setup avoids the already documented installed `tests`
package collision. PostgreSQL fixtures create/migrate/drop disposable test databases;
no migration or profile publication was applied to a retained database.

No new test failure occurred. Broader backend and ML suites were not rerun for
this frontend-only change. Their approved unresolved baseline remains: Phase 5's
broader API selection had 4 failures; Phase 0's full backend diagnostic had
15 failures/735 passes/1 skip; the last full ML run had 95 failures caused by
missing fitted artifacts and consequential BundleNotReadyError. None was hidden,
repaired or relabelled as passing. See the prior reports for exact cases.

## Browser and visual evidence

Unified browser tooling failed to initialize (Windows sandbox helper error).
Bundled Playwright with installed Chrome launched but screenshot capture timed out.
Installed Edge with screenshot-surface/GPU flags successfully rendered/captured
the UI. Therefore browser verification **was** completed through that fallback.

Temporary browser commands from the root:

```powershell
node "$env:TEMP\transformer-phase6-browser.cjs" before
node "$env:TEMP\transformer-phase6-browser.cjs" after
node "$env:TEMP\transformer-phase6-browser-interactions.cjs"
```

These task-local helpers/output live in TEMP, not production or tracked sources.
The first helper uses browser-only request interception with existing legacy test
fixtures and the generated controlled fixture. The reconstructed pre-Phase-6 view
uses the original two frontend modules from HEAD through a temporary Vite load
plugin; their CRLF checkout hashes match the Phase 6 entry audit. It does not
overwrite workspace modules or change the running backend. The temporary baseline
server on 5176 was closed. The after view uses the current source on 5174.

Pixel comparison with identical fixed-clock fixtures found **zero differing pixels**
for overview (1440×1000) and transformer monitoring (1440×2168). Desktop thermal
and settled 390×844 mobile views were inspected, including the new panel; no document
horizontal overflow. Existing stylesheet files are byte-identical. The thermal
page gains only the disclosed panel's height. All ten rows remain accessible in
the existing bounded table scroll area. No fabricated chart was introduced.

The initial live check on the existing development URL could not load its expected
registry card. A separate temporary Vite process used the documented same-origin
`VITE_API_BASE_URL=/` proxy on free port 5177. Port 5175 was occupied and was left
alone. This process read the real existing backend and then closed. Four physics
reads (entry, Refresh, Retry, mobile re-entry) returned **404**; the UI showed the
sanitized error, no table/numbers, and functional retry. All checked navigation
worked, there were zero browser page errors and no mobile horizontal overflow.
This is a real error-path integration check, not a live successful physics result.

Screenshots and `actual-api-check.json` are under
`$env:TEMP/transformer-phase6-visual/`: before/after overview, monitoring, thermal,
mobile, plus `actual-api-404.png`. They are local test evidence, not committed
release artifacts. Intermediate screenshots captured a sidebar transition; the
final mobile capture waits for the existing animation to settle. Failed helper
processes created by this task were closed; existing browsers/services were kept.

## Assumptions, remaining prerequisites and exit criteria

The available real running backend does not yet expose the newly approved route
(registry 200, physics 404). Deploy/restart the approved Phase 5 backend before
expecting the complete unavailable v1 response. This task did not restart it,
enable PHYSICS_ENABLED, publish profiles or migrate retained data. Same-origin
development proxy or correctly allowed frontend CORS origin remains necessary.

Real sensor units/targets/side/scaling, transformer specifications, sourced losses
and thermal applicability are still missing. No frontend constant or selected
fleet nameplate is substituted. No thermal/FEM equation or physical parameter was
added. Selected IEEE/IEC full-equation text remains unverified as documented in
[physics_references.md](physics_references.md); no new source/compliance claim.
Ageing prerequisites and a defensible FEM common target remain unresolved.

The 708-entry source audit preserves all prior reports, canonical plan, frozen
contracts, backend, ML, FEM and validation sources. Plan SHA-256 remains
`59168b51219ce0ebffb5d5a1ac831f6cd66e28f8c33cabcf07fb5e60c78a96d8`.
Only the three listed pre-existing frontend files were intentionally edited;
the existing `.frontend.log` also advanced naturally while Vite served requests.
Existing uncommitted work was retained. No source or prior artifact was deleted.
The 21 local links in the new report/frontend README resolve; `git diff --check`
passes. No test fixture import exists under production `frontend/src`.

| Phase 6 exit criterion | Status |
|---|---|
| Existing design remains recognizable | PASS: unchanged styles/nav/charts and zero-pixel differences in two unaffected views; thermal/mobile inspected. |
| Values labelled with units/provenance | PASS: ten independent component rows, controlled node-proxy labels, references/time metadata and explicit unavailability. |
| No inert new control | PASS: existing Refresh and selector reused; error Retry and all new disclosures tested. |
| Loading/unavailable/error states work | PASS: focused tests, superseded snapshot guard and actual live 404 browser path. |
| Frontend build and applicable tests pass | PASS: 95 frontend / 57 focused backend tests and both validators; 16 inherited lint warnings remain. |

**Phase 6 focused exit criteria pass with the stated deployment and baseline
limitations.** This is not end-to-end operational physics validation or release
readiness. Stop here for user review/approval before Phase 7.
