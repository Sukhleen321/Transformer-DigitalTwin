# Model limitations and intended use

Release audit: 10 October 2026. Canonical authority is
[the physics-first plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md).
The [Phase 7 report](phase7_report.md) records current evidence and a NOT READY
release decision. Earlier approved reports remain historical evidence.

## Supported use

- Read-only source-aware monitoring with existing empirical analytics, subject
  to their documented prerequisites and unresolved regression failures.
- Controlled-simulation verification of PROJECT_TWO_NODE_RC_V1: constant effective
  resistances/capacitances, explicit oil/winding heat rates, a declared ambient
  boundary, explicit seeds and previous-sample hold over event-time intervals.
  Its temperatures are uniform node proxies, not measured internal maxima.
- Independent verification of synthetic homogeneous steady 2D conduction with
  explicit conductivity, thickness, distributed source and full Dirichlet edges.
  FEM outputs are SIMULATED_REFERENCE; the rectangle is not a transformer model.
- Inspection of independent component statuses, units, lineage, version and
  evidence references through the frozen physics result contract.

## Excluded claims and prerequisites

Operational transformer top-oil/hot-spot estimation is unsupported by this
two-node implementation. Real equipment specifications, sensor units/locations,
electrical side/RMS/scaling, loss test/reference-temperature data, thermal
applicability and independently measured reference histories are missing.
No fictional fleet value or existing empirical coefficient fills those gaps.

IEEE C57.91-2025 and IEC 60076-7:2018 catalog metadata was checked in prior
phases, but full applicable thermal/ageing clauses and exact formula locators
remain **UNVERIFIED**. No standards compliance is asserted. Verified general
technical locators and project derivations are separated in
[physics_references.md](physics_references.md).

Insulation ageing remains unavailable: no supported operational hot-spot history,
verified law/constants, liquid/insulation applicability or complete exposure
window is established. There is no real RUL or failure-probability result.
Preserved legacy synthetic first-passage RUL is a separate fictional scenario,
not real transformer service life.

The RC uniform node and FEM spatial maximum have no evidenced common target,
geometry/material reduction, heat partition, equivalent boundary or common
time interpretation. Cross-model difference/errors stay null with
INCOMPATIBLE_COMPARISON. A unit conversion cannot remove that incompatibility.
FEM is steady only: no transient storage, fluid flow, cooling law, anisotropy,
temperature-dependent materials or real winding geometry is validated.

## Evidence and failure behavior

The independent analytic RC reference/energy balance and manufactured FEM
solution/mesh refinement pass their predeclared numerical criteria. These
establish numerical verification, not model-to-model agreement or field accuracy.
Regression snapshots are records of synthetic computation, not independent truth.
Relative rise errors are unavailable at/below the declared synthetic 0.001 K
denominator floor; no relative Celsius error is reported.

Unknown/missing/invalid/stale measurements, absent policies or version/evidence
identities, gaps, wrong reset seeds, corrupt checkpoints and numerical errors
withhold affected values with independent reasons. No zero-fill, guessed units,
implicit backfill or older READY fallback is permitted. Refresh/loading/errors
and asset changes remove prior physics values in the frontend. Newer telemetry
than the selected physics event requires Refresh; the panel is a read snapshot.

Publication checks typed supplied records and digests; it does not authenticate
equipment documents. Digests are not signatures. No uncertainty propagation,
field calibration or production throughput/latency guarantee is established.
Retention is bounded per asset; immutable identities persist. Access control,
backups, total fleet/storage sizing and rollout remain operator responsibilities.

Strict fitted artifacts are absent; backend regressions, baseline lint/format
failures, missing pymodbus and the unexecuted dedicated broker check remain.
The current retained backend image lacks the physics route. Current-source HTTP
and browser checks pass for unavailable/error responses on a disposable database;
no eligible successful equipment response or clean production deployment was
demonstrated. See [deployment boundaries](../README.md) before any later rollout.
