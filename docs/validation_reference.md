# Phase 4 — independent validation and blocked comparison

Written before harness implementation, 10 October 2026. Governing specification:
the sole [canonical plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md).
The [contract](physics_contract.md), [two-node model](physics_model.md),
[FEM specification](fem_reference.md), sources, fixtures and approved Phase 3
results were inspected. This document specifies validation, not another plan.

## Compatibility decision

There is **no defensible nontrivial common target in the current models**.

| Requirement | Two-node estimator | Current FEM | Blocking evidence |
|---|---|---|---|
| Target | Idealized uniform winding-node proxy; uniform oil node | Spatial maximum in a synthetic homogeneous rectangle | No node-to-region/location or maximum/average mapping |
| Geometry/material | Effective resistances and capacitances; no spatial geometry | Constant-k rectangle with thickness | No documented reduction linking geometry/k to R/C |
| Heating | Separate explicit oil/winding heat rates, W | Distributed manufactured source, W/m^3 | No regions or justified heat-partition mapping |
| Boundary | Finite oil-to-ambient resistance | Prescribed temperature on all exterior edges; no z-face loss | No equivalent boundary heat-transfer relationship |
| Time | Transient, explicit seed and held forcing | Steady only; no storage or initial condition | Steady RC can be checked analytically, but time agreement alone cannot repair other incompatibilities |
| Units | Internal absolute K, public DEG_C | Absolute K | Units can be converted; conversion does not establish a common quantity |

Do not choose R/C from the FEM maximum to force agreement. Do not invent oil
regions, winding layout, material values or source partitions. A zero-heat
equilibrium shared at a declared temperature is a useful independent limiting
case, not evidence of a meaningful transformer comparison. Even identical
temperatures or equal total heat would not waive this gate.

The harness emits a contract-shaped hot_spot_difference component with
INVALID_CONFIGURATION, INCOMPATIBLE_COMPARISON and null value. Cross-model
absolute and relative error diagnostics are likewise unavailable. FEM's domain
maximum is not relabelled fem_hot_spot_temperature. Existing production model
implementations and their unavailable API components remain unchanged.

To reopen comparison, supply a sourced model-reduction/target record defining
regions, locations/averaging/maxima, geometry/material-to-R/C relationship,
heat distributions/partitions, equivalent boundaries, compatible steady-state
window and units. This is absent for both synthetic and real equipment cases.

## Independent controlled cases

The harness has an explicit packaged synthetic manifest, not an equipment
fallback. RC inputs reproduce the fictional Phase 2 test case: Ro=Rw=1 K/W,
Co=Cw=1 J/K, Ta=300 K, Po=10 W, Pw=20 W and explicit initial node temperatures
300 K. It retains the existing fixture ranges, 60 s age / 100 s gap policies,
zero required warm-up history and explicit initialization/previous-hold policy.
The source is [test_physics.py](../ml/tests/test_physics.py), not a nameplate.
Event times are explicit declared UTC and elapsed samples 0,0.1,1,5,20,100 s.

The harness feeds real PhysicsEstimator snapshots; it does not import test
helpers. It checks statuses, canonical unit export and synthetic/proxy labels.
Independent closed-form verification uses the same declared energy balances:

```text
Ts_o = Ta + Ro*(Po+Pw); Ts_w = Ts_o + Rw*Pw
B = [-(1/Ro+1/Rw)/Co, 1/(Rw*Co); 1/(Rw*Cw), -1/(Rw*Cw)]
lambda_+/- = (trace(B) +/- sqrt((B00-B11)^2+4*B01*B10))/2
u_+ = (B-lambda_- I)*(Tinitial-Ts)/(lambda_+-lambda_-)
u_- = (Tinitial-Ts)-u_+
T(t) = Ts + u_+ exp(lambda_+ t) + u_- exp(lambda_- t)
modal tau_+/- = -1/lambda_+/-                         [s]
```

This is an algebraic two-dimensional spectral solution derived from the
documented project equations E1/E2; it does not call production expm or rates
to generate its reference. It is a within-model numerical reference, not FEM
or field data. The base modal times are approximately 2.618034 and 0.381966 s,
not real transformer cooling constants. The stored-energy change (J) is checked
against integrated heating minus ambient heat rejection; the analytic integral
uses expm1(lambda*t)/lambda. No parameters are calibrated.

Separate sanity cases explicitly vary existing synthetic inputs: double both
node heat rates; halve Ro for stronger ambient conductance; double both
capacitances and double elapsed time; and set both heat rates to supported
zero. These controlled perturbations are documented test choices, not inferred
equipment specifications. Steady, transient and zero-heat checks are separate.

FEM verification reruns the approved packaged sine benchmark with its frozen
mesh/convergence policy. Separate FEM-only sanity cases keep that exact
geometry, boundary and source shape: zero heat; twice the original source;
twice conductivity **at fixed original source**; twice thickness. Use nx=ny=16
from the approved mesh sequence. Conductivity changes test conduction strength,
not an unimplemented convection coefficient. A steady solver cannot verify
transient response: that FEM check is explicitly unavailable, not reported as
passed. No input is aligned between the two model families or used to compute
a cross-model temperature difference.

## Metrics and acceptance declared before execution

Within-model temperature verification uses **temperature rises** from the
declared ambient/boundary. For matching numerical and analytical targets:

```text
signed_error = numerical_rise - analytic_rise         [K]
absolute_error = abs(signed_error)                   [K]
relative_error = absolute_error / abs(analytic_rise)  [1]
```

Numerical/analytic target IDs and K temperature-difference semantics must
match. Missing, invalid, unverified or incompatible operands produce null
metrics with reasons. No Celsius ratio or relative absolute-temperature error.
If |analytic_rise| <= the explicitly declared 0.001 K floor, relative error
is INSUFFICIENT_DATA/null with NEAR_ZERO_REFERENCE; absolute error remains
eligible. The floor is a synthetic metric policy, not a sensor threshold.
An expected near-zero unavailability does not become a zero relative error.

Predeclared RC criteria: each published temperature differs from the modal
reference by <=1e-8 K; steady endpoint at 100 s <=1e-8 K; constant-forcing
subdivision/one-step and doubled-capacitance/time differences <=1e-9 K;
monotonic/transport checks allow only 1e-9 K numerical slack; transient
stored-energy balance error <=1e-8 J; steady heat rejection error <=1e-10 W.
Values remain inside the declared 100–1000 K calculation envelope. Cold-start
estimates remain INITIALIZING/null; missing required heat must be unavailable.
The modal calculation must have finite negative eigenvalues.

FEM retains all Phase 3 criteria; no threshold is loosened. Separate nodal
source/conductivity/thickness scaling checks require <=1e-9 K deviations and
discrete reaction/source balance <=1e-8 W. Analytical maximum-rise relative
error is reported only for the approved nonzero 10 K reference, with a 0.001 K
floor. These are numerical verification metrics, not estimator–FEM errors.

The output labels scope explicitly: CALCULATED_ESTIMATE for RC quantities and
metrics, SIMULATED_REFERENCE for FEM quantities, SIMULATED origin, SYNTHETIC
verification and CONTROLLED_SIMULATION context. The suite's PASS/FAIL records
only independent checks, alongside unavailable comparison/time capabilities;
there is no aggregate operational READY. A failed check makes the command
exit nonzero and retains diagnostics. New regression snapshots are labelled
synthetic numerical regression, not independent truth.

Reproducible command and tests (from repository root):

```powershell
.venv/Scripts/python.exe -m ml.validation
.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py -q
```

No new physics law, standards clause, API, database or frontend behavior is
introduced. [Verified source locators](physics_references.md) remain the
authority for existing equations. Real-world validation, operational hot-spot
accuracy, ageing, RUL and standards compliance remain unsupported.
