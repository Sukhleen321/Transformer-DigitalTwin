# Phase 3 — independent synthetic 2D FEM reference

10 October 2026; baseline HEAD 3bf835c7e373565300e395ddaca4007773ef542e,
branch main. The [canonical plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md),
[physics contract](physics_contract.md), [Phase 2 report](phase2_report.md) and
[source ledger](physics_references.md) were reviewed. Phase 2 was approved by
the user with its controlled-simulation restriction. Its exit criteria remain
satisfied: before new implementation, 79 physics/thermal tests and both contract
validators passed. The same 79 tests also pass with Phase 3 included.

The sole canonical plan is unchanged (SHA256
59168b51219ce0ebffb5d5a1ac831f6cd66e28f8c33cabcf07fb5e60c78a96d8).
No Phase 4 harness, API integration, frontend change or equipment inference
is implemented. The approved estimator remains controlled-simulation only.

## Model and predeclared specification

[fem_reference.md](fem_reference.md) documented geometry, material, source,
boundary/initial data, method and numerical acceptance criteria **before
coding**. It is a model specification under the canonical plan, not a second
plan. The exact supported case is [synthetic_sine_v1.json](../ml/fem/synthetic_sine_v1.json):
Lx=Ly=d=1 m, synthetic isotropic conductivity k=1 W/(m*K), Tb=300 K and
manufactured amplitude A=10 K. These are declared verification inputs, not
real transformer dimensions, material properties or temperatures.

The independent ml.fem package solves steady homogeneous conduction:

```text
j = -k grad(T)
-div(k grad(T)) = q'''              in the 2D rectangle
T = Tb                             on all four exterior edges
q''' = k A pi^2 (Lx^-2+Ly^-2) sin(pi x/Lx) sin(pi y/Ly)
T*   = Tb + A sin(pi x/Lx) sin(pi y/Ly)
```

Flux is W/m^2, source W/m^3, conductivity W/(m*K), coordinates/thickness m,
temperature K. Temperature is uniform through thickness, with zero flux on
out-of-plane faces. This is steady state; there is no time variable, initial
temperature, density/specific-heat requirement or transient capability.
The manufactured exact solution follows by direct differentiation, and its
integrated source is exactly 80 W with maximum 310 K at the rectangle center.

Fourier-law authority is MIT §16.2 equations 16.6–16.8. The weak formulation
is checked against Langtangen/Logg/Dokken's Poisson equations (2)–(5) and
coefficient variational-form section. Error-norm/rate and SciPy sparse-solve
locators are recorded in [physics_references.md](physics_references.md).
No IEEE/IEC equation, real material-table value, standards compliance or field
accuracy is asserted. The selected standards clauses remain unverified.

Continuous P1 triangles, two per structured cell, use a fixed SW–NE diagonal.
Element stiffness is k*d*area*grad(N_i).grad(N_j); source loads use order-6
tensor Gauss-Legendre/Duffy triangle quadrature. Boundary elimination retains
the full prescribed nonzero data. Sparse direct SuperLU uses COLAMD ordering,
use_umfpack=False and a supplied backward-residual threshold. An algebraic
boundary-temperature shift reduces cancellation without adding physical data.

## Numerical verification and convergence

Independent tests include a hand-computed single-triangle stiffness/load/energy
check; exact polynomial quadrature integrals; an affine patch with nonconstant
Dirichlet data; and a quadratic manufactured solution on unequal side lengths
with nonunit conductivity/thickness. The latter checks integrated field error,
not merely nodal error. Physical checks verify zero heat, monotone heating,
conductivity and thickness scaling, and discrete reaction/source balance.

The sine benchmark's measured refinement results are:

| nx=ny | Nodes / triangles | h (m) | L2 temperature error (K*m) | Gradient H1 error (K) | Maximum (K) |
|---|---|---|---|---|---|
| 8 | 81 / 128 | 0.1767766953 | 0.2113277347 | 4.3179828301 | 309.8724767920 |
| 16 | 289 / 512 | 0.0883883476 | 0.0537743501 | 2.1753633636 | 309.9679342557 |
| 32 | 1,089 / 2,048 | 0.0441941738 | 0.0135043625 | 1.0897542352 | 309.9919719652 |
| 64 | 4,225 / 8,192 | 0.0220970869 | 0.0033799233 | 0.5451370454 | 309.9979922657 |

Observed L2 orders: **1.974492, 1.993493, 1.998363** (required >=1.8).
Observed H1 orders: **0.989101, 0.997254, 0.999312** (required >=0.9).
Both norms decrease on every level. Final L2 <=0.005 K*m and maximum error
**0.0020077343 K** <=0.01 K pass the predeclared criteria.

- Largest free-equation scaled backward residual: **3.144659e-16**, below 1e-10.
- Largest source/reaction imbalance: **3.268497e-13 W**, below 1e-8 W.
- Integrated source on every mesh agrees with analytic 80 W within 1e-6 W.
- Order-6/order-8 final L2 difference: **5.874207e-15 K*m**, below 1e-8 K*m.

All benchmark acceptance checks pass. Criteria were not loosened after runs.
The regression fixture stores selected observed numbers with units/provenance;
it is a regression record, **not** independent truth. Analytic and patch tests
provide the independent numerical verification. A direct residual or discrete
reaction balance alone would not establish discretization convergence.

## Output and comparison limits

The independent artifact is always SIMULATED_REFERENCE, SIMULATED origin,
SYNTHETIC verification and CONTROLLED_SIMULATION context. It includes complete
case inputs, content digest, model/equation IDs, dependency versions, mesh and
verification references. Quantities carry units and provenance. Case digest:
e7dbc75fa6d4c5fb9bf2ea7af2b4c8e4da32637e48ccc4dd1fc071b4b3d432ea.

Invalid case data returns INVALID_CONFIGURATION with null reference maximum
from the CLI. Failure of convergence/acceptance returns MODEL_ERROR and null
published maximum while retaining diagnostic mesh values. Numerical overflow,
nonfinite solutions and failed residual checks are explicit errors; neither
missing values nor round-off-to-zero error norms can silently publish success.

The target is SYNTHETIC_RECTANGLE_DOMAIN_MAXIMUM. It has no established
location/geometry/material/source/cooling mapping to the approved two-node
estimator. No model-to-model comparison is attempted; the frozen estimator's
fem_hot_spot_temperature and hot_spot_difference remain unavailable. Later
comparison needs explicit same-target and compatible steady-state assumptions.
This verification establishes code behavior on a synthetic PDE, not hidden
transformer hot-spot accuracy, real-world validation, ageing or RUL.

## Exact changed files

New in Phase 3:

1. [ml/fem/__init__.py](../ml/fem/__init__.py): independent exports.
2. [solver.py](../ml/fem/solver.py): mesh, P1 element assembly, quadrature,
   boundary elimination, sparse solve and residual/balance/error diagnostics.
3. [benchmark.py](../ml/fem/benchmark.py): strict synthetic manifest,
   manufactured fields, acceptance checks and labelled reproducible artifact.
4. [__main__.py](../ml/fem/__main__.py): deterministic command and explicit errors.
5. [synthetic_sine_v1.json](../ml/fem/synthetic_sine_v1.json): complete declared case.
6. [test_fem.py](../ml/tests/test_fem.py): 70 deterministic numerical/edge cases.
7. [reference_v1.json](../tests/fixtures/fem/reference_v1.json): bounded regression data.
8. [fixture README](../tests/fixtures/fem/README.md): provenance and reproduction.
9. [fem_reference.md](fem_reference.md): pre-code specification and final runtime limits.
10. [phase3_report.md](phase3_report.md): this report.

Modified in Phase 3:

11. [ml/pyproject.toml](../ml/pyproject.toml): register ml.fem and its packaged JSON;
    no dependency/version changes.
12. [physics_contract.md](physics_contract.md): additive independent-artifact
    binding and explicit unavailable comparison/API target policy.
13. [physics_references.md](physics_references.md): verified conduction/FEM locators.

Entry-file hash comparison finds only those three pre-existing files changed.
The canonical plan, all five Phase 2 source files, its tests/report, public
result schema and unit registry are unchanged. Pre-existing untracked Phase
0/1/2 files and runtime logs remain in place. No legacy tests, application,
frontend, API or database code is edited; no existing module imports ml.fem.

## Actual commands and results

Repository-root environment: Python 3.12.7, NumPy 1.26.4, SciPy 1.16.2.

| Command / check | Real result |
|---|---|
| `.venv/Scripts/python.exe -m pytest ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short` before coding | Exit 0; **79 passed** in 3.10 s. |
| `.venv/Scripts/python.exe -m pytest ml/tests/test_fem.py -q --tb=short` initial | Exit 0; **67 passed** in 5.85 s. Three additional robustness tests were added afterward. |
| `.venv/Scripts/python.exe -m pytest ml/tests/test_fem.py ml/tests/test_physics.py ml/tests/test_thermal_twin.py -q --tb=short` final | Exit 0; **149 passed** in 8.79 s: 70 FEM and 79 prior tests. |
| `.venv/Scripts/python.exe -m pytest ml/tests -q --tb=line -rN`, redirected to `$env:TEMP/transformer-phase3-ml-baseline.txt` | Exit 1; **95 failed, 325 passed, 4 warnings** in 11.62 s. Prior phase: 95 failed/255 passed/4 warnings. All 70 new FEM tests pass; failure output retains FileNotFoundError for absent fitted artifacts and consequent BundleNotReadyError. No unrelated repair. |
| `.venv/Scripts/python.exe -m ml.fem` twice, stdout captured and compared | Both exit 0 / READY; identical JSON. First final CLI wall time **1.791 s** including startup. Initial in-process run **0.947 s**. |
| `.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml --target-version py310 ml/fem ml/tests/test_fem.py --output-format concise` | Exit 0; all checks pass. |
| `.venv/Scripts/python.exe -m ruff format --check --config backend/pyproject.toml --target-version py310 ml/fem ml/tests/test_fem.py` | Exit 0; **5 files already formatted**. Only new files were formatted. |
| `.venv/Scripts/python.exe -m pip wheel <temporary-copy-of-ml> --no-deps --no-build-isolation --wheel-dir <temporary-wheel-directory>`; ZIP inventory/source-byte comparison; isolated `python -I` benchmark import | Exit 0; four FEM modules plus case JSON match final source bytes; wheel benchmark READY from a directory outside the repo; no ml.physics import. Existing physics package also retained. No dependency installed. |
| `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` | Exit 0; **9 unit rules, 18 vectors/inverses, 13 unit rejections, 6 fixtures, 31 result rejections, 3 JSON rejections, 90 local links** pass. |
| `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | Exit 0; **15 JSON files, 10 schemas/57 examples, 13 arithmetic/eligibility checks, 10 traces, 3 hash vectors, bounded queries and 17 documentation links** pass. |
| Python pathlib/Markdown local-link and JSON checks on Phase 3 fixtures/documents plus source ledger | Exit 0; **37 local links and two strict JSON files** pass. |
| `git diff --check`; entry-hash comparison; import search over ml/backend/simulator | Exit 0; no tracked whitespace errors. Only the three listed pre-existing files changed; existing code has no FEM imports. |

Initial new-file lint found 48 formatting/import/zip issues, then five remaining
issues after formatting, then one long string; these were corrected in new
files only. An intermediate robustness run had **1 failed/148 passed** because
manufactured-source overflow was classified as INVALID_CONFIGURATION. Explicit
derived-source overflow handling now yields MODEL_ERROR, and the final 149
tests pass. These resolved development failures are separate from the 95
persistent legacy failures. No analytical/convergence criterion failed.

Full frontend/backend/simulator suites were not rerun because their code and
integration are unchanged. Their [Phase 0 results](phase0_report.md) remain
the evidence; this report does not claim they newly passed. Python 3.10 is the
lint target, but execution on that interpreter was not available/tested.

## Reproduction and remaining limits

```powershell
# From the repository root; existing environment/dependencies required.
.venv/Scripts/python.exe -m ml.fem
.venv/Scripts/python.exe -m pytest ml/tests/test_fem.py -q
```

The command emits JSON to stdout; retain it by redirecting stdout to a file.
`--case <path>` explicitly selects a supported synthetic manifest. There is no
equipment fallback. Default finest resolution has 4,225 nodes / 8,192 triangles;
an explicit cap of 128 subdivisions per direction bounds custom cases. Sparse
factorization adds fill-in cost; native peak memory was not measured. Timing is
environment-specific, not a performance guarantee.

Real geometry, material-property curves, source distribution, boundary/cooling
and independent measurements are absent. Transient storage/time convergence,
mixed/Robin/Neumann boundaries, anisotropy, fluid flow, radiation, contact
resistance and real winding maxima are unsupported. Selected standards and
ageing prerequisites remain unavailable. No real-world accuracy is established.

## Canonical Phase 3 exit criteria

| Criterion | Status / evidence |
|---|---|
| Independent numerical verification and mesh-convergence tests | **PASS**: exact element/patch/quadratic checks plus sine norms, four-level refinement and predeclared acceptance. |
| Reproducible simulation with explicit parameters | **PASS**: sourced synthetic manifest, digest, deterministic repeated CLI, packaged case and regression fixture. |
| FEM provenance preserved | **PASS**: simulated-reference labels on solution/artifact; units, case and numerical/mesh evidence accompany outputs. |
| Comparison restricted to compatible quantities | **PASS by withholding comparison**: no matching estimator target established, no differences computed or API component populated. |

**Phase 3 numerical exit criteria pass.** This is a restricted synthetic
reference, not an operational transformer model. The wider baseline remains
failing. Stop after Phase 3 and wait for review/approval; Phase 4 is not started.
