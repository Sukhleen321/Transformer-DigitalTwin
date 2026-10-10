# Phase 4 — independent validation and comparison decision

10 October 2026; sole specification is the
[canonical implementation plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md).
Approved Phase 3 synthetic verification and convergence are preserved.
Phase 4 only; no API/frontend/database integration or production physics edits.

## Outcome and compatibility gate

There is no defensible nontrivial estimator–FEM target in the existing models.
The two-node model estimates uniform node proxies with effective R/C and
separate oil/winding heat rates. FEM computes a spatial maximum in a
homogeneous rectangle with distributed heating and prescribed edge
temperatures. No evidenced reduction connects targets, geometry/material,
heat partition, boundary transfer or time applicability.

The harness therefore runs independent numerical verification and sanity
checks. Model-to-model hot_spot_difference, absolute error and relative error
are INVALID_CONFIGURATION/null with INCOMPATIBLE_COMPARISON. No 350 K node
versus 310 K domain-maximum difference is calculated. Zero-heat equilibrium
is an independent limiting check, not a validation of their comparability.

[validation_reference.md](validation_reference.md) was written before coding
and records the compatibility table, mathematical references, input units,
initial/steady conditions and predeclared acceptance criteria. No physical
parameters are fitted and no criteria are loosened to make models agree.

## Formulas and sources

RC uses the existing project E1/E2 stored-energy balances. The harness derives
their affine steady solution and an independent 2-by-2 spectral transient
solution using closed-form eigenvalues/projectors; it does not call production
expm or rate functions to construct the reference. Modal times are -1/lambda
seconds. Integrated stored-energy change is checked against heating minus
ambient rejection using the analytic expm1 integral.

FEM reruns the approved manufactured-sine case and unchanged four-level mesh
acceptance. Separate fixed-source sanity runs double source, conductivity or
thickness and test supported zero heat. Changing conductivity keeps the
original source fixed; no accidental manufactured-source cancellation.

Source authority remains the exact locators in
[physics_references.md](physics_references.md): MIT §18.3 equations 18.15–18.18
(lumped balance), §16.4 equation 16.21 (resistance), §16.2 equations 16.6–16.8
(Fourier conduction); the cited FEniCSx Poisson/coefficient weak-form and
error-norm/convergence sections; BIPM SI locators and installed SciPy numerical
documentation. The new spectral/metric expressions are **project algebraic
derivations**, not new verified IEEE/IEC clauses. No new external source or
standards equation is claimed verified in Phase 4. Full selected IEC/IEEE
equations remain unverified, equipment applicability absent and ageing disabled.

Within-model metrics compare matching temperature **rises**, K: signed=numeric
minus analytic; absolute=|signed|; relative=absolute/|analytic rise|. The sourced
0.001 K synthetic denominator floor makes relative error null/INSUFFICIENT_DATA
with NEAR_ZERO_REFERENCE at or below the floor. Missing/invalid operands or
incompatible targets/semantics remain unavailable. Absolute error can still be
reported near zero; no Celsius ratio or relative absolute-temperature metric.

## Numerical results

The default harness reports **PASS for 15 RC checks and 10 FEM checks**,
including the unchanged FEM benchmark's nine acceptance checks. Comparison
and FEM transient validation remain explicitly unavailable alongside that PASS.
Manifest SHA-256:
`c648bf0fad068b00434942534d5e3ecf5a44bec9b1d7c16173e69561b0690f50`.

| Within-model diagnostic | Actual result | Declared acceptance |
|---|---:|---:|
| RC maximum absolute analytic temperature error | 1.830358087318018e-11 K | <=1e-8 K |
| RC maximum eligible relative analytic rise error | 5.854872142663226e-13 (1) | Reported, not a separate acceptance gate |
| RC transient stored-energy balance error at 20 s | 9.379164112033322e-12 J | <=1e-8 J |
| RC steady heat rejection balance error | 1.7564616427989677e-11 W | <=1e-10 W |
| RC one-step versus subdivided constant forcing | 4.121147867408581e-11 K | <=1e-9 K |
| RC doubled-capacitance/doubled-time difference | 0 K | <=1e-9 K |
| RC slow / fast modal times | 2.6180339887498953 / 0.38196601125010515 s | Finite, positive; transient response matches spectral reference |
| FEM finest spatial L2 / H1 seminorm errors | 0.00337992334839594 K*m / 0.545137045359989 K | L2 <=0.005 K*m; H1 convergence-order gate |
| FEM maximum-rise absolute analytic error | 0.002007734251662896 K | <=0.01 K |
| FEM maximum-rise relative analytic error | 0.0002007734251662896 (1) | Reported against nonzero 10 K rise |
| FEM source / fixed-source conductivity scaling deviations | 5.684341886080802e-14 / 2.842170943040401e-14 K | Each <=1e-9 K |
| FEM thickness-temperature / zero-source deviations | 0 / 0 K | Each <=1e-9 K |
| FEM maximum sanity-case discrete balance error | 8.526512829121202e-14 W | <=1e-8 W |

RC final states are 330.0000000000175 / 350.0000000000183 K, compared only
with their own exact 330 / 350 K steady nodes. Positive heating is monotonic;
more heat increases steady temperatures; stronger ambient conductance lowers
them; zero heat preserves equilibrium. The documented calculation envelope
and explicit initialization/missing-heat gates pass. Relative zero-heat error
is null, not a fabricated zero.

FEM L2 rates are 1.9744920307046627, 1.9934926491472746, 1.9983631008215796
(>=1.8); H1 rates are 0.9891011038360992, 0.9972535922789274,
0.9993119419622076 (>=0.9). The nonzero FEM error is expected discretization
error within predeclared criteria; no physical parameter is tuned. These are
independent manufactured-solution results, not cross-model or field accuracy.

## Exact commands and actual results

Repository-root existing environment: Python 3.12.7, NumPy 1.26.4, SciPy 1.16.2.
No dependency installed or downloaded.

| Command / check | Actual outcome |
|---|---|
| `.venv/Scripts/python.exe -m pytest ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short` before coding | Exit 0; **149 passed** in 12.12 s. Previous phase's exit evidence remains satisfied. |
| `.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py -q --tb=short`, after initial schema correction | Exit 0; **52 passed** in 9.61 s. A subsequent FEM failure-injection test brings the final new-test count to 53. |
| `.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short` final | Exit 0; **202 passed** in 19.58 s: all 53 new tests plus 149 prior focused tests. |
| `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | Exit 0; **9 unit rules, 18 vectors/inverses, 13 unit rejections, 6 fixtures, 31 result rejections, 3 JSON rejections, 94 local links** pass. |
| `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | Exit 0; **15 JSON files, 10 schemas/57 examples, 13 arithmetic/eligibility checks, 10 traces, 3 hash vectors, bounded queries and 17 local links** pass. |
| `.venv/Scripts/python.exe -m pytest ml/tests -q --tb=line -rN`, captured to `$env:TEMP/transformer-phase4-ml-baseline.txt` | Exit 1; **95 failed, 378 passed, 4 warnings** in 21.12 s. Phase 3 had 95 failed/325 passed/4 warnings. The Phase 3/4 failure-detail sections are identical after newline normalization. Missing release_manifest.json/proxy_prediction_params.json and consequent BundleNotReadyError remain; all 53 new tests pass. |
| `.venv/Scripts/python.exe -m ml.validation` twice via subprocess with stdout compared | Both exit 0, suite PASS, **identical JSON**; final CLI wall times 2.406 / 2.014 s including startup. Timing is environment-specific. |
| `.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml --target-version py310 ml/validation ml/tests/test_validation.py --output-format concise` | Exit 0; all checks pass. |
| `.venv/Scripts/python.exe -m ruff format --check --config backend/pyproject.toml --target-version py310 ml/validation ml/tests/test_validation.py` | Exit 0; **6 files already formatted**. Only new files formatted. Python 3.10 is the lint target, not a tested interpreter. |
| `.venv/Scripts/python.exe -m pip wheel <temporary-copy-of-ml> --no-deps --no-build-isolation --wheel-dir <temporary-wheel-directory>`; ZIP/source-byte check and isolated `python -I` import outside the repository | Exit 0; five validation Python modules and packaged JSON match source bytes. Installed harness PASS with blocked comparison and existing physics/FEM retained. |
| Python pathlib/JSON/local-link audit of new docs/fixtures; 22 entry-file hashes | Exit 0; **27 local links and two JSON files** pass. Only ml/pyproject.toml and docs/physics_contract.md changed among pre-existing entry files. |
| `git diff --check`; existing application import search | Exit 0; no tracked whitespace errors. No existing application/estimator/FEM module imports ml.validation; only the new package/test uses it. |

Resolved development failures: the first manifest-generation shell snippet
had a bracket SyntaxError and wrote no file; the first analytic probe rejected
NumPy scalar modes under the strict numeric gate, fixed by explicit float
conversion in the new reference calculation. A subsequent suite failed its
proxy-label check because it used an incorrect warning-code name; corrected
to the existing SIMPLIFIED_NODE_PROXY without altering production code.
Initial new pytest run had **1 failed/51 passed**: the blocked component used
assumption key description instead of the frozen schema's message; corrected
in the new component. Initial new-file lint/format/import/zip errors were
resolved. These are separate from the persistent 95 legacy failures.

Frontend/backend/simulator suites and live controls were not rerun because
Phase 4 adds no application integration. Their prior baseline evidence remains
in [phase0_report.md](phase0_report.md); no new end-to-end pass is claimed.

## Exact files changed

New Phase 4 files:

1. [ml/validation/__init__.py](../ml/validation/__init__.py): opt-in harness export.
2. [cases.py](../ml/validation/cases.py): strict synthetic manifest/quantity gates.
3. [cases_v1.json](../ml/validation/cases_v1.json): explicit fictional RC case,
   policies/perturbations and approved FEM identity/digest.
4. [metrics.py](../ml/validation/metrics.py): matched-rise metrics, null gates,
   near-zero handling and blocked contract-shaped comparison.
5. [harness.py](../ml/validation/harness.py): independent analytical checks and
   physical sanity checks with reproducible labelled JSON.
6. [__main__.py](../ml/validation/__main__.py): CLI, explicit errors and exit codes.
7. [test_validation.py](../ml/tests/test_validation.py): numerical, schema,
   negative-input, failed-check and deterministic CLI tests.
8. [reference_v1.json](../tests/fixtures/validation/reference_v1.json): synthetic
   numerical regression snapshot; never an independent physical oracle.
9. [fixture README](../tests/fixtures/validation/README.md): units/provenance,
   tolerances and reproduction.
10. [validation_reference.md](validation_reference.md): pre-code validation specification.
11. [phase4_report.md](phase4_report.md): this report.

Modified Phase 4 files:

12. [ml/pyproject.toml](../ml/pyproject.toml): package ml.validation and its JSON;
    no dependency/version changes.
13. [physics_contract.md](physics_contract.md): additive independent-validation
    and unavailable-comparison binding; public schema and unit registry unchanged.

The canonical plan, all five Phase 2 source files, all Phase 3 FEM sources and
manifest, prior tests/fixtures/reports, public result schema and unit registry
retain their entry hashes. Existing tracked application/frontend/database
sources are unchanged; prior untracked phase files and runtime logs remain.

## Assumptions, discrepancies and remaining decisions

The RC manifest repeats fictional Phase 2 fixture values: R_o=R_w=1 K/W,
C_o=C_w=1 J/K, T_a=initial T_o=initial T_w=300 K, P_o=10 W/P_w=20 W,
60 s age/100 s gap policies and explicit seed/previous-sample hold. Samples are
0, 0.1, 1, 5, 20, 100 s from a declared UTC epoch. Constant forcing and
temperature-independent parameters define this test. Synthetic variations
are declared in the manifest. None is a sensor or equipment default.

FEM retains exactly the approved sine geometry/material/boundary and mesh
policy. It is a synthetic reference, **not a transformer model**. FEM transient
validation is explicitly unavailable because it has no storage, initial state
or transient solver. RC modal checks cannot supply that missing capability.

Reopening comparison requires a sourced target/reduction record, regions and
heat partition/distribution, geometry/material-to-R/C relationship, equivalent
boundaries and a compatible steady window. Operational estimation additionally
requires real equipment/sensor specifications, parameter provenance and
applicability; field accuracy needs independent measurements with uncertainty.
Ageing, RUL and standards compliance remain unavailable. Numerical regression,
independent numerical verification, model-to-model comparison and real-world
validation are kept distinct.

Legacy missing fitted artifacts and associated baseline failures remain
separate; no unrelated fixes. Existing frontend/API/DB behavior is preserved
through isolation and unchanged source, not newly claimed end-to-end testing.

## Reproduce

```powershell
# From repository root, using the existing environment.
.venv/Scripts/python.exe -m ml.validation
.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py -q
```

`--case <path>` selects an explicit supported synthetic manifest. Default
packaged data is an intentional benchmark, never a fallback for missing
equipment. The command exits 0 only when independent checks pass; expected
blocked comparison and FEM transient checks remain labelled unavailable.
Failure returns nonzero and retains check diagnostics where computed.

## Canonical Phase 4 exit criteria

| Criterion | Assessment |
|---|---|
| Validation reproducible | **PASS**: explicit complete manifests/digests, identical repeated CLI, packaged harness and regression snapshot. |
| Numerical/physics sanity pass or justified exceptions | **PASS for supported independent cases**: analytical RC/energy/time checks and FEM numerical/convergence/scaling/balance checks; FEM transient checks explicitly unavailable for a steady model. |
| Discrepancies and limits recorded | **PASS**: numerical errors, incompatible targets, missing reduction/equipment/standards evidence, steady-only FEM and separate legacy failures documented. |
| No unsupported real-world accuracy claims | **PASS**: controlled synthetic scope preserved; no cross-model calibration, operational accuracy or field validation inferred. |

**Phase 4 exit criteria pass under the user-authorized independent-validation
branch.** Meaningful estimator–FEM comparison remains blocked, with null
outputs and explicit reasons. The repository-wide legacy baseline remains
failing. The next sequential phase would be Phase 5, subject to user approval
and these continuing synthetic/unavailable restrictions. Phase 5 is not started.
