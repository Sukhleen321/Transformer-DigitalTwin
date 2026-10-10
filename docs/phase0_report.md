# Phase 0 — repository audit and baseline report

Date: 10 October 2026 (Asia/Calcutta). Audited branch `main`, HEAD `3bf835c7e373565300e395ddaca4007773ef542e`.

## Scope and changed files

Phase 0 only: inspected the existing repository, ran baseline checks, documented current behavior and drafted the physics interface requirements. No model/API/frontend implementation, parameter changes, dependency installation, standards-compliance claim, commits or later-phase work.

Created:

- [architecture_current.md](architecture_current.md): architecture/data-flow diagram, startup/deployment/environment inventory, current routes/response shapes, telemetry/analytics behavior, frontend appearance/extension points and verification limits.
- [physics_contract.md](physics_contract.md): existing units/nulls/provenance, empirical equations/coefficient inventory, initial physics output/status requirements, error/time/version semantics and unresolved decision log.
- [phase0_report.md](phase0_report.md): this baseline and phase-boundary report.

At the time of the Phase 0 audit, the requested `Transformer_DigitalTwin_Physics_First_Implementation_Plan.md` did not exist. The full existing `Transformer_DigitalTwin_Unified_Phase_Plan.md` was read and used because it contained the requested Phase 0 scope and sequential approval protocol. It was already untracked and was not renamed/edited during that audit. Four untracked runtime logs were also present initially (`.demo-api.log`, `.demo-api-error.log`, `.frontend.log`, `.frontend-error.log`) and were left untouched. No `AGENTS.md` was found in the repository.

Post-approval clarification (Phase 1): the user confirmed [Transformer_DigitalTwin_Physics_First_Implementation_Plan.md](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md) as the sole canonical plan. That file now exists and the former filename does not. Phase 1 uses it without creating or editing another plan. The baseline results and historical audit findings in this report remain unchanged; the physics draft has since been finalized in [Phase 1](phase1_report.md).

## Baseline execution environment

Windows PowerShell, existing root `.venv` Python 3.12.7, Node v24.14.1, npm 11.11.0. The venv enables system site packages; several dependencies resolve from the user's Python installation. It is not a verified clean dependency environment.

Normal shell and node/CUA tools failed to initialize with `windows sandbox failed: helper_unknown_error: setup refresh had errors`. Shell inspection/checks continued through the approved elevated execution fallback. CUA remained unavailable, so source/CSS and an existing screenshot were inspected; no live browser/control verification is claimed.

No dependency packages were installed/downloaded. Python wheels used installed build tools with `--no-deps --no-build-isolation`; generated untracked backend/ML build directories and ML egg metadata were removed after verifying their resolved paths were within this repository. Wheels and compact test capture logs were written under the system temporary directory. Frontend build/cache output is generated/ignored, not a source change.

## Actual commands and results

Commands below use the root `.venv`; working directory matters. Exit 0 means the command succeeded, not that physical validity was established.

| Working directory | Command | Actual outcome |
|---|---|---|
| `frontend` | `npm test` | Exit 0; **6 files, 50 tests passed**, 49.29 s. |
| `frontend` | `npm run build` | Exit 0; TypeScript project build and Vite production build succeeded, 2005 modules; Vite 2.98 s. JS 372.88 kB / gzip 112.98 kB, CSS 58.80 kB / gzip 12.04 kB. |
| `frontend` | `npm run lint` | Exit 0 with **16 warnings**: unused imports, synchronous state-in-effect and fast-refresh export warnings in existing files. |
| `backend` | `../.venv/Scripts/python.exe -m pytest -q` | Exit 1; **17 collection errors**, no suite execution, due to installed `tests` package shadowing this repository's namespace directory; one existing Starlette/httpx deprecation warning. |
| root | `.venv/Scripts/python.exe -m pytest ml/tests simulator/tests -q` | Exit 1; **3 collection errors** because `pymodbus` is absent. Collection aborted; does not establish ML test results. |
| root | `.venv/Scripts/python.exe -m pytest ml/tests -q` | Exit 1; **95 failed, 193 passed, 4 warnings**. Compact repeat `--tb=line -r f` gave the same counts in 11.07 s. Failures reference absent fitted release/parameter files under `data/processed`. |
| root | `.venv/Scripts/python.exe -m pytest simulator/tests -q --ignore=simulator/tests/test_delivery_h03.py --ignore=simulator/tests/test_modbus_h03.py --ignore=simulator/tests/test_runtime_h06.py` | Exit 1; **2 failed, 46 passed**; compact repeat `--tb=line` completed in 10.82 s. Both remaining failures still require Modbus bridge imports (`pymodbus` absent); three ignored modules are unexecuted, not passed. |
| `backend` | `../.venv/Scripts/python.exe -m ruff check .` | Exit 1; **173 errors**, 39 fixable under normal fix mode. Existing issues include import order, long lines and other configured lint violations. No fixes applied. |
| `backend` | `../.venv/Scripts/python.exe -m ruff format --check .` | Exit 1; **57 files would be reformatted, 166 already formatted**. No formatting applied. |
| root | `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | Exit 0; 15 JSON files parse, **10 schemas / 57 examples**, 13 arithmetic/eligibility cases, 10 traces, 3 semantic hash vectors, bounded queries and 17 local documentation links pass. |
| root | `.venv/Scripts/python.exe -m pip wheel ./ml ./backend ./simulator --no-deps --no-build-isolation --wheel-dir $env:TEMP/transformer-phase0-wheels` | Exit 0; all three wheels built: transformer-ml-runtime 0.1.0, transformer-backend 0.1.0, transformer-simulator 1.0.0. Package creation does not establish runtime dependency completeness or fitted readiness. |
| `backend` | Source-generated `app.openapi()` inventory | Exit 0; current routes/response schemas inspected, including existing dynamic resources without typed OpenAPI response schemas. |
| root | `docker ps --format '{{.Names}} {{.Ports}}'` | Exit 0; existing transformer DB/broker/backend/frontend/Modbus server/bridge running; no container operations performed. |
| root | Read-only `Invoke-WebRequest` checks on loopback | `/health` **200**, `/health/ready` **200**, `/api/v1/transformers?limit=50&offset=0` **200, total 10**, frontend `/` on port 5173 **200**. These observe running services, not a newly launched source checkout or end-to-end physics validation. |

Ruff was repeated with concise/tail output only because its initial output exceeded the tool display limit. ML/simulator repeats captured compact tracebacks for the same reason; they were not retries after fixes. Commands to inspect files/status/versions and the failed sandbox attempts are investigative checks, not passing application tests.

### Backend baseline with process-only environment workarounds

The unrelated installed `tests/__init__.py` won import resolution over `backend/tests` (which has no root `__init__.py`). To run the actual existing suite without editing test/package code, an in-memory namespace was bound before pytest. `TEST_DATABASE_URL` pointed at the repository's documented local demo PostgreSQL service on 55433; the fixture created a uniquely named **disposable** database, migrated it and dropped it afterward. It never downgraded/reset the retained demo database. Real MQTT test variables were not supplied, avoiding publishing test traffic through the retained broker/source pipeline.

First diagnostic invocation, from `backend/`:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://transformer:transformer@127.0.0.1:55433/transformer'
& ../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q"]))'
```

Actual exit 1: **106 failed, 595 passed, 49 errors, 1 skipped, 1 warning**, 118.23 s. Most additional errors/failures are `ModuleNotFoundError: ml` because the local ML runtime is not installed/on that working directory's import path. Existing latest-state shape expectations also fail. Real broker test skipped explicitly for missing `MQTT_TEST_HOST/PORT`.

Second diagnostic invocation adds only the repository source import path, retains the namespace workaround and captures compact output:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://transformer:transformer@127.0.0.1:55433/transformer'
& ../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; sys.path.insert(0,str(pathlib.Path("..").resolve())); ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q","--tb=line","-r","f"]))' > $env:TEMP/transformer-phase0-backend-baseline.txt 2>&1
```

Actual exit 1: **15 failed, 735 passed, 1 skipped, 1 warning**, 488.81 s (8 min 8 s). No collection/setup errors remained. This run includes the existing real PostgreSQL integration/migration tests, the 10,000-row ingestion test and million-row read test. Passing those individual tests does not cancel the failed regression checks below. The real broker test remains unexecuted; no failed test expectation or runtime behavior was changed.

| Failing tests / count | Observed failure and practical limitation |
|---|---|
| `demo/test_deliverables.py::test_api_reference_and_http_requests_cover_every_operation` (1) | Existing consolidated API document lacks the expected ingestion-status operation entry; older documentation is incomplete. |
| `demo/test_reset.py::test_fk_safe_reset_clears_all_requested_tables` (2 variants), `demo/test_seed.py::test_seed_idempotent_reset_determinism_and_scenario_chain` (1) | Deleting telemetry violates the ingestion-receipt foreign key. Current reset/seed-reset workflow is not verified safe/correct with added receipt tables. These failures occurred only in the disposable test database; no retained demo reset was attempted. |
| `hardening/test_concurrency.py::test_http_mqtt_style_and_real_replay_concurrently` (1) | Replay raises HTTP 422 requiring a registered replay_transformer_id; legacy scenario/setup does not meet current replay requirements. |
| `ingestion/test_batch.py::test_partial_batch_validation_and_quality_stats` (1) | Expected HTTP 200, observed 422. Request-level versus row-level rejection expectation remains unresolved. |
| `ingestion/test_concurrency.py::test_two_overlapping_batches_do_not_deadlock` (1) | Analytics row count observed 30 versus expected 45. Cannot claim full concurrent analytics preservation from this baseline. |
| `ingestion/test_single.py::test_alert_hook_failure_rolls_back_the_transaction` (2 variants) | Test expected an exception to propagate; HTTP response was 500 and no exception propagated to its assertion. Rollback test expectation/transport behavior needs review; this result alone does not establish data loss. |
| `performance/test_differential.py::test_500_mixed_rows_match_row_by_row_with_late_arrivals` (2 chunk sizes) | Bulk/row telemetry snapshots differ. Compact diff does not identify every differing field; root cause not established. |
| `performance/test_differential.py::test_duplicate_chunks_bypass_inference_hook_and_bulk_writes` (1) | Duplicate path reaches a function the test requires to be bypassed. Duplicate-work/performance invariant fails. |
| `performance/test_differential.py::test_batch_repository_failure_preserves_telemetry_and_analytics` (1) | Injected repository RuntimeError escapes; expected recovery behavior is not established. |
| `performance/test_differential.py::test_chunk_sql_count_does_not_grow_per_healthy_row` (1) | Observed 913 statements versus expected fewer than 30; the existing SQL budget fails. |
| `test_schema_orm.py::test_every_out_model_converts_postgres_orm_and_latest_state` (1) | Latest-state output contains additive analytics_availability beyond the older exact-key expectation. Current shape and legacy assertion differ. |

No assertion mismatch was relabelled as harmless without evidence, and these failures were not repaired in a documentation-only phase. The passing running-service readiness check selects its existing demo configuration and does not contradict missing strict fitted artifacts in source tests.

## Findings, assumptions and unresolved decisions

- Real equipment identity/type, cooling, fluid/insulation, nameplates, rated losses, temperature-rise/gradient/time constants and thermal applicability are unsupported. The operational roster supplies explicitly fictional values only.
- Public OTI/ATI units, WTI continuous-versus-contact semantics, sensor positions, oil-level scale, electrical side/scaling, timezone, counter/sign/continuity policy need owner/OEM/source evidence. WTI is excluded from the current continuous thermal model; current acquisition schema cannot declare verified `DEG_C` for WTI.
- The existing model is an empirical oil-indicator estimator with source-unverified output, not hot-spot. Its current-squared/power fallback and mode names need review before any physical reuse. Parameter values and calibration choices are documented as existing code, not newly approved physics inputs.
- Strict fitted release files expected by tests/loaders are absent. No artifacts were fabricated, no model recalibration performed and no demo mode was substituted to hide failed strict tests.
- Physical ageing and FEM are not implemented. Existing RUL is a fictional degradation scenario or an operational prerequisite check; matching synthetic/model outputs is not real-world validation.
- IEEE C57.91 / IEC 60076-7 equations, editions and applicability are **unverified in Phase 0**. No authoritative formula or standards compliance is claimed. Source verification belongs to the planned equation-selection work; missing access must remain explicit.
- New physics output placement/version, per-component status mapping, event-time stale/gap/range policy, longer history and comparison assumptions require Phase 1 decisions. See D01–D12 in the physics draft.
- The appearance audit uses current code/CSS plus prior ten-asset screenshot evidence. Frontend unit tests/build pass; exhaustive live controls/mobile/end-to-end verification was not completed in this documentation phase.

No unrelated fixes were made. Package build outputs were cleaned; all existing tracked source and frontend styling remain unchanged.

## Phase 0 exit criteria

| Required criterion | Audit assessment |
|---|---|
| Baseline test/build results recorded | PASS — original invocation errors, diagnostic workarounds, completed suite counts, skips, lint failures and successful builds/fixture checks are all recorded. Baseline is **not green**. |
| Existing telemetry/API contracts documented | PASS — current routes, formats, fields, provenance, quality/status differences and source-unit ambiguity are recorded. |
| Initial draft uses existing names where appropriate | PASS — existing names/metadata retained; new conceptual fields explicitly unimplemented and pending Phase 1. |
| Unknown units/unsupported physical parameters listed | PASS — field inventory and decision log; no real parameters invented. |
| No application behavior removed | PASS — `git diff --exit-code` returned 0 for tracked files; status shows only the three new documents plus the original untracked plan/logs. No source, styling, lockfile or configuration edits. |

**Phase 0 audit exit criteria PASS; baseline tests/lint are NOT GREEN.** All local links in the three new documents were checked successfully. No new tests were added for this documentation-only change. The complete project's definition of done is not yet satisfied. Work stops at Phase 0; the recommended next phase is **Phase 1: contract and physical model specification**, only after user review/approval. Do not start Phase 2 physics or FEM while resolving Phase 1 decisions.
