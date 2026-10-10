# Phase 2 — physics foundation and restricted thermal estimator

Date: 10 October 2026. Baseline HEAD
3bf835c7e373565300e395ddaca4007773ef542e; branch main.

Reviewed the canonical plan and approved Phase 1 contract/report. Before
coding, both contract validators passed and existing thermal tests passed
(17 tests). Phase 1 exit criteria remain satisfied. The sole canonical plan
was not edited; its SHA256 is
59168B51219CE0EBFFB5D5A1AC831F6CD66E28F8C33CABCF07FB5E60C78A96D8.

## Implemented scope

The opt-in [ml/physics](../ml/physics/__init__.py) module implements typed
quantity/evidence/snapshot records, explicit unit conversions, per-component
availability, a documented current-squared loss approximation and a
CONTROLLED_SIMULATION-only two-node thermal estimator. State is explicit,
causal, per asset and aware of irregular event time, missing data, initialization,
gaps, retries and version changes. No physical parameter default or existing
empirical coefficient is imported.

[physics_references.md](physics_references.md) records selected IEC 60076-7:2018
edition 2.0 and IEEE C57.91-2025. Their full authoritative equation clauses were
not available; exact standards equation/section numbers and parameter/ageing
definitions are explicitly UNVERIFIED, not guessed. Both selected standards
thermal paths return EQUATION_UNVERIFIED/null. Catalog access is not compliance
evidence. IEEE's linked code project was inaccessible through browsing (418).

The implemented thermal equations are project-derived energy balances from
MIT's verified §18.3 equations 18.15–18.18 and §16.4 equation 16.21, combined
with an explicitly declared two-node topology. Constant R/C and held forcing
are integrated by SciPy's matrix exponential. The proxy is never offered as
an operational winding maximum. Exact implemented formulas and limitations
are in the references and [model documentation](physics_model.md).

Ageing remains unavailable because standard laws, actual insulation/fluid
applicability and supported hot-spot history are absent. No FEM, API integration,
frontend, database, simulator configuration or legacy-model change is made.

## Changed files

- [ml/physics/__init__.py](../ml/physics/__init__.py): opt-in exports.
- [types.py](../ml/physics/types.py): immutable typed snapshot/quantity/provenance,
  policy, evidence and state records.
- [units.py](../ml/physics/units.py): explicit conversions, source consistency,
  finite/range checks; no unit guesses.
- [equations.py](../ml/physics/equations.py): project loss approximation and
  general two-node heat-balance kernels.
- [estimator.py](../ml/physics/estimator.py): eligibility, independent result
  statuses, state/timestamp/version/evidence handling and contract envelope.
- [ml/pyproject.toml](../ml/pyproject.toml): include ml.physics in the existing
  package list; no dependencies/version changed.
- [test_physics.py](../ml/tests/test_physics.py): focused numerical, data/state
  edge-case and result-contract checks using fictional cases.
- [physics_contract.md](physics_contract.md): additive model binding; fixed
  public result names/units/statuses and contract version unchanged.
- [physics-units-v1.json](contracts/physics-units-v1.json): register K/W and J/K
  as identity units for explicit R/C quantities. Nine conversion rules unchanged.
- [physics_references.md](physics_references.md),
  [physics_model.md](physics_model.md), [phase2_report.md](phase2_report.md):
  traceable sources, implemented model/limits and this report.

The Phase 1 result JSON Schema, prior reports, current architecture audit,
canonical plan, original runtime logs and existing tests are preserved.

## Verification

Commands below ran from the repository root using the existing Python 3.12.7
virtual environment (NumPy 1.26.4, SciPy 1.16.2). Exit codes and counts are real.
Lint uses Python 3.10 as its target, matching the declared ML minimum; execution
on Python 3.10 itself was not tested.

| Command / check | Actual result |
|---|---|
| `.venv/Scripts/python.exe -m pytest ml/tests/test_thermal_twin.py -q --tb=line` before editing | Exit 0; **17 passed** in 1.41 s. |
| `.venv/Scripts/python.exe -m pytest ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short` final | Exit 0; **79 passed** in 2.40 s: 62 new physics cases and 17 unchanged thermal cases. |
| `.venv/Scripts/python.exe -m pytest ml/tests -q --tb=line -rN` final, output redirected to `$env:TEMP/transformer-phase2-ml-baseline.txt` | Exit 1; **95 failed, 255 passed, 4 warnings** in 7.70 s. Phase 0 was 95 failed/193 passed/4 warnings. All 62 new cases pass. Failure output contains missing `data/processed/release_manifest.json` / `proxy_prediction_params.json` and consequent BundleNotReadyError; no fitted artifacts fabricated. |
| `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | Exit 0; **9 rules, 18 exact vectors/inverses, 13 unit rejections, 6 fixtures, 31 result rejections, 3 JSON rejections, 87 local links** pass. |
| `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | Exit 0; **15 JSON files, 10 schemas/57 examples, 13 arithmetic/eligibility cases, 10 traces, 3 semantic hash vectors, bounded queries, 17 documentation links** pass. |
| `.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml --target-version py310 ml/physics ml/tests/test_physics.py` | Exit 0; all checks pass on new files only. |
| `.venv/Scripts/python.exe -m ruff format --check --config backend/pyproject.toml --target-version py310 ml/physics ml/tests/test_physics.py` | Exit 0; **6 files already formatted**. |
| `.venv/Scripts/python.exe -m pip wheel <temporary-copy-of-ml> --no-deps --no-build-isolation --wheel-dir <temporary-wheel-directory>` plus ZIP inventory and isolated `python -I` import | Exit 0; builds transformer_ml_runtime-0.1.0-py3-none-any.whl; all five ml/physics files included and PhysicsEstimator imports from the wheel. Staging/build outputs are outside the repository. No dependency install. |
| `Get-FileHash Transformer_DigitalTwin_Physics_First_Implementation_Plan.md -Algorithm SHA256`; `git diff -- ml/pyproject.toml`; `git status --short` | Canonical hash unchanged; sole tracked-code diff is package registration. Phase 0/1 documents and logs were already untracked at entry. No frontend/backend/schema/legacy-test edits. |
| Python pathlib/Markdown link check on physics_references.md, physics_model.md and phase2_report.md; `git diff --check`; import search across ml/backend/simulator | **26 local links pass**, tracked diff has no whitespace errors, no existing modules import the new package. |

Development checks initially found **2 failed/52 passed** in new tests: source
Celsius identity validation rejected supported raw Celsius and prevented the
partial measured output. Fixed the source-unit identity eligibility; subsequent
tests passed. A later reset test incorrectly expected continuity after an
invalid configuration had cleared state; corrected that test to exercise a
version change from an independently initialized stream. Final tests also cover
invalid evaluation time independently of event identity. Initial lint/format
findings in new files were corrected. These are resolved Phase 2 development
failures, separate from the persistent 95 legacy failures.

One validation-command lookup incorrectly attempted
`.venv/Scripts/python.exe tools/validate_contracts.py` (exit 1: file absent).
The actual existing checker is `tests/fixtures/hackathon/validate.py`, run
successfully above. This was a command-path mistake, not an application failure.

Numerical checks include independent adaptive-ODE comparison, analytical
steady states and stored-energy balance, plus limiting cases, causal forcing,
irregular sampling, retries, resets, version/evidence mutation, missing/invalid
inputs and schema conformance. Fictional test values verify computation only.
They do not establish transformer accuracy, ageing applicability or standards
compliance. No FEM numerical or mesh-convergence claim is made.

Frontend, full backend and simulator suites were not rerun: their code and
dependencies are unchanged and the new package is not integrated. Their actual
Phase 0 results remain in [the baseline report](phase0_report.md); they are not
reported as newly passed here.

## Remaining evidence and limitations

- Full authoritative selected-edition thermal and ageing clauses/definitions.
- Real transformer type/construction, fluid/insulation/cooling and applicability.
- Sensor units/locations/RMS side/scaling/time documentation; real loss test and
  thermal parameter data. No nameplates, losses, R/C or calibration invented.
- Actual hot-spot target mapping and independent measurements; lumped-node
  numerical verification cannot establish field accuracy.
- Supported ageing law/history and insulation/fluid prerequisites; no life
  budget or RUL. Unavailable status is intentional.
- Uncertainty propagation, persistence/checkpoints, transactional ownership,
  retention/eviction and API integration remain unimplemented.
- Existing Phase 0 missing fitted artifacts, pymodbus/import issues, backend
  regression failures and unrelated lint failures are not repaired here.

## Exit criteria

| Canonical Phase 2 exit criterion | Status / evidence |
|---|---|
| Calculations isolated from transport/UI | **PASS**: opt-in ml.physics, no existing callers or routes changed. |
| Formula sources and limitations documented | **PASS with explicit restriction**: verified general heat-transfer locators; IEC/IEEE full equations unverified/unimplemented; controlled-case model only. No standards compliance claimed. |
| Unit and edge-case tests pass | **PASS**: 62 new tests; focused regression total 79 passes; lint/format and packaging pass. The broader legacy baseline is still failing. |
| Missing inputs cannot silently produce a valid-looking estimate | **PASS**: contract-shaped null/status/reasons; missing units, evidence, parameters, seeds/history or unsupported models withhold values. |
| API contract has not drifted | **PASS**: existing APIs untouched, Phase 1 result schema unchanged, both contract validators pass. R/C identity-unit registrations and the documented isolated model binding are additive. |

**Phase 2 exit criteria pass for this restricted implementation.** Operational
IEEE/IEC thermal estimates and insulation ageing remain unavailable; real
equipment readiness is not achieved. Baseline tests are not all green.
No Phase 3 work is performed. Stop and wait for user review/approval.
