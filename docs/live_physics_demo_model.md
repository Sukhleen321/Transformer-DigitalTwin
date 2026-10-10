# Opt-in live synthetic physics demonstration v1

This is the model definition for the explicitly requested follow-up, not a
replacement implementation plan. The canonical plan and Phase 0–7 reports remain
historical records. Production physics contract 1.0.0 and eligibility are frozen.
This specification is recorded before implementation. All parameters below are
fictional project definitions, not transformer specifications or standards data.

## Scenario and units

Case LIVE_SYNTHETIC_TWO_LAYER_V1: ambient and both initial nodes 300 K; oil-to-
ambient resistance 0.35 K/W; winding-to-oil resistance 0.2 K/W; oil capacitance
80 J/K; winding capacitance 40 J/K. Synthetic balanced RMS line currents on a
declared fictional HV side: I(t)=10[0.55+0.25 sin(t/20)] A (t in seconds).
Synthetic reference current 10 A, no-load loss 6 W, rated load loss 30 W at
300 K. Existing current-squared kernel gives P=6+30(I/10)^2 W. Explicit demo
partition Po=6 W, Pw=P−6 W. No partition is inferred for equipment.

Existing PhysicsEstimator receives typed SYNTHETIC quantities, evidence,
versions, ranges, explicit initialization and previous-sample-hold forcing.
Its unchanged two-node equations and exact exponential time advance are used.
The existing RC source trail remains in [physics references](physics_references.md).
The sensor, sheet case and illustrative ageing laws below are explicit project
definitions; no new authoritative IEEE/IEC equation or applicability is claimed.
The first event is INITIALIZING; no temperatures are fabricated to bypass it.
Input bounds: absolute temperature 250–400 K, heat 0–100 W, current 0–20 A,
resistance 0.01–10 K/W, capacitance 1–1000 J/K. Maximum step/gap 30 s,
freshness 15 s; required history 0 s after a strictly positive first interval.
The producer defaults to 4 s, configurable 1–10 s. Event time advances in real
elapsed UTC seconds; there is no accelerated clock. Gaps outside the envelope
fail closed and require a new disposable run.

Synthetic sensor: first-order oil-channel lag with 5 s time constant,
Ts(new)=To(previous)+(Ts(previous)−To(previous)) exp(−dt/5). Initial Ts=300 K.
It is a simulated sensor input, never MEASURED_TELEMETRY. Absolute K converts
to °C by subtracting 273.15. Temperature differences retain K without offsets.
No measurement noise is added: this reproducible verification stream uses the
filtered lag response itself, rather than independent random fluctuations.

The generator now produces a raw demo event before calculation. Raw contract
1.0.0 records event/run/asset/sequence identity, UTC timestamp, source, synthetic
provenance, reference, and explicit value/unit pairs for current (A), load fraction
(1), ambient (K), lagged oil sensor (K), and oil/winding heat inputs (W).
The declared reference current remains 10 A. Ambient 300 K and oil heat 6 W are
fixed applicability conditions for standalone mode. The explicitly selected
accepted-telemetry mode below supports variable ambient with matching RC/FEM
forcing; source partitions remain 6 W plus current-squared winding loss.
Missing/nonfinite/boolean/out-of-range inputs, wrong units, source identities or
inconsistent load/current/loss values are rejected before thermal state advances.

## Explicit full-stack input mode: accepted synthetic telemetry

`PHYSICS_DEMO_INPUT_MODE=accepted-telemetry` is available only with the existing
opt-in flags, `ENV=local-demo`, matching newly named database and an explicit
fictional fleet manifest. It reuses this model and response contract 1.0.0, not a
second estimator. Model source digests distinguish this extension from old
checkpoints. Standalone fixed-ambient validation remains unchanged by default.

The shared `simulator/config/operational-fleet.json` supplies all ten IDs, Modbus
unit IDs 1–10, seeds 42–51 and fictional LV configuration (30 kVA, 400 V line-line,
43.30127018922193 A). No real nameplate is inferred. The profile-only server
configuration selects `CORRELATED_DEMO_V1`: 5 s cadence, load period 120 s,
noise correlation time 30 s, phase offset `2π*asset_index/10`.
Load fraction is `clip(0.55+0.25*sin(2π*t/120+phase)+noise,0.15,1)`.
The existing generator's phase currents, phase-neutral voltages, PF, coherent
power, oil level, contacts and trapezoidal energy calculations are retained.
Noise evolves per channel as `n_new=ρ*n_old+sqrt(1−ρ²)*N(0,σ)`,
`ρ=exp(−dt/30)`, bounded to ±3σ, seeded independently per asset, initialized at 0.
σ values: load 0.05; phase current relative 0.01; phase voltage relative 0.005;
PF 0.02; ambient 0.5 °C; oil level 0.3 percentage points. Daily ambient remains
`32+6*sin(π*(UTC_hour−6)/12)+noise` °C. These are fictional demo definitions.

The existing raw oil sensor channel starts at 42 °C and follows
`T_new=T_target+(T_old−T_target)*exp(−dt/1200)`, with
`T_target=ambient+25*loading²` °C using coherent apparent-power loading.
It is a **SIMULATED SENSOR** input, not a real measurement or the RC node truth.
The telemetry adapter preserves that channel (°C→K via +273.15), using model
identity `DEMO_TELEMETRY_SENSOR_INPUT_V1`; it does not apply the standalone 5 s
sensor law a second time. The two thermal models are not calibrated to this
sensor and their initial nodes remain explicitly 300 K.

Accepted LV currents drive a *dimensionless load proxy*:
`L=(I1+I2+I3)/(3*fictional_LV_rating)` and demo reference `I_demo=10*L A`.
This is an explicit synthetic input mapping, **not an actual HV/LV conversion**.
The existing loss law gives `6+30*L² W`, with Po=6 W and Pw=30*L² W.
Ambient is the declared synthetic DEG_C input plus 273.15. Eligibility requires
complete finite currents/ambient/sensor, A/DEG_C units verified SYNTHETIC,
SIMULATED source/origin, declared UTC, fictional-lv-v1 mapping, matching registry
ratings/provenance and source hash. Supported adapter envelope: 0≤L≤1.5,
250≤ambient≤350 K, 250≤sensor≤400 K, age 0–15 s.

Both unchanged governing RC equations and demo sheet FEM now use the same
previous-sample-held ambient Ta(t) as well as previous Po/Pw. `SheetFEM.step`
accepts explicit ambient with default 300 K. Its distributed ambient rejection
forcing is `Ta/(Ro*A)*M*1`; the area means still satisfy the two-node equations
exactly, including variable ambient. Tests check agreement at <1e−8 K.
The independent manufactured rectangle benchmark remains a numerical test,
never an equipment winding result. Ageing laws and common mean target below
are unchanged and illustrative only.

Each accepted source event advances its own SQL-restored checkpoint under the
existing asset lock. Checkpoints retain canonical telemetry ID, asset, timestamp
and semantic hash alongside derived raw quantities. Exact retries do not advance
state. An invalid input/solver failure preserves accepted raw telemetry but
withholds previous demo readings on GET. A forward gap >30 s starts an explicitly
new run, resets illustrative hours, and returns INITIALIZING for thermal history;
corrupt checkpoints are withheld, not silently reset. No GET advances a model.
The opt-in profile runs no standalone physics producer: existing MQTT ingestion
is the single calculation trigger. Ordinary simulator configurations do not
select the correlated demo profile.

## Independent 2D reference and defensible common target

Two overlapping fictional 0.5×0.5 m sheets, thickness d=0.02 m, conductivity
k=2 W/(m K), area A=0.25 m². These are abstract energy storage sheets, not oil
or winding geometry/materials of a real transformer. Two scalar temperature
fields satisfy reaction-diffusion heat balances:

Co/A ∂To/∂t = kd ΔTo + Po s(x,y)/A +(Tw−To)/(Rw A) −(To−Ta)/(Ro A)

Cw/A ∂Tw/∂t = kd ΔTw + Pw s(x,y)/A −(Tw−To)/(Rw A)

All lateral boundaries have zero normal heat flux. Ambient rejection and
inter-sheet transfer are distributed exchange terms, not boundary convection.
Initial fields are uniform 300 K. Source shape s=1+0.15 cos(πx/Lx)cos(πy/Ly),
normalized by its quadrature integral to preserve exactly the prescribed total
heat. Continuous s has unit area average and is strictly positive. Consistent
P1 triangular FEM mass/stiffness matrices, structured 6×6 subdivisions, order-4
triangle quadrature, and the independent assembled affine matrix exponential
advance the semidiscrete field under the same previous-event forcing.

Integrating these PDEs over the insulated domain yields exactly the two-node
mean equations, independently of conductivity. Therefore the *area-average*
winding-sheet temperature is a defensible common target. It is not the maximum
field temperature. The existing manufactured rectangle is not reused. Demo
rows retain their component keys but explicitly label the FEM row as a winding
mean reference and the estimator row as a winding node proxy. The comparison
is RC winding mean minus FEM winding mean in K. Agreement verifies a conserved
mean and aligned forcing; it does not establish spatial hot-spot accuracy.

Verification criteria: constant patch/heat conservation ≤1e−9; RC/FEM means
≤1e−8 K under irregular positive steps; manufactured insulated cosine mode
L2 error must decrease on 4, 8, 16 meshes with final observed order >1.5. The
manufactured diffusion mode is independent of the old sine/Dirichlet benchmark.
No fitting or adjustment of production numerical models is permitted.

## Illustrative ageing, not insulation life

Demo-only F(t)=exp[(Tw(t)−310 K)/(20 K)] (unit 1). Reference Tw=310 K gives
F=1. The 20 K scale and reference are invented *for this demonstration*, with
no claim to insulation chemistry, IEEE/IEC equations or applicability.
Equivalent illustrative hours H += (Fprevious+Fcurrent)dt/(2×3600).
Only contiguous supported winding-proxy history in this run is integrated;
initial H=0 h denotes zero elapsed supported demo history, not missing data.
This is trapezoidal event-time integration, not an exact continuous integral.
Ageing, RUL and failure probabilities remain unavailable in the production API.

## Isolation and response boundary

Separate GET /api/v1/demo/transformers/{id}/physics, demo contract 1.0.0,
requires PHYSICS_ENABLED and ENABLE_PHYSICS_DEMO (legacy alias
LIVE_PHYSICS_DEMO_ENABLED, default false), explicit local-demo
environment and database name live_physics_demo_<32 hex digits>. A separate
producer writes atomic, timestamped demo events/checkpoints; reads never write.
No production profiles, telemetry or operational evidence are published.
The new empty demo tables are additive; migrations run only on a new DB.
The implementation uses one `live_physics_demo_events` ledger: each row contains
an atomic result and complete checkpoint including its validated `raw_event`,
protected by a digest and code-source
fingerprint. A locked asset row serializes producers; the ledger retains at most
4096 events per asset/run and survives producer restarts within the 30 s gap limit.
Stale/future/corrupt events return unavailable, never cached numeric fallback.
All ten component units/target/provenance are explicit in the demo schema.
Frontend opt-in VITE_LIVE_PHYSICS_DEMO_ENABLED=true selects that endpoint in
Transformer monitoring and Thermal & loading, using one shared hook.
VITE_LIVE_PHYSICS_POLL_INTERVAL_MS is set by the launcher to match its 1–10 s
producer interval (default 4 s). Other builds retain production reads in thermal
and show disabled demo cards in monitoring without requesting simulation data.
Every row displays SYNTHETIC provenance and a demo-specific model identity.
No new migration or public result field was needed for raw-event persistence;
the separate demo result contract remains 1.0.0. Checkpoints from a different
source fingerprint are rejected; do not reuse an old disposable run after
changing demo source. Start a fresh isolated database instead.

The browser-free `--verify-api` launcher mode verifies real generated raw events,
committed checkpoints, changing numeric HTTP responses, exact Vite process
configuration, read-only behavior, missing/invalid/stale/disabled responses and
cleanup. See [pipeline verification and manual startup](live_physics_data_pipeline_report.md).
The current [enablement report](physics_demo_enablement_report.md) documents the
typed flag aliases, precedence and the PowerShell wrapper's KA-BLR-KOR-TX01/TX02
default identities. These identities are taken from the fictional fleet roster,
but the isolated physics case still uses its own explicit 10 A reference and
300 K environment above. The fleet's separate fictional LV ratings are not
imported as thermal evidence or replaced by inferred equipment properties.
