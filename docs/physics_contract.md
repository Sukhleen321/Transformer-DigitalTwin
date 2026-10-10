# Physics contract — version 1.0.0 (Phase 1)

Audit date: 10 October 2026 (Asia/Calcutta). Baseline revision: `3bf835c7e373565300e395ddaca4007773ef542e`, branch `main`.

The sole governing specification is [Transformer_DigitalTwin_Physics_First_Implementation_Plan.md](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md), confirmed by the user after Phase 0. This document freezes the interfaces for subsequent phases; it is not a second implementation plan. The existing-interface inventory below records the Phase 0 baseline. The normative new-physics sections apply to future modules, not to running APIs today. No thermal estimator, ageing law or FEM solver is implemented by Phase 1.

## Authority and compatibility

Preserve [dataschema.md](../dataschema.md), [mlcontract.md](../mlcontract.md), and the additive [1.1.0 contract](contracts/hackathon-v1.1.md). Use the actual Python schemas and [golden fixtures](../tests/fixtures/hackathon/README.md) to resolve implementation details. Historical documents sometimes describe already implemented routes as proposed, or refer to absent fitted artifacts; those statements are not current runtime evidence.

Existing telemetry is flat canonical JSON. `schema_version` accepts `1.0.0` and `1.1.0`, defaulting to `1.0.0`; optional extensions do not authorize changing existing field meanings. Wire, feature, model, parameter, preprocessing and checkpoint versions are separate identities. Package version `0.1.0` is not the fitted model version.

Sources: [TelemetryIn](../backend/app/schemas/telemetry.py), [Acquisition and metadata](../backend/app/schemas/hackathon.py), [asset configuration](../backend/app/schemas/transformer.py), [common validators](../backend/app/schemas/common.py), [analytics](../backend/app/schemas/analytics.py).

## Existing telemetry input

`transformer_id` is a nonempty string of at most 128 characters, without surrounding whitespace. `timestamp` is an aware ISO timestamp, accepted at up to microsecond precision and normalized to UTC. Source event time is distinct from server `received_at`, receipt commit time, publication time and browser poll time. `received_at` is output-only. Numeric measurements accept finite JSON numbers/null, rejecting numeric strings, booleans and non-finite values. Omitted measurements become null. Extra and excluded raw fields are rejected.

| Existing field(s) | Contract unit / semantics | Current validation and unresolved source evidence |
|---|---|---|
| `phase_voltage_l1`, `phase_voltage_l2`, `phase_voltage_l3` | V | Finite/null; no generic magnitude bounds. Phase-neutral versus line-line and HV/LV must come from source evidence; never infer a sqrt(3) conversion. |
| `current_l1`, `current_l2`, `current_l3`, `neutral_current` | A | Finite/null; no generic magnitude/sign bounds. RMS/line/phase interpretation and CT scaling need source evidence. |
| `oil_temperature` | `DEG_C`, `SOURCE_UNIT`, or unknown evidence | Finite/null; public OTI unit and sensor location remain unverified. Not automatically top-oil or hot-spot. |
| `winding_temperature` | `STATUS` or `SOURCE_UNIT` | Finite/null; public WTI semantics unresolved. Verified/synthetic `DEG_C` is **not** accepted for this field by current acquisition validation. A future verified hot-spot sensor requires an explicit contract decision. |
| `ambient_temperature` | `DEG_C`, `SOURCE_UNIT`, or unknown evidence | Finite/null; source ATI unit/location unresolved. |
| `oil_level` | `percent`, `SOURCE_UNIT`, or unknown evidence | Finite/null; public OLI scale/reference unresolved. Percent is a declared synthetic convention, not proof about real sensors. |
| `oil_temp_alarm`, `oil_temp_trip`, `magnetic_oil_gauge_alarm` | `STATUS` | Nullable integer 0/1 output; boolean input normalizes to integer. Float 1.0 and strings are invalid. Contact polarity/applicability need evidence. |
| `active_power_total` | kW | Finite/null, sign retained. Import/export sign, instantaneous versus interval average and meter boundary need evidence. |
| `apparent_power_total` | kVA | Finite/null. Rating and measurement side must be compatible before loading is eligible. |
| `reactive_power_total` | kVAr | Finite/null, source sign convention unresolved for real data. |
| `energy_kwh` | kWh | Finite/null. Name alone does not establish cumulative/net/import/export/reset/rollover semantics. |
| `power_factor_l1`, `power_factor_l2`, `power_factor_l3` | `1` or `dimensionless` | Finite/null in [-1, 1]; sign convention requires source evidence. |

These are 21 measurement fields. Backend completeness is the fraction of non-null measurements; it is not unit validity or physical accuracy. Its seven critical fields are oil temperature, three currents and three voltages. The current ML overall gate instead returns `INSUFFICIENT_DATA` when at least two of oil temperature/three currents are missing. Neither gate alone establishes physics eligibility.

`source_name` and `scenario_id` are optional metadata, not measurements. `VL12`, `VL23`, `VL31` and other dataset-specific columns must remain outside downstream canonical interfaces. The ML adapter owns raw-column translation. Public-dataset units listed in repository documents are intended contract units, not independently verified source certificates.

## Acquisition and parameter provenance

When `acquisition` exists it requires maps covering all 21 measurements: `field_units` and `field_verification`. Existing verification labels are `VERIFIED`, `UNVERIFIED`, `SYNTHETIC`; source labels are `LIVE`, `SIMULATED`, `REPLAYED`, with `origin_kind=LIVE|SIMULATED|UNKNOWN`. Source label does not establish measurement verification. Absent acquisition means unknown provenance, even if a flat source name says simulator.

Preserve `origin_transformer_id`, `replay_run_id`, `gateway_id`, `map_version`, `snapshot_id`, `sequence`, `measurement_side`, `timestamp_origin`, `timezone_status`, and `expected_interval_seconds`. Replay requires a separate registered destination and lineage. Unknown timezone must be staged. A deliberate replay timezone assumption must be declared; synthetic UTC declarations must retain synthetic origin. MQTT PUBACK is not a durable SQL receipt.

Existing configuration metadata is `{version, status, field_metadata}`. A leaf entry is `{unit, verification, provenance, evidence_reference, effective_at}`; configuration verification uses `VERIFIED`, `UNVERIFIED`, `SYNTHETIC_CONFIG`. Verified leaves require evidence references. Populated configuration leaves under metadata require their own entries; aggregate status cannot override missing leaf evidence.

Every new physical parameter must additionally document: value/null, symbol and meaning, unit and explicit conversion, source title/edition/section/table/equation or equipment record, applicable transformer/liquid/insulation/cooling envelope, calibration method if empirical, effective time and version, uncertainty if supported, valid range, and missing/default policy. No operational physical-parameter default is approved. A synthetic case may declare a fictional parameter with a reproducible case ID, but it must remain ineligible as real equipment evidence.

## Existing equipment configuration

| Existing parameter | Unit | Availability / applicability |
|---|---|---|
| `rated_power_kva` | kVA | Nullable; no backend rating default. |
| `rated_voltage_hv`, `rated_voltage_lv` | V when new configuration evidence exists | Legacy V/kV ambiguity must not be silently converted. |
| `rated_current_a` | A | Nullable; rated line current on declared side needs evidence. |
| `rated_frequency_hz` | Hz | Nullable, positive when populated. |
| `impedance_percent` | percent | Nullable, positive; base/reference needed. |
| `cooling_class`, `oil_type`, `insulation_type`, `vector_group` | Named category | Nullable; actual equipment applicability unknown. |
| `measurement_side` | HV/LV/UNKNOWN | No inferred side. |
| `ct_ratio`, `pt_ratio` | primary/secondary A or V | Positive values with evidence; do not apply scaling twice. |
| `temperature_rise_limits.top_oil_k`, `.winding_k`, `.hot_spot_k` | K rise | Nullable positive limits; reference and applicability required. Limits are not measured temperatures. |
| `loss_parameters.no_load_kw`, `.rated_load_kw` | kW | Nullable nonnegative; test/reference and loading/cooling applicability required. |
| `loss_parameters.reference_temperature_deg_c` | °C | Nullable; no reference temperature invented. |

`AssetConfig.calculate_loading` produces `100*S/S_r` (%) and `S/S_r` (dimensionless) only with evidence-compatible kVA, eligible rating and matching HV/LV side. Synthetic rating is eligible only for simulated origin. A positive legacy rating alone is insufficient.

The shared operational fleet declares **fictional** 30 kVA, 400 V LV line-line, approximately 43.30127 A, 5-second samples for ten simulated assets. These are not real nameplates or defaults for the physics estimator. The standalone synthetic generator has separate fictional compatibility defaults (500 kVA, 415 V). See [fleet](../simulator/config/operational-fleet.json) and [generator](../simulator/simulator/generator.py).

## Existing calculated outputs and thermal behavior

`thermal_model_temperature` estimates the oil indicator using an empirical first-order model, not winding hot-spot. `thermal_residual` is observed oil indicator minus that model value; its unit must match both operands. `thermal_state` is nullable and assessed only against configured warning/critical limits in the thermal module. A configured threshold's name does not independently verify its source.

From [thermal_twin.py](../ml/thermal/thermal_twin.py):

```text
J(t) = (I1(t)^2 + I2(t)^2 + I3(t)^2) / 3
u(t) = b0 + bA*A(t) + bJ*J(t)
T_hat(t) = u(t-1) + (T_hat(t-1) - u(t-1))*exp(-dt_hours/tau_hours)
r(t) = oil_temperature(t) - T_hat(t)
warmup_hours = -tau_hours*ln(warmup_epsilon)
```

| Current coded parameter | Value | Interpretation / provenance limit |
|---|---|---|
| `b0` | -2.1073 | Empirical output-unit offset; independent calibration provenance unavailable here. |
| `bA` | 1.1284 | Output-unit / ambient-source-unit; dimensionless only if compatible temperature scales. |
| `bJ` | 8.065e-5 | Output-unit/A² only if J is verified current squared. Not a resistance or loss coefficient. |
| `tau_hours` | 0.240 h | Empirical time constant, not verified winding/oil equipment constant. |
| `continuity_gap_hours` | 0.5 h | Existing analytical continuity policy. |
| `warmup_epsilon` | 0.05 | Dimensionless warm-up policy; approximately 0.719 h using coded tau. |
| `parameter_version` | `1.0.0` | Coded identity, distinct from physical verification. |
| mode / unit | `PUBLIC_EMPIRICAL` / `SOURCE_UNVERIFIED` | No conversion to °C. |
| warning / critical temperatures | null / null | No default assessed thermal state. |

Initial valid oil observation initializes state and is not independently predicted; its residual is suppressed. Previous forcing is held across each elapsed interval. Residuals remain suppressed until warm-up completes. A gap greater than 0.5 h resets/reinitializes; nonpositive elapsed time raises an error. Missing present forcing prevents next-step integration, although the current step may still use prior forcing. Missing current oil can coexist with an integrated prediction but cannot supply a residual. Infinite inputs raise errors. WTI is excluded.

Audit concern: `compute_current_forcing` accepts precomputed `J`, or falls back to `active_power_demand` when current columns are absent. That fallback has different dimensions; it must not be carried into a physically interpreted current-squared model without a separate specification/calibration. `STANDARDS_INSPIRED_ELIGIBLE` is a mode name using the same implementation, not evidence of a standards-derived hot-spot solver.

[Calibration code](../ml/thermal/calibration.py) fits b0/bA/bJ/tau with L-BFGS-B and Huber delta 1.5. Initial guess is [-2, 1.1, 1e-4, 0.5]; bounds are [-10,10], [0.01,3], [0,0.01], [0.05,5] respectively. Candidate training runs require at least 10 points, gap at most 0.5 h, clear oil alarm/trip, oil in (0,100) and ambient in (0,60), all in source units. Chronological cuts are 2019-11-23 11:45 and 2020-02-13 11:15. These are empirical filtering/optimization choices, not equipment thermal limits. The expected fitted release and training evidence under `data/processed` are absent in this checkout; do not claim reproduced fitted coefficients or physical accuracy.

Existing health/anomaly/maintenance outputs are condition heuristics or research analytics. `health_index` is [0,100], `anomaly_score` [0,1], `anomaly_flag` boolean/null, loading %, and `maintenance_priority=NORMAL|WATCH|PLAN|URGENT`. Fault-risk/confidence outputs are gated by release evidence; none establish real failure probability. Current RUL is fictional first passage or operational eligibility assessment. `equivalent_ageing_hours` remains null in the current operational path; there is no implemented physical ageing or FEM solver identified by this audit.

## Normative Phase 1 interface and compatibility boundary

Contract identity: `physics_contract_version=1.0.0`. The [result JSON Schema](contracts/physics-result-v1.schema.json) fixes names, types, units, labels and null/status rules. The prose also defines eligibility and cross-field invariants that JSON Schema alone cannot establish. The [unit registry](contracts/physics-units-v1.json) and [contract checks](../tests/fixtures/physics/validate.py) are normative conversion vectors and structural checks, not production calculation code.

Future modules exchange an immutable normalized input snapshot and a result envelope described below. Phase 5 exposes the envelope through the separate read resource, `GET /api/v1/transformers/{transformer_id}/physics`, using bounded event-time selection. Its implemented persistence and read semantics are documented in [physics_integration.md](physics_integration.md). It avoids extending current strict telemetry/analytics schemas. Existing latest/history/ML payloads and status enums retain their current meanings. Do not put new fields into legacy `MLResultIn` or require old clients to understand new statuses.

No existing `thermal_model_temperature`, `winding_temperature`, RUL or energy field is repurposed. The new envelope's `equivalent_ageing_hours` uses the existing name and unit for a supported integration over its stated coverage window; it does not populate the legacy eligibility-only field until Phase 5 explicitly integrates it.

### Input snapshot

The snapshot has `transformer_id`, `timestamp` (source event time), `evaluated_at` (server calculation time), `evaluation_time` (event-time freshness reference), `context=OPERATIONAL|CONTROLLED_SIMULATION`, `lineage`, `versions`, and the five maps below. Live evaluation uses a trusted current time; controlled/replayed runs supply their explicit event-time reference. Replay speed never changes a physical timestep.

Every numeric leaf uses a quantity record:

| Member | Required meaning |
|---|---|
| `value` | Finite number/null; booleans and numeric strings rejected. Null propagates as unavailable, never zero. |
| `unit`, `quantity_kind` | Registry token and physical meaning (absolute temperature, temperature difference, apparent power, etc.). Unknown source units stay outside the eligible normalized snapshot. |
| `verification` | `VERIFIED|UNVERIFIED|SYNTHETIC`; adapt existing `SYNTHETIC_CONFIG` without losing the original label. |
| `provenance` | `evidence_reference`, source/case ID, original field/unit/value, conversion ID or identity, and applicability. Verified/synthetic eligible leaves require a retrievable record/case reference. Original null/invalid values are recorded in diagnostics, never normalized into a number. |
| `valid_range` | Nullable evidenced min/max in the leaf's unit, with source; null means no evidenced range, not unlimited model applicability. |
| `uncertainty` | Null unless supported; if populated, numeric value, unit, coverage/interpretation and evidence. No automatic error bars. |
| `effective_at` | UTC configuration effective time or event time for an observation. |

Non-numeric categories use explicit value/null and evidence records. Configuration objects have immutable version IDs. Do not inherit unit verification from a filename, field name, aggregate status or demo label.

| Map / input category | Fields and normalized units | Eligibility / source required |
|---|---|---|
| `observed` | Existing voltages V; currents A; power factors 1; active W, apparent VA, reactive var, energy J; oil/ambient absolute temperature K; oil level 1 only with verified percent convention; contact values STATUS. | Preserve all 21 canonical names at the adapter boundary. Model-specific required subset is declared, not the legacy completeness score. Voltage phase reference, side, RMS basis, scaling, sign, sensor target/location and timestamps need source evidence. WTI contact is never normalized as temperature. |
| `equipment` | Existing nameplate leaves with kVA→VA, kW→W, DEG_C→K, percent→1; rated current A, voltage V, frequency Hz; rises K; CT/PT primary/secondary A/V. Type, side, connection, fluid, insulation, cooling are categories. | Actual nameplate, test reports and sensor mapping. Rise **limits** are not rated model rises; do not substitute them. A loading ratio requires compatible measured/rated quantities and side. No inferred rating or sqrt(3) conversion. |
| `model_parameters` | Candidate `rated_top_oil_rise`, `rated_hot_spot_gradient` K; `oil_time_constant`, `winding_time_constant` s; `loss_ratio`, `oil_exponent`, `winding_exponent`, `hot_spot_factor` 1; optional `ageing_reference_temperature` K and `ageing_activation_temperature` K if the selected law uses them. | Candidate names define quantities, not an approved formula or mandatory parameter set. Selected model manifest declares exact requirements, ranges and equation/source IDs. Other law-specific parameters require registered meaning/unit/evidence before use. None has a default value. Existing empirical coefficients are not physical substitutes. |
| `environment` | Ambient temperature K; optional boundary temperature K, surface heat-transfer coefficient W/(m²·K), imposed heat flux W/m²; cooling-mode schedule category with UTC event times. | Boundary location, loading/cooling applicability, and stated schedule/hold assumptions. Do not assume convection, radiation, uniform ambient or perfect mixing without a declared model/case. |
| `simulation` | Geometry lengths and out-of-plane thickness m; conductivity W/(m·K), density kg/m³, specific heat J/(kg·K), volumetric heat source W/m³, initial temperature K, duration/timestep s, mesh length m, solver relative tolerance 1; iteration count integer/count. | Optional and isolated from live calculation. Case ID, dimensional interpretation, regions, source distribution, boundary types, material references, solver/version and numerical-verification record required. Absolute solver tolerances carry their residual's unit. No transformer material defaults. |

The supported model manifest declares its required input paths, target definition/location, equation classification and source locators, applicability predicates, initialization policy, history requirement, valid ranges and output names. An unverified equation may be recorded but cannot produce physics READY. Missing manifests/parameters make the affected component `INVALID_CONFIGURATION`. Unknown sensor semantics/units make it `INSUFFICIENT_DATA`. A fully declared synthetic case can run only in controlled simulation; its result retains synthetic origin and is not operational equipment evidence.

### Normalized units and explicit conversions

Internal units are s, m, A, V, Hz, W, VA, var, J, K and 1, plus the material/boundary units above. W, VA and var retain different quantity kinds even where their dimensions coincide. `DEG_C` is the existing API token for °C; K absolute and K difference are distinct quantity kinds. STATUS remains a contact code, never a scalar thermal input.

The [unit registry](contracts/physics-units-v1.json) lists the only approved non-identity conversions. For each rule, `normalized = source * scale + offset`; reverse export is `source = (normalized - offset) / scale`. Scale/offset are exact unit definitions, not fitted physical parameters.

| Conversion | Formula / constraint |
|---|---|
| Absolute DEG_C → K | Add 273.15; values below absolute zero are invalid. |
| Temperature difference DEG_C → K | Identity; **no** 273.15 offset. Export temperature differences as K. |
| kW → W; kVA → VA; kVAr → var | Multiply by 1000; preserve quantity kind and supported sign. |
| kWh → J | Multiply by 3,600,000; meter/reset semantics remain separately required. |
| h → s | Multiply by 3600; time constants must be positive, elapsed dt must be positive. |
| percent → 1 | Divide by 100. A percentage reading is not automatically a loading fraction or oil-volume fraction. |
| mm → m | Divide by 1000, only when the geometry source explicitly states mm. |

Identity leaves still record their original unit and quantity kind. Arbitrary unit aliases, V/kV guessing, STATUS→DEG_C, SOURCE_UNIT→K, active-power→current-squared, applying CT/PT scaling twice, and phase/line conversion without a declared electrical mapping are forbidden. Conversion does not verify the source unit or equation applicability. An unverified leaf remains ineligible even if its unit string looks familiar. Conversion fixtures test exact vectors, inverse conversion, temperature-difference handling and rejection of unsupported/missing/nonfinite inputs; production conversion code and its module tests belong to Phase 2.

### Result envelope and output categories

Required envelope fields: `physics_contract_version`, `transformer_id`, `timestamp` (nullable if no observation), `evaluated_at`, `context`, `lineage`, `versions`, `components`. No aggregate READY masks a partial failure. All ten component keys are present, with null values/status/reasons when unavailable.

`lineage` preserves source kind/origin including UNKNOWN, acquisition reference (telemetry/snapshot/map/source identity), replay run/origin asset and evidence references. It carries `input_verification=VERIFIED|UNVERIFIED|SYNTHETIC|MIXED|UNKNOWN`. No synthetic input or configuration is permitted in OPERATIONAL READY results. In CONTROLLED_SIMULATION, calculations remain CALCULATED_ESTIMATE and retain SIMULATED origin plus a case ID. FEM remains SIMULATED_REFERENCE even when using verified real material inputs.

| Component key | Public unit | Result kind / meaning |
|---|---|---|
| `measured_oil_temperature` | DEG_C | MEASURED_TELEMETRY: eligible continuous oil sensor reading, with its actual sensor target disclosed. Does not imply top-oil. Unknown unit: null here; legacy reading preserved. |
| `top_oil_temperature` | DEG_C | CALCULATED_ESTIMATE: model-defined top-oil target. No existing oil indicator silently becomes a top-oil measurement. |
| `hot_spot_temperature` | DEG_C | CALCULATED_ESTIMATE: model-defined winding hot-spot target, always labelled “estimate”. |
| `top_oil_rise` | K | CALCULATED_ESTIMATE: modeled top-oil minus applicable ambient. |
| `winding_hot_spot_gradient` | K | CALCULATED_ESTIMATE: model-defined hot-spot minus its oil-reference temperature. |
| `total_loss` | W | CALCULATED_ESTIMATE: only supported electrical-loss approximation with stated boundary/reference temperature. |
| `ageing_acceleration_factor` | 1 | CALCULATED_ESTIMATE: selected law's instantaneous factor, not failure probability. |
| `equivalent_ageing_hours` | h | CALCULATED_ESTIMATE: integral over declared supported coverage, not total consumed life or RUL. |
| `fem_hot_spot_temperature` | DEG_C | SIMULATED_REFERENCE: reproducible numerical reference at a matching target/location. Verification and mesh records must accompany READY. |
| `hot_spot_difference` | K | CALCULATED_ESTIMATE: estimator minus FEM, signed temperature difference for an eligible comparison. No relative Celsius error. |

Each component contains `value`, fixed `unit` and `result_kind`, `status`, `reasons`, `missing_inputs`, `warnings`, `assumptions`, `coverage`, `provenance`. Reasons/warnings use machine-readable codes plus messages/affected paths. Assumptions identify their reference; they never silently waive required real data. Every emitted numeric output has its unit and provenance, even when null. Diagnostic numbers/thresholds, if added later, must use quantity records rather than untyped numbers in messages.

Component provenance requires `model_id`, `equation_ids`, `input_paths`, `evidence_references`, `case_id`, `comparison_id`, `numerical_verification_reference`, `mesh_convergence_reference` (nullable IDs where not applicable). Evidence-reference lists cannot be empty for READY. Derived results include model/equation and input references; measured results refer to the source observation, not a fitted equation. FEM READY additionally requires a case ID and independent numerical-verification/mesh-convergence references. Comparison READY requires a declared comparison record and both operands READY.

A comparison record specifies the shared target definition/location, time/window, side/loading/loss basis, geometry abstraction, material/cooling assumptions, boundary/source/initial conditions and unit conversions. Incompatible or unavailable operands produce null with `INCOMPATIBLE_COMPARISON` or an operand reason. Error aggregation, normalization scale and near-zero denominator policy are configurable but unapproved until Phase 4; relative metrics remain unavailable in v1. Numerical verification, model-to-model comparison and real-world validation are separate evidence types.

Synthetic readings are not measured equipment temperatures. In controlled synthetic cases, measured_oil_temperature stays null with SYNTHETIC_NOT_MEASURED; the synthetic input remains in lineage/input evidence and may support explicitly simulated-context estimates.

### Status, missing data and transport errors

Preserve native legacy enums without additions. Physics components use:

| Status | Exact behavior |
|---|---|
| READY | Required evidence, configuration, model applicability, measurements and state/coverage pass for **this** output. Finite value and evidence required. Does not assert field accuracy. |
| INITIALIZING | Eligible inputs/configuration but cold start, warm-up, gap/configuration reset or incomplete initial state. Value null; provisional state may be logged internally but not exported as an estimate or used for ageing. |
| INSUFFICIENT_DATA | Required observation absent, invalid, stale, unknown unit/semantics, unsupported timestamp or history/coverage inadequate. Value null; list affected input paths and reason. |
| INVALID_CONFIGURATION | Required configuration/model absent, invalid, unverified, incompatible or outside verified applicability. Value null; list affected paths/evidence requirements. Optional unconfigured FEM/ageing reports this status with MODEL_NOT_CONFIGURED, not a crash. |
| MODEL_ERROR | Attempted eligible computation failed, diverged or produced nonfinite output. Value null; sanitized diagnostic ID/reason. Never return the last value as a new READY result. |

Evaluate all causes and report them. Deterministic selection: INVALID_CONFIGURATION first, then INSUFFICIENT_DATA, then INITIALIZING; attempt computation only after these clear, then MODEL_ERROR on failure, otherwise READY. Independently valid measured output may be READY while estimates are unavailable. Downstream ageing never accepts INITIALIZING, stale, failed or synthetic-operational thermal inputs.

Native thermal READY is not sufficient for physics READY; all eligibility gates are additional. Native warm-up/gap-reset maps to INITIALIZING only with eligible physics inputs/configuration; unknown/uninitialized or missing forcing maps to its actual missing-input/initialization cause. The empirical model's SOURCE_UNVERIFIED prediction is not a physics hot-spot.

Omitted required transport members are malformed (future API 422). Required members explicitly null are valid unavailable data. Unknown asset 404; semantic source identity conflict 409; unexpected transport failure 500 using the existing error envelope and X-Request-ID. Successful reads/accepted ingestion may contain unavailable analytics; HTTP success does not imply physics success.

Repository clarification: [ingestion_service.py](../backend/app/services/ingestion_service.py) retains accepted late telemetry with `REJECTED_LATE_OBSERVATION` and `forward_state_advanced=false`, without advancing live analytics/checkpoints. This is the compatibility rule for the current implementation; historical generic “late=409” text is not a reason to change it. Do not discard observations or retrospectively recompute state in Phase 1.

### Time, ranges, coverage and state

All event/coverage/configuration times are timezone-aware UTC; input offsets normalize explicitly to UTC. Event time drives dt, not received_at or replay wall time. Unknown timezone is ineligible; declared synthetic UTC and deliberate replay assumptions retain their labels. OPERATIONAL READY requires a verified event-time interpretation; any accepted legacy timezone assumption remains visible and ineligible for this path.

Each selected model/configuration must declare `max_sample_age_seconds` and `max_gap_seconds` (positive finite s), `initialization_policy` (named sourced policy), `required_history_seconds` (nonnegative finite s), and a `range_policy_reference`. These are application/model policy, not invented transformer constants. No default cadence, 10-second UI timeout, 0.5-hour empirical gap or one-hour buffer is inherited. Missing required policy is INVALID_CONFIGURATION. A model may explicitly use required_history_seconds=0 for an evidenced instantaneous method.

A sample is stale when evaluation_time minus event time exceeds max_sample_age_seconds (equal is allowed). A future event beyond evaluation_time is ineligible pending an explicitly evidenced clock policy; v1 allows no silent skew correction. A gap exceeding max_gap_seconds resets dynamic state. Nonpositive dt never integrates: exact retry preserves existing state, conflict follows current ingestion identity rules, late data cannot advance forward state.

A required observation outside its evidenced/model range remains stored under legacy ingestion rules but is null/ineligible for the new calculation with OUT_OF_RANGE; never clamp/extrapolate silently. Invalid parameters yield INVALID_CONFIGURATION. Unrecognized ranges and unknown equipment applicability do not become permissive defaults.

Coverage: `start`, `end` (both UTC/null); `covered_seconds`, `expected_seconds` (s/null); `fraction` (1/null); `gap_count` (integer/count); `missing_fields` (paths). Expected/covered durations refer to declared intervals, not sample counts. Require 0 ≤ covered ≤ expected; fraction=covered/expected when expected>0; fraction null at zero/unknown duration. An instantaneous result has start=end, durations zero and fraction null. Absent history uses null times/durations/fraction, not fabricated zero exposure. Gap_count counts detected gaps; unknown history has no asserted continuous coverage.

No zero filling, interpolation or extrapolation is implicit. If a later model uses interval holding/interpolation, declare method, range, maximum gap and coverage effect in its manifest and assumptions. Initial state must come from an eligible target measurement or an explicit sourced initialization policy; do not initialize from 0, ambient or steady state by convention. Changes to contract/model/parameters/equipment/time-unit mapping/applicability reset dynamic state at the configuration effective time; mixed-version history must be split or explicitly recomputed, never spliced silently.

Ageing requires an applicable sourced law, READY hot-spot trajectory, supported timestamps/interval integration and coverage adequate for the requested window. Report the requested window's unavailable status if required intervals are missing; do not call a partial integral a full-window exposure. No normal-life-hour budget, prior ageing or future duty is supplied here. Existing one-hour/4096-row history is not proof of ageing eligibility.

### Version and evidence identities

Envelope `versions` contains `model_version`, `parameter_version`, `configuration_version`, `preprocessing_version`, `equation_registry_version` (nonempty immutable IDs/null). A derived READY component requires all five IDs. Measured READY requires preprocessing_version; absent model IDs are acceptable for measured-only output. FEM case/solver identity is referenced from component provenance.

Contract version governs names/types/semantics; a breaking change increments its major version. Model identity changes with equations, required-input definition, state evolution or applicability. Parameter identity changes with any value, source, uncertainty, range or default policy; configuration identity with equipment/policy/effective time. Never overwrite a released identity with different content. Evidence records retain title/edition/locator/URL or equipment record ID, retrieval date and content digest where available. Phase 5 encodes bounded finite JSON with sorted keys and compact separators and records SHA-256 content digests; versions resolve to immutable asset-scoped records before READY. No standards claim follows from a version or model-mode name.

## Phase 2 model binding (additive; result contract remains 1.0.0)

The isolated implementation is [ml/physics](../ml/physics/__init__.py). Source
verification and equation status are recorded in [physics_references.md](physics_references.md).
This release implements the separately identified PROJECT_TWO_NODE_RC_V1
simplified heat-balance model for CONTROLLED_SIMULATION only. Operational
thermal requests and selected IEC/IEEE models remain unavailable without
supported equations/equipment evidence. No legacy oil-estimator coefficients
are reused, and no standard hot-spot or ageing law is inferred.

Additional registered model quantities are oil_thermal_resistance and
winding_thermal_resistance (K/W, positive), oil_thermal_capacitance and
winding_thermal_capacitance (J/K, positive), and minimum_temperature /
maximum_temperature (absolute K, explicit model envelope). All require
quantity/evidence records; none has a default. K/W and J/K are additive
identity-unit registrations, not new source-unit guesses or conversions.

Controlled forcing uses environment.ambient_temperature (absolute K),
simulation.oil_heat_input and simulation.winding_heat_input (W, heat_rate),
with explicit ranges, timestamps and case references. Initialization uses
simulation.initial_oil_temperature and initial_winding_temperature (absolute
K) at the reset event. These are explicit initial conditions, not invented
sensor readings. Previous forcing drives each elapsed interval; a missing or
invalid required observation breaks continuity and withholds estimates. Current
temperature observations are never assimilated as hidden winding state.

An optional PROJECT_CURRENT_SQUARED_LOSS_V1 approximation requires three
compatible RMS line currents (A), equipment.rated_current_a (A), model
parameters no_load_loss and rated_load_loss (W, active_power), and
loss_reference_temperature (absolute K), plus energized/side/basis evidence.
It does not infer a heat partition or silently feed the thermal nodes.

The typed [Snapshot records](../ml/physics/types.py) implement the five input
maps and evidence lookup. Model-selection and time-policy records are explicit;
numeric policy fields are quantity records with unit/evidence. Model version
1.0.0 and equation registry physics-equations-1.0.0 identify this implementation.
Parameter, equipment/policy and source-map identities remain caller-supplied
immutable records, checked within the estimator's owned process. Production
transport, persistent version/checkpoint storage and operational scheduling
are deferred. Unsupported uncertainty propagation is explicitly unavailable
rather than producing invented error bars. In the Phase 2 estimator envelope,
ageing and FEM remain null; the independent Phase 3 reference below does not
change that envelope.

See [physics_model.md](physics_model.md) for required inputs, state rules and
limitations, and [Phase 2 report](phase2_report.md) for actual verification.

## Phase 3 FEM binding (isolated numerical artifact; no API change)

The separate [ml/fem](../ml/fem/__init__.py) package implements homogeneous,
constant-conductivity, steady 2D conduction with fully prescribed boundary
temperatures. Its [synthetic benchmark specification](fem_reference.md) was
documented before coding. No real transformer material or geometry is inferred.
The case carries explicit SI quantity/evidence records and immutable content
digest; published scalar quantities have units and numerical/mesh provenance.
Spatial L2 temperature-error diagnostics use K*m and 2D H1 seminorm errors
use K; these are documented numerical norm units, not sensor conversions.

The CLI artifact is an independent numerical record, not the frozen ten-field
physics API envelope. It is always SIMULATED_REFERENCE with SIMULATED origin,
SYNTHETIC inputs and CONTROLLED_SIMULATION context. Only a passing manufactured
verification/refinement run publishes READY and a reference domain maximum.
Failed acceptance withholds that maximum (MODEL_ERROR/null), retaining mesh
diagnostics explicitly for review. Invalid cases are INVALID_CONFIGURATION.

The target is SYNTHETIC_RECTANGLE_DOMAIN_MAXIMUM, not an established transformer
winding hot spot. There is no compatible spatial mapping to the two-node model.
Consequently fem_hot_spot_temperature and hot_spot_difference remain unavailable
in the existing estimator result. Future comparison requires an explicit
compatible target/geometry/source/boundary/steady-state record; no comparison
or transport integration is implemented here. See [Phase 3 report](phase3_report.md).

## Phase 4 independent validation binding

The isolated [validation harness](../ml/validation/harness.py),
[explicit synthetic manifest](../ml/validation/cases_v1.json) and
[validation specification](validation_reference.md) verify existing models
independently. Their CLI artifact is a numerical-verification record, not a
new public API envelope. No production equations, parameter defaults, unit
registry, result schema, database or transport behavior change.

There is no evidenced common target between the uniform two-node proxy and
the spatial FEM maximum. Target reduction, geometry/material-to-R/C mapping,
heat partition/distribution, boundary equivalence and a common time window
are absent. The harness's contract-shaped hot_spot_difference is
INVALID_CONFIGURATION with INCOMPATIBLE_COMPARISON and null value;
cross-model absolute/relative errors also remain null. Existing estimator
FEM/comparison components remain unavailable. A shared zero-heat equilibrium
does not establish a nontrivial model-to-model comparison.

Within-model analytical verification reports signed and absolute **K rises**
and dimensionless relative rise errors only for matching targets/semantics.
The denominator is the absolute analytical rise; at or below the explicit
0.001 K synthetic policy floor, relative error is INSUFFICIENT_DATA/null with
NEAR_ZERO_REFERENCE, while absolute error remains eligible. Unavailable,
invalid or unsourced operands cannot silently become zero metrics.

All outputs retain CONTROLLED_SIMULATION, SIMULATED and SYNTHETIC labels;
FEM temperatures remain SIMULATED_REFERENCE. PASS/FAIL refers to independent
checks with explicit unavailable comparison and FEM transient capabilities.
It does not enable an operational transformer estimator, ageing, real-world
accuracy or standards compliance. See [Phase 4 report](phase4_report.md).

## Equation plan and verified source ledger

Sources checked 10 October 2026. This Phase 1 equation-selection ledger is retained under the canonical plan. The Phase 2 binding and [references](physics_references.md) above identify the implemented approximation and unverified standards paths. No thermal/ageing/FEM equation is approved from memory.

| Source ID | Verified source / locator | What is established; remaining work |
|---|---|---|
| SI-2026 | BIPM, *The International System of Units*, 9th edition (2019), English V4.01 June 2026; [official brochure](https://www.bipm.org/en/publications/si-brochure), [English PDF](https://www.bipm.org/documents/20126/41483022/SI-Brochure-9-EN.pdf). §2.3.1 p129; §2.3.4 Tables 4–5 pp134–135; §3 Table 7 p138; §4 Table 8 p140. | Verified absolute Celsius/kelvin relation, interval equality, derived units, kilo/milli prefixes and hours/seconds. kWh/J combines those definitions. VA/var are project quantity-preserving tokens; this is not a metering-semantics certificate. Percent normalization is the declared mathematical convention. |
| IEC-CATALOG-2018 | IEC, *Power transformers — Part 7: Loading guide for mineral-oil-immersed power transformers*, IEC 60076-7:2018, edition 2.0, published 2018-01-12; [official catalog](https://webstore.iec.ch/en/publication/34351). | Title/edition and mineral-oil scope verified. No full-text equation, clause, numeric constant or equipment applicability verified. Candidate reference only. |
| IEEE-CATALOG-2025 | IEEE, *IEEE Guide for Loading Mineral-Oil-Immersed Transformers and Step-Voltage Regulators*, C57.91-2025; [official catalog](https://standards.ieee.org/ieee/C57.91/7163/). | Active edition; approval 2025-09-10, publication 2026-03-05; supersedes 2011. Title/scope verified, full formula clauses not reviewed. Select applicable edition explicitly in Phase 2; do not silently apply 2011 equations to 2025. |
| REPO-EMPIRICAL | [thermal_twin.py](../ml/thermal/thermal_twin.py), [calibration.py](../ml/thermal/calibration.py), baseline revision above. | Existing empirical oil-indicator recurrence/coefficient inventory earlier in this document verified in code. Missing fitted provenance; not a standards hot-spot law. |
| REPO-LOSS | [loss.py](../ml/energy/loss.py), [analytics_resources.py](../backend/app/services/analytics_resources.py) and [asset_config.py](../ml/pipeline/asset_config.py). | Existing loading and approximate no-load plus current-squared load-loss logic; reference temperature/loss boundary applicability must be evidenced before physical reuse. Not a verified total electromechanical loss model. |

| Planned equation family | Classification and required verification | Required inputs / output gate |
|---|---|---|
| Loading and supported loss | Existing project approximation; dimensional ratio and loss assumptions reviewed against equipment/test references. No active power substituted for current squared. | Compatible side/RMS/rating; no-load/rated load-loss references and test temperature. Temperature correction requires its own supported law. Otherwise total_loss unavailable. |
| Dynamic oil / winding / hot-spot | Candidate standards-derived only **after** exact edition/section/equation and applicability review. A simplified or empirical alternative must use a distinct ID, source and limitation statement. | Selected manifest, rated rises/gradient, loss basis, time constants/exponents if used, ambient/load history, initialization/cooling envelope. Missing constants remain null. |
| Thermal ageing | Candidate standards-derived; exact insulation/liquid law, reference temperature, factors and interval integration to verify. Do not invent an Arrhenius constant or normal-life budget. | Supported hot-spot history and law applicability. Unavailable otherwise; no RUL/failure probability. |
| 2D heat conduction / FEM | Simplified numerical reference. Governing balance, material coefficients, dimensional/source interpretation and boundary terms require an authoritative technical reference before Phase 3 implementation. | Explicit geometry/properties/sources/boundaries/initial state; independent analytical/manufactured verification and mesh convergence. No material values supplied. |
| Comparison | Project comparison definition; signed same-target temperature difference fixed here. Aggregate/relative metric definitions belong to Phase 4 evidence. | Compatible READY operands and comparison record; numerical agreement is model-to-model evidence only. |

## Decision register — all unresolved questions by evidence owner

“Resolved” means the available evidence settles the interface, not that missing physical data exists. The identifiers preserve the Phase 0 D01–D12 lineage.

### 1. Answerable from the existing repository

| ID | Resolution / evidence | Remaining effect |
|---|---|---|
| D01 | RESOLVED by user instruction and current tree: sole canonical physics-first filename exists; former unified filename absent. | No competing plan created; historical Phase 0 filename note retained. |
| D11 | RESOLVED: independent v1 result envelope, separate future resource, per-component statuses, two-axis provenance; strict legacy schemas unchanged. Current WTI accepts STATUS/SOURCE_UNIT, not verified DEG_C. | Future measured hot-spot sensor needs a separately named/versioned observation; never relabel WTI. Phase 5 implements transport. |
| D03-repo | RESOLVED: existing allowed unit/verification tokens, null/type rules, UTC handling and 21 fields are documented. Acquisition evidence does not supply real sensor documents. | Observed source uncertainties continue in category 3. |
| D08-repo | RESOLVED: current empirical gap/warm-up, history cap, late observation and retry/state behavior; new physics gates do not inherit them. | Preserve behavior and retain nulls while policy absent. |
| D04-repo | RESOLVED: fictional fleet/standalone defaults, existing configuration leaf metadata and loading gate verified. | No real nameplate inferred. |
| D09-repo | RESOLVED: current ageing field is unavailable; fictional RUL and empirical oil prediction are not validated physics outputs. | No migration/recalibration performed. |

### 2. Requiring authoritative standards or technical references

| ID | Open decision / required evidence | Safe consequence |
|---|---|---|
| D06 | Obtain/review applicable IEC/IEEE full equation clauses and edition applicability; verify variable definitions, initialization, cooling regimes, limits and source locators. Catalog identity/scope is resolved above. | Equation eligibility remains unverified, INVALID_CONFIGURATION/EQUATION_UNVERIFIED. |
| D05-source | Verify thermal-rise/gradient/time-constant/exponent/loss-ratio law and any parameter estimation/testing method. Separate standard recommendations from empirical fits. | No default constants. |
| D09-source | Verify liquid/insulation ageing law and integration, reference temperatures and factors; any life interpretation needs independent evidence. | Ageing unavailable; RUL not inferred. |
| D07-source | Select authoritative heat-conduction/FEM reference and analytical/manufactured verification problem; verify material/boundary constitutive laws if used. | No solver or transformer reference temperature produced. |

### 3. Requiring real transformer specifications or sensor documentation

| ID | Required input / evidence | Safe consequence |
|---|---|---|
| D02 | Transformer identity/type, fluid/insulation, cooling, construction/winding arrangement and operating envelope. | No operational model applicability assumed. |
| D03 | OTI/ATI/WTI units and continuous/contact semantics, sensor locations/calibration/ranges, contact polarity, oil-level reference, source timezone/clock/cadence. | Unknown/unverified observations ineligible, legacy display retained. |
| D04 | Rated power/voltage/current/frequency, HV/LV and line/phase/RMS basis, CT/PT scaling, meter sign/counter/reset/boundary semantics; test losses and reference temperatures. | No physical loading/loss defaults or inferred conversions. |
| D05-equipment | Rated top-oil and winding/hot-spot rises/gradients, tested thermal time constants/factors or admissible fitting data, cooling dependence and effective dates. | Estimator unavailable until selected model requirements met. |
| D07-equipment | Actual geometry/dimensions, materials/properties versus temperature, source distribution and boundary/cooling measurements if claiming equipment-specific FEM. | Controlled synthetic cases may be declared later; no real geometry/material inference. |
| D09-equipment | Supported hot-spot history, prior exposure and life/future-duty data if later proposing a life model. | Recent exposure cannot establish absolute age or RUL. |
| D10 | Independent internal-temperature reference measurements with traceable units/times/locations and uncertainty. | No real-world accuracy validation claim. |

### 4. Safely configurable or unavailable until later phases

| ID | Fixed contract behavior / deferred selection | Availability policy |
|---|---|---|
| D08-policy | Stale/gap/range/history/initialization policy fields, event-time dt and reset-on-version-change are fixed above; numeric thresholds/method are sourced configuration, not universal defaults. | Missing policy → INVALID_CONFIGURATION; missing/stale/out-of-range data → INSUFFICIENT_DATA. |
| D07-case | Optional 2D abstraction, synthetic verification geometry/properties, boundary case, mesh/solver tolerances and runtime/storage choice selected in Phase 3. | FEM unconfigured/null; later cases retain synthetic labels and reproducible case IDs. |
| D10-comparison | Metric aggregation/relative normalization, uncertainty treatment and comparison harness selected in Phase 4. | Only signed eligible temperature difference specified now; relative metric unavailable. |
| D11-integration | Phase 5 implements persistence, bounded endpoint selection and version-record/hash encoding. A separately named real hot-spot observation remains unsupported pending documented sources and a versioned input interface. | Frozen result interface; separate additive read resource and isolated storage tables. Strict legacy schemas unchanged. |
| D09-history | Longer historical retention and partial-window exposure products require an explicit supported request/window policy. | Full-window ageing withheld if coverage inadequate. |

### 5. Existing test failures and missing fitted artifacts unrelated to this contract

| ID | Baseline issue / evidence | Phase 1 disposition |
|---|---|---|
| D12-artifacts | 95 ML failures reference absent fitted release/parameter artifacts under data/processed; no authenticated release or fitting evidence supplied. | Not restored/fabricated; empirical provenance remains limited. |
| D12-environment | Raw backend collection shadowed by installed tests package; backend diagnostic needed source-path setup. Simulator pymodbus absent: 3 collection errors, narrowed run 2 failures/46 passes. | No dependency/package-layout repair. |
| D12-regressions | Backend diagnostic: 15 failed/735 passed/1 skipped. Includes reset/seed receipt FK failures, API-doc gap, replay/batch expectations, concurrent/bulk/duplicate/rollback/performance assertions, latest-state shape expectation. See exact cases in Phase 0 report. | Not relabelled as harmless or fixed; no claim that baseline became green. Real broker test still unexecuted. |
| D12-lint | Backend lint 173 errors, format 57 files; frontend lint 16 warnings at baseline. | No unrelated formatting/refactor. |

See [current architecture](architecture_current.md), [Phase 0 commands/results](phase0_report.md) and [Phase 1 verification/report](phase1_report.md). Phase 1 was reviewed and approved. Physical availability remains conditional on evidence; [Phase 2 results](phase2_report.md) describe the current restricted implementation and approval boundary.

## Phase 5 persistence binding (result contract remains 1.0.0)

The [integration boundary](physics_integration.md) implements immutable
publication, asset-owned transactional checkpoints and read-only transport.
Model/equation records fingerprint the unchanged foundation source files. The
endpoint returns the ten frozen components; it never invokes FEM, ageing, RUL
or a probability model. Operational thermal remains unavailable. No standards
equations are newly verified; the existing [reference status](physics_references.md)
continues to apply. Raw ATI mappings declare their actual units; supported
DEG_C inputs are normalized to K inside the unchanged foundation. Publication
has no default parameters and does not use fleet demo ratings.

Optional `at` selects the latest telemetry event at or before the cutoff, within
a 31-day event window. Unknown/repeated parameters and future/naive cutoffs are
rejected. GET never substitutes an earlier READY result for the selected event.
It resolves that event's versions; a new effective profile without a matching
observation withholds derived values. Receipt time remains separate storage
metadata and existing telemetry output. Read evaluation time is server UTC.
See [Phase 5 report](phase5_report.md) for actual results and baseline failures.
