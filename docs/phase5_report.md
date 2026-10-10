# Phase 5 report — persistent physics integration and API boundary

10 October 2026. Phase 5 only, under the canonical
[Transformer_DigitalTwin_Physics_First_Implementation_Plan.md](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md)
and approved [physics contract](physics_contract.md). No competing plan, commit,
push, frontend work or Phase 6 implementation. Approval is required before
continuing. The earlier Phase 0–4 reports remain unchanged.

## Outcome and boundaries

Implemented a separate read-only physics resource and opt-in, transactional
PostgreSQL persistence around the **unchanged** physics foundation. Controlled
RC temperatures retain their synthetic context and SIMPLIFIED_NODE_PROXY
warning. They are idealized oil/winding node proxies, not operational transformer
hot-spot estimates. Missing inputs, unsupported units, stale events, unresolved
identities and invalid state produce null components with explicit reasons.

No FEM solve runs in the server. All FEM hot-spot/comparison and ageing outputs
remain unavailable. No RUL/failure probability output is added. Full IEEE
C57.91-2025 / IEC 60076-7:2018 equation text remains unverified as documented in
[physics_references.md](physics_references.md); no standards-compliance claim.
No physical equation, material property, real equipment parameter or calibration
coefficient was added. Existing Phase 2–4 references and independent numerical
verification remain the evidence for the unchanged synthetic numerical models.

## Architecture and exact Phase 5 files

The pre-code architecture/design and migration risks were reported before
implementation. FastAPI read routes retain public-read conventions; strict
telemetry/acquisition/analytics schemas are unchanged. Existing ingestion locks
and transaction boundaries cover the new result/checkpoint writes. PostgreSQL
is authoritative; there is no persistent global physics estimator or unlimited
history replay. Details: [physics_integration.md](physics_integration.md).

Added:

- `backend/app/models/physics.py`
- `backend/alembic/versions/0005_physics_persistence.py`
- `backend/app/repositories/physics_repo.py`
- `backend/app/services/physics_codec.py`
- `backend/app/services/physics_service.py`
- `backend/app/schemas/physics.py`
- `backend/app/api/v1/physics.py`
- `backend/tests/test_physics_codec.py`
- `backend/tests/test_physics_integration.py`
- `docs/physics_integration.md`
- `docs/phase5_report.md`

Modified:

- `backend/app/models/__init__.py`: register four ORM models.
- `backend/app/api/v1/router.py`: register the separate read route.
- `backend/app/core/config.py`: PHYSICS_ENABLED, default false.
- `backend/app/services/ingestion_service.py`: conditional preparation in the
  existing telemetry transaction, before commit; retries do not recompute.
- `backend/README.md`: migration/configuration/startup/recovery guidance.
- `backend/docs/api.md`: document the new operation and eligibility limits.
- `backend/examples/requests.http`: requests for the new operation only.
- `docs/physics_contract.md`: replace reserved-route/deferred-persistence text
  with additive Phase 5 binding. Frozen JSON schema/unit registry untouched.

The API reference and HTTP examples were added to cover this new operation;
older missing-operation documentation was not repaired. `ml/pyproject.toml` was
already modified on entry by approved earlier phases and was not edited here.
Other pre-existing untracked files/logs and previous phase artifacts were kept.

## Persistence, migration and recovery

Alembic 0005 follows 0004 and adds **empty** physics_records, physics_profiles,
physics_events and physics_checkpoints. No existing columns/data are modified;
no synthetic fixture is installed as equipment configuration. Existing migration
round-trip, legacy-row preservation and Alembic metadata checks pass on disposable
PostgreSQL databases. Retained demo/production databases were not migrated or reset.

Records use composite `(asset, kind, ID)` identity and canonical, sorted, compact,
finite JSON SHA-256 digests. Separate MODEL, REGISTRY, PARAMETERS, CONFIGURATION,
SOURCE_MAP and EVIDENCE namespaces resolve before READY. Model/registry records
fingerprint the actual approved foundation source bytes. Published IDs cannot be
reused with different content. PostgreSQL triggers reject record update/delete
and event update. Configuration retains all its evidence IDs, including references
outside lineage. Publication runs inside a savepoint, under the same asset row
lock as ingestion; the caller owns commit. There is no HTTP write endpoint.

An explicit profile binds activation time, selection, policy, quantity definitions,
equipment, controlled forcing and seeds to an asset/source identity. It never reads
fictional fleet ratings as physical inputs. Synthetic records cannot publish as
OPERATIONAL. Supported raw ATI DEG_C is converted by the existing unit registry;
unknown SOURCE_UNIT is never interpreted as Celsius. Optional current-squared
loss requires explicit rating, no-load/rated-load losses, reference temperature,
side, RMS semantics, energization and compatible evidence; it does not feed thermal
forcing automatically.

Every configured ingestion restores a new estimator from a checked, asset-owned
checkpoint. Checkpoints bind codec/model, event watermark, input/result digests
and optional ThermalState. Validation checks ownership, timestamps, source runtime,
parameter bounds, evidence resolution and available node outputs. Incompatible
state is quarantined. Read also withholds a corrupt selected checkpoint's thermal
values. The adapter uses the existing estimator's state container only after
codec/ownership checks; future foundation state changes require codec/release review.

Telemetry, receipt/legacy effects, physics event and checkpoint share one commit.
Failure rolls everything back. Tests cover failed checkpoint write, failed commit,
fresh committed Sessions and concurrent exact retries. Duplicate/conflicting/late
observations follow existing ingestion semantics; late events never advance the
head. Invalid required inputs clear continuity. An accepted unprocessed interval
also breaks continuity. Missing identities never trigger fabricated defaults or
implicit backfill. Gap/version resets require explicit seeds at the reset event.
Corrupt state requires a new configuration ID, activation after the checkpoint,
matching explicit initial conditions and `publish_profile(..., recover=True)`.

Bounds are 64 KiB per encoded record, 64 evidence records per profile, 32 quantities
per map, 128 characters per identity, 4096 permanent identities per asset, and 4096
retained events per asset. Pruning occurs on configured ingestion, by 31-day receipt
age and count; the protected checkpoint event counts toward the cap and survives
age expiry. No background pruning or global asset quota was added. GET selects
one event in a 31-day event-time window and bounded identity lookups. Legacy
telemetry retention is unchanged. Downgrade removes physics data and requires
appropriate backup authorization outside disposable tests.

## Endpoint examples and semantics

```http
GET /api/v1/transformers/TX-001/physics
GET /api/v1/transformers/<registered-synthetic-asset>/physics?at=2026-10-10T00:00:01Z
X-Request-ID: physics-read-example
```

The first request returns HTTP 200 with all ten values null if integration is off
or no explicit matching result exists. The second requires retained observations
and an explicit synthetic profile; it does not install the test fixture. `at` must
be aware ISO time, normalizes to UTC, and cannot exceed server time. Unknown or
repeated query parameters are 422. Default cutoff is trusted current time. The
selected telemetry event must have its matching physics event; GET never substitutes
an older READY event. New effective profile without a matching observation withholds
derived values. Historical events resolve their own immutable identities.

The integration tests use the explicitly fictional Phase 4 RC case, with raw ATI
26.85 DEG_C (300 K), Ro=Rw=1 K/W, Co=Cw=1 J/K, Po=10 W, Pw=20 W and initial nodes
300 K, under its declared ranges/policies/evidence. Those values exist only in tests.
At +1 second the asserted endpoint outputs are:

| Component | Unit | Status/value in controlled test |
|---|---|---|
| measured_oil_temperature | DEG_C | unavailable/null (synthetic is not measured operational data) |
| top_oil_temperature | DEG_C | READY, 35.97672139752427, idealized oil node |
| hot_spot_temperature | DEG_C | READY, 42.96989878808216, idealized winding proxy |
| top_oil_rise | K | READY, 9.12672139752425 |
| winding_hot_spot_gradient | K | READY, 6.993177390557889 |
| total_loss | W | unavailable/null in the thermal-only profile |
| ageing_acceleration_factor | 1 | unavailable/null |
| equivalent_ageing_hours | h | unavailable/null |
| fem_hot_spot_temperature | DEG_C | unavailable/null, SIMULATED_REFERENCE label retained |
| hot_spot_difference | K | unavailable/null |

The optional separate loss test supplies Phase 2 fictional prerequisites and
10 A in all three phases, giving 10 + 30*(10/10)^2 = **40 W**. Removing any required
rating/reference/RMS/current prerequisite returns null. No real rating or loss
is inferred. Long decimal values above record regression evidence, not supported
physical measurement precision.

Response excerpt (the actual response always includes all ten full components):

```json
{
  "physics_contract_version": "1.0.0",
  "timestamp": "2026-10-10T00:00:01Z",
  "context": "CONTROLLED_SIMULATION",
  "lineage": {
    "source_kind": "SIMULATED",
    "origin_kind": "SIMULATED",
    "input_verification": "SYNTHETIC"
  },
  "components": {
    "hot_spot_temperature": {
      "value": 42.96989878808216,
      "unit": "DEG_C",
      "result_kind": "CALCULATED_ESTIMATE",
      "status": "READY"
    },
    "fem_hot_spot_temperature": {
      "value": null,
      "unit": "DEG_C",
      "result_kind": "SIMULATED_REFERENCE",
      "status": "INVALID_CONFIGURATION"
    }
  }
}
```

Full runtime responses preserve versions, reasons, missing inputs, assumptions,
warnings, coverage and provenance and validate against the unchanged schema.
Cold-start thermal output is INITIALIZING/null. Malformed transport context,
source labels or missing evaluation times are rejected by the codec before
publishing a profile, separately from domain inputs that remain unavailable. Missing-result/disabled response
adds PHYSICS_RESULT_UNAVAILABLE/PHYSICS_DISABLED reasons; input failures preserve
contract status priority and nulls. Event time is source time, evaluated_at is
server read time, and receipt time is persisted separately and remains in existing
telemetry/receipt resources. Controlled freshness uses cutoff time; operational
freshness uses current server time even for historical cutoffs. Existing public
read/authentication conventions are retained: 404 unknown asset, 409 incompatible
source, 422 invalid request and sanitized 500 internal error, correlated X-Request-ID.

## Actual commands/results

Python/pytest used the existing repository `.venv/Scripts/python.exe`. Backend
runs used disposable databases created/dropped by existing fixtures, with
TEST_DATABASE_URL set to the documented local demo PostgreSQL administrative
connection on port 55433. No retained database was changed. The installed third-party
`tests` package still shadows repository tests; the existing process-only namespace
workaround was used, not a source/dependency fix.

Backend runner, from `backend/` (the path list below is substituted for `paths`):

```powershell
& ../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; sys.path.insert(0,str(pathlib.Path("..").resolve())); ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q","--tb=short", *sys.argv[1:]]))' <paths>
```

| Command/run | Real result |
|---|---|
| Pre-code focused physics/FEM/validation pytest | Exit 0, 202 passed, 20.07 s. |
| Pre-code existing backend selection listed below | Exit 0, 238 passed, 1 warning, 18.33 s. |
| Same existing selection + new tests, before final cap=1 boundary case | Exit 0, 291 passed (238 existing + 53 new), 1 warning, 20.36 s. |
| `tests/test_physics_codec.py tests/test_physics_integration.py`, including cap=1, before final metadata guards | Exit 0, 54 passed, 1 warning, 12.80 s. |
| Final same existing selection + all new tests, including metadata guards | Exit 0, **295 passed (238 existing + 57 new)**, 1 warning, 20.35 s. |
| Broader backend selection including ingestion/hardening below | Exit 1, 4 failed, 321 passed, 1 warning, 17.18 s. All 49 new tests present at that run passed. Failures match Phase 0; later new cases passed in the final run. |
| `.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short` | Exit 0, 202 passed, 18.88 s. |
| `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | Exit 0: 9 rules, 18 vectors/inverses, 13 unit rejections, 6 fixtures, 31 result rejections, 3 JSON rejections; **98 local links** pass. |
| `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | Exit 0: 15 files, 10 schemas/57 examples, 13 eligibility checks, 10 traces, 3 hash vectors, bounded queries, 17 local links. |
| `.venv/Scripts/python.exe -m ml.validation` | Exit 0, suite_status PASS; independent synthetic verification, comparison remains INVALID_CONFIGURATION/null. |
| `.venv/Scripts/python.exe -m pytest ml/tests -q --tb=line -rN` | Exit 1, 95 failed, 378 passed, 4 warnings, 22.25 s. Failure-detail section identical to Phase 4 after newline normalization. |
| Ruff check/format check from backend/ on the nine new Python files | Exit 0; final checks pass. Existing unrelated files were not reformatted. |
| Temporary backend `pip wheel --no-deps --no-build-isolation`, ZIP/source-byte audit | Exit 0; 103 application source files matched the wheel. No dependency installed/upgraded. |
| Temporary wheel startup/OpenAPI with TestClient; disposable PostgreSQL startup/readiness test | Exit 0; separate GET/error schemas registered, startup/readiness checks pass. |
| Entry-file SHA-256 audit; git diff --check | Pass; only declared pre-existing files changed, canonical/frozen/frontend/numerical sources preserved. |

Existing backend selection:
`tests/test_main.py`, `tests/test_config.py`, `tests/test_telemetry_contract.py`,
`tests/test_analytics_schemas.py`, `tests/test_migrations.py`,
`tests/test_h02_contracts.py`, `tests/test_h02_http_and_diagnostics.py`,
`tests/test_h02_postgres.py`, `tests/test_h06_resources.py`,
`tests/read_api/test_contract.py`, `tests/read_api/test_latest.py`.

Broader run added `tests/ingestion/test_single.py`, `tests/ingestion/test_batch.py`,
`tests/ingestion/test_concurrency.py`, `tests/ingestion/test_lifespan.py`,
`tests/hardening/test_readiness.py`, `tests/hardening/test_repository_recovery.py`.
The four failures are the same Phase 0 cases: two variants of
`test_alert_hook_failure_rolls_back_the_transaction` (expected propagated exception,
actual sanitized HTTP 500), `test_partial_batch_validation_and_quality_stats`
(expected 200, actual 422), and `test_two_overlapping_batches_do_not_deadlock`
(expected 45 analytics rows, actual 30). They were not repaired. Phase 0's entire
backend run had 15 failures/735 passes/1 skip; the entire backend suite was not
rerun here and must not be reported as passing.

The 95 ML failures still involve missing release_manifest.json /
proxy_prediction_params.json and consequential BundleNotReadyError. No fitted
artifact, demo substitution or calibration was fabricated. Temporary logs use
`transformer-phase5-*` names under TEMP; the full ML failure section was compared
directly with `transformer-phase4-ml-baseline.txt` and is identical. The backend
warning is the pre-existing Starlette/httpx deprecation.

Resolved development issues: an oversized parametrized test name exceeded the
Windows environment-variable limit (fixed short IDs); the loss fixture's quantity
applicability did not match its declared evidence (fixed fixture, not formula);
a documentation edit initially omitted explicit UTF-8 decoding and wrote nothing
before correction. Running Ruff from the repository root with backend config
reported six I001 import-order errors because inferred first-party modules differ
by working directory; the documented backend-directory Ruff check/format check
both pass. No unrelated lint configuration was changed. A transient tool approval-review spending-cap failure prevented
one earlier edit call from executing; continuation calls succeeded. No tool safety
rejection or outstanding approval block remains.

A bare isolated `python -I` backend import failed because FastAPI is available
through this machine's user site rather than the virtualenv alone. The wheel
startup check explicitly included the existing dependency location and unchanged
ML source, with wheel-first app imports. This proves packaging/startup in the
available environment, not a freshly provisioned production image. No dependency
installation or clean Docker deployment was attempted.

## Security, compatibility, limitations and exit criteria

The integration is off by default; unconfigured ingestion does not install any
physics profile or fixture. Source/evidence publication remains trusted internal
operator work, not document verification. Digests are not signatures. Public-read
access and database-role protections remain existing deployment responsibilities;
GET exposes named provenance, not stored evidence bodies, physical parameters or
exception text. No new secrets/logging of payloads or environment variables.
Runtime source-byte changes require deliberate identity/codec review rather than
silent checkpoint reuse. Retention is asset-local; fleet count/legacy storage and
production throughput remain operator responsibilities. GET has indexed bounded
selection and never solves FEM; no production load/latency claim is made.

Legacy receipt-FK reset failures remain. Immutable physics ownership additionally
prevents deleting a configured asset's published records through demo reset;
use explicit physics recovery, not a demo reset. Real operational profiles cannot
be prepared from the available fictional fleet values. Real units, sensor placement,
current side/RMS definitions, nameplate/rated-loss/reference-temperature data,
thermal applicability and supported standards/ageing history remain prerequisites.
Geometry/material/source/boundary reduction remains absent, so no FEM comparison
or FEM hot-spot is transported as a usable number.

The 509-entry source audit preserves the canonical plan, all frozen contract
schemas/unit rules, frontend source, physics/FEM/validation code, previous reports,
and the pre-existing ML pyproject modification. HTTP example additions were also
reviewed by tracked diff. Frontend tests/build were not run: no frontend source,
client contract, existing response shape or frontend dependency changed.

| Phase 5 exit criterion | Status |
|---|---|
| Relevant new tests and selected existing API regressions pass | PASS against approved baseline; final new tests 57/57 and selected existing tests 238/238. Broader existing suite remains 4 known failures; no unconditional all-backend-pass claim. |
| Responses match shared contract | PASS; unchanged schema validated for controlled responses, ten keys/units/nulls and runtime eligibility tests. |
| Invalid/missing inputs give meaningful status/reasons | PASS; unsupported source/units/evidence, stale/gap/reset/rollback/recovery/error cases covered. |
| Backend starts using current approach | PASS in available environment: FastAPI lifespan/readiness/OpenAPI and temporary-wheel startup pass; clean production deployment not established. |

**Phase 5 deliverables pass the focused criteria with the approved baseline
limitations. Full-suite/release readiness is not green.** Before frontend integration,
review this report, keep synthetic proxy wording/null states, decide deployment of
migration/profile publication, and preserve the operational evidence gates. The
legacy failures/artifact blockers need their own authorized resolution before any
release-readiness claim. Phase 6 is not started; stop for review and approval.

## Copyable focused verification commands

From `backend/`, with TEST_DATABASE_URL configured for the disposable PostgreSQL
fixtures, the exact process-only test workaround for the new suites is:

```powershell
& ../.venv/Scripts/python.exe -c 'import sys,types,pathlib,pytest; sys.path.insert(0,str(pathlib.Path("..").resolve())); ns=types.ModuleType("tests"); ns.__path__=[str(pathlib.Path("tests").resolve())]; sys.modules["tests"]=ns; raise SystemExit(pytest.main(["-q","--tb=short","tests/test_physics_codec.py","tests/test_physics_integration.py"]))'
& ../.venv/Scripts/python.exe -m ruff check app/models/physics.py alembic/versions/0005_physics_persistence.py app/repositories/physics_repo.py app/schemas/physics.py app/services/physics_codec.py app/services/physics_service.py app/api/v1/physics.py tests/test_physics_codec.py tests/test_physics_integration.py --output-format concise
& ../.venv/Scripts/python.exe -m ruff format --check app/models/physics.py alembic/versions/0005_physics_persistence.py app/repositories/physics_repo.py app/schemas/physics.py app/services/physics_codec.py app/services/physics_service.py app/api/v1/physics.py tests/test_physics_codec.py tests/test_physics_integration.py
```

From the repository root:

```powershell
& .venv/Scripts/python.exe tests/fixtures/physics/validate.py
& .venv/Scripts/python.exe tests/fixtures/hackathon/validate.py
& .venv/Scripts/python.exe -m ml.validation
& .venv/Scripts/python.exe -m pytest ml/tests/test_validation.py ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short
& .venv/Scripts/python.exe -m pytest ml/tests -q --tb=line -rN
```

The full ML command intentionally reports the unresolved baseline failures;
it is not a successful-release shortcut. The test fixture creates/drops its own
database, including committed restart/concurrency cases; profile fixtures are
not written into the retained demo database.
