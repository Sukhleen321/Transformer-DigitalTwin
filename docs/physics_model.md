# Phase 2 physics module — implemented scope and limits

The isolated [ml/physics](../ml/physics/__init__.py) package is opt-in. The
legacy ML pipeline, empirical oil estimator, API/database and frontend do not
import it. It has no network, database, filesystem history reads, calibration,
FEM, ageing integration or physical-parameter defaults. NumPy/SciPy are already
declared dependencies of the ML package; no dependency is added.

Sources, selected standard editions and exact verified technical locators are
in [physics_references.md](physics_references.md). The general two-node model
is a project approximation, not an IEEE/IEC hot-spot model. Selected standard
equations remain unverified/unimplemented. Physical field accuracy is unknown.

## Interface

Create a [Snapshot](../ml/physics/types.py) with the five quantity maps,
source lineage, evaluation/event times, immutable versions, selected model,
time policy and evidence-record lookup. Call `PhysicsEstimator.evaluate(snapshot)`.
It returns the existing [physics result envelope 1.0.0](contracts/physics-result-v1.schema.json).
All ten components are present. Each unavailable component has null value,
independent status and reasons; valid measured/loss outputs do not certify
thermal or ageing eligibility.

`Quantity` records carry raw/current unit, quantity kind, verification,
original value/unit/conversion identity, source/evidence/applicability,
effective time and optional range. Known source units are normalized explicitly;
unknown units, booleans, strings, nonfinite values and invalid ranges cannot
become numbers. Source originals remain available. Normalization of an already
normalized quantity does not apply the Celsius offset twice. Export uses the
declared inverse conversion; an inverse quantity's recorded conversion identity
uses `inverse:<conversion_id>`. No arbitrary unit aliases or CT/PT/phase
conversions are inferred. Unsupported uncertainty propagation is reported
unavailable; source uncertainty is not converted into fabricated error bars.

Evidence IDs must resolve to nonempty source records with a compatible kind
and applicability. Synthetic leaves require a declared case and synthetic-case
record. OPERATIONAL calculations require verified live-origin inputs and event
time; synthetic evidence cannot verify equipment data. This validates supplied
records/labels; it cannot authenticate an OEM certificate or sensor claim.
Required equipment/technical/source review remains an external prerequisite.

Malformed typed caller metadata (e.g. invalid asset identity or missing aware
server evaluation time) raises InputIssue. Missing/invalid physical quantities,
event timestamps and configuration return the contract's unavailable statuses.
Future transport integration must convert malformed requests to existing 422
behavior; no new API route exists now.

## Controlled thermal model

Model ID PROJECT_TWO_NODE_RC_V1, model version 1.0.0, equation registry
physics-equations-1.0.0. Required maps:

| Input path | Unit / meaning |
|---|---|
| model_parameters.oil_thermal_resistance | K/W; positive, oil-node to ambient |
| model_parameters.winding_thermal_resistance | K/W; positive, winding-node to oil-node |
| model_parameters.oil_thermal_capacitance | J/K; positive, oil-node energy storage |
| model_parameters.winding_thermal_capacitance | J/K; positive, winding-node energy storage |
| model_parameters.minimum_temperature / maximum_temperature | Absolute K; explicit supported calculation envelope |
| environment.ambient_temperature | Absolute K; case boundary, at the source event |
| simulation.oil_heat_input / winding_heat_input | W, heat_rate; explicit nonnegative node heat inputs, at the event |
| simulation.initial_oil_temperature / initial_winding_temperature | Absolute K; explicit initial conditions at cold-start/reset event |

R/C, boundary and heat inputs require explicit ranges and traceable case
evidence. The node names are model targets. Oil temperature is not proven
top-oil equivalence, and the uniform winding node is an idealized hot-spot
proxy, not a resolved physical maximum. Every thermal output warns
SIMPLIFIED_NODE_PROXY and keeps CALCULATED_ESTIMATE with simulated origin.
The model cannot produce OPERATIONAL thermal READY in this release.

Policy requires sourced positive max_sample_age_seconds and max_gap_seconds
(s), nonnegative required_history_seconds (s), range-policy reference,
EXPLICIT_INITIAL_TEMPERATURES and PREVIOUS_SAMPLE_HOLD with their references.
No UI/legacy gap thresholds are reused. These are caller-declared application
and case policies, not fitted cooling constants.

## State and time

- One immutable state per asset within an explicitly owned estimator. Callers
  must serialize writes; the module is not a global service/scheduler.
- Cold start sets state from explicit case initial temperatures and exports
  INITIALIZING/null. A missing seed leaves the component INITIALIZING; invalid
  seed or wrong reset time is unavailable. No ambient/zero/steady-state seed.
- Previous boundary/heat input is held over the elapsed event interval and
  integrated by the affine matrix exponential. Irregular intervals are used
  exactly; replay wall time does not change dt.
- Warm-up lasts the declared supported-history duration. Until complete,
  provisional temperatures are withheld. No ageing is computed from them.
- Exact retry returns the cached thermal result without advancing state.
  Equal-time conflicting identity and late observations do not advance it.
- Stale/future/invalid required data breaks continuity. There is no implicit
  zero fill or interpolation across unsupported observations. New valid data
  needs explicit current-event initialization.
- Gaps exceeding the declared maximum reset state. Equality is accepted.
  Configuration/parameter/source-map version changes reset rather than splice
  state. Changes to source-unit mappings or parameters under a published ID
  are rejected; changing another ID does not authorize reuse of that ID.
- Within this owned process, evidence and version IDs resolve to immutable
  content records scoped to the asset. Source-map definitions are tracked per
  input path. Persistence/global identity resolution is deferred to Phase 5.
- Numerical failure or violation of the declared calculation envelope returns
  MODEL_ERROR/null and clears thermal state. No last value becomes new READY.

Coverage describes contiguous supported event-time intervals since the last
initialization, with explicit durations and gap/reset count. It is not sensor
accuracy or whole-life coverage. The owned process keeps state, last results
and evidence/version identities; no long-term retention/eviction or transactional
checkpoint system is integrated. Those need explicit Phase 5 storage policy.

## Optional loss approximation

PROJECT_CURRENT_SQUARED_LOSS_V1 requires three observed current_l1/l2/l3
quantities (A, nonnegative, declared ranges), equipment.rated_current_a
(A, positive), model_parameters.no_load_loss and rated_load_loss (W), and
loss_reference_temperature (absolute K). Selection must explicitly declare
energized=True, HV/LV side, RMS_LINE_CURRENT basis and a sourced loss-basis
reference. Current provenance must identify the same side/basis.

This estimates total_loss using the existing project current-squared scaling.
It assumes fixed reference-temperature effective phase losses and does not
correct resistance for operating temperature or include unprovided losses.
The basis/equipment applicability must be documented. No heat-location
partition is inferred, so this result does not automatically feed thermal
P_o/P_w. Missing rated loss/current or unsupported side makes it unavailable.

## Ageing, FEM and verification limits

Ageing acceleration and equivalent ageing remain null: selected standards
formulas/parameters, real insulation/fluid applicability and eligible hot-spot
history are not established. No operational ageing, absolute life, RUL or
failure probability is calculated. FEM and comparison remain unconfigured.

[Unit tests](../ml/tests/test_physics.py) declare fictional cases explicitly.
They check production conversions against frozen vectors, steady states,
stored-energy balance, independent adaptive ODE integration, causal/irregular
state evolution, monotonic heating/cooling, stronger cooling, missing/invalid
data, cold start/reset/retry/version behavior and result-schema conformance.
These are numerical verification and code tests, not equipment validation or
FEM mesh convergence. No parameters were tuned to make models agree.

```powershell
.venv/Scripts/python.exe -m pytest ml/tests/test_physics.py -q
.venv/Scripts/python.exe tests/fixtures/physics/validate.py
```

Actual commands/results, packaging and remaining baseline issues are recorded
in [phase2_report.md](phase2_report.md).
