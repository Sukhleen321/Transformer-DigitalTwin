# Physics references — verified foundations and unavailable standards

Checked 10 October 2026. Governing specification:
[canonical implementation plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md).
Public result semantics remain [physics contract 1.0.0](physics_contract.md).

## Standards verification and unavailable equations

| Selected reference | Verified access / exact locator | Equation status and implementation |
|---|---|---|
| IEC 60076-7:2018, edition 2.0, *Power transformers — Part 7: Loading guide for mineral-oil-immersed power transformers* | [Official catalog](https://webstore.iec.ch/en/publication/34351), publication identity/scope only. No full authoritative equation text supplied in the repository or retrieved. | Thermal equations, variable definitions, parameter tables, insulation-ageing equations and clause/equation numbers **UNVERIFIED**. Exact formula locators are unavailable; none fabricated. Model ID IEC_60076_7_2018 returns EQUATION_UNVERIFIED, null thermal values. |
| IEEE C57.91-2025, *IEEE Guide for Loading Mineral-Oil-Immersed Transformers and Step-Voltage Regulators* | [Official catalog](https://standards.ieee.org/ieee/C57.91/7163/), identity/scope only; supersedes 2011. Its linked [open-source project](https://opensource.ieee.org/inslife/ieee-c57.91-thermal-models) returned HTTP 418 through browsing; raw README also inaccessible. | Thermal/ageing clauses, parameter definitions and numerical constants **UNVERIFIED**. No older-edition or third-party formula is silently substituted. Model ID IEEE_C57_91_2025 returns EQUATION_UNVERIFIED, null thermal values. |

Searching for full text also returned third-party previews/summaries and papers
about other editions. Those were not used as standards-formula authority.
Catalogs alone cannot establish equation verification or equipment applicability.
No purchase, account login, subscription or standards-compliance claim is made.
Supplied licensed authoritative clauses can be reviewed in a later authorized
phase; their title/edition/section/equation and applicability must be recorded.

Both standards have mineral-oil scope at catalog level. Actual transformer
fluid, insulation, cooling, construction, rise classes and applicability remain
unsupported. A mode/version name does not establish compliance.

## Verified technical foundations

| Reference ID | Primary source and exact locator | Established use |
|---|---|---|
| SI-2026 | BIPM, *The International System of Units*, 9th edition (2019), English V4.01 June 2026; [official PDF](https://www.bipm.org/documents/20126/41483022/SI-Brochure-9-EN.pdf), §2.3.1 p129; §2.3.4 Tables 4–5; §3 Table 7; §4 Table 8. | Absolute Celsius/kelvin conversion, temperature-difference equality, derived units, kilo/milli prefixes and hour/second conversion. No sensor-unit certificate. |
| MIT-BALANCE | MIT Unified Engineering, *Thermodynamics and Propulsion*, [§18.3 Transient Heat Transfer](https://web.mit.edu/16.unified/www/SPRING/propulsion/notes/node129.html), equations 18.15–18.18. The HTML displays double-dot equation numbers, while its internal cross-references use 18.15 etc. | Lumped stored-energy balance, cooling law and single-node exponential solution; spatial-uniformity assumptions are explicit. This is general heat transfer, not a transformer loading standard. |
| MIT-RESISTANCE | Same course, [§16.4 Thermal Resistance Circuits](https://web.mit.edu/16.unified/www/SPRING/propulsion/notes/node118.html), equation 16.21. | Heat rate equals temperature difference divided by thermal resistance. No wall dimensions/material values from the worked example are reused. |
| SCIPY-EXPM | [SciPy 1.16.2 expm documentation](https://docs.scipy.org/doc/scipy-1.16.2/reference/generated/scipy.linalg.expm.html), function definition/Notes; Al-Mohy and Higham (2009), DOI 10.1137/09074721X as cited there. | Existing installed SciPy computes the matrix exponential. No new numerical dependency. |
| REPO-LOSS | [ml/energy/loss.py](../ml/energy/loss.py), baseline 3bf835c7e373565300e395ddaca4007773ef542e, interval_loss and eligibility functions. | Existing project current-squared approximation; retained as a separately identified approximation, not standards authority. |
| REPO-EMPIRICAL | [ml/thermal/thermal_twin.py](../ml/thermal/thermal_twin.py), same baseline. | Existing empirical oil-indicator model preserved; no coefficients imported into the new model. |

## Implemented equation identities

PROJECT_TWO_NODE_RC_V1 is a **project-derived simplified model** combining
MIT-BALANCE and MIT-RESISTANCE with this project's chosen two-node topology.
It is not an IEC/IEEE equation and is restricted to CONTROLLED_SIMULATION.
The parameters below have no defaults and no real equipment values supplied.

```text
E1: C_o * dT_o/dt = P_o + (T_w - T_o)/R_w - (T_o - T_a)/R_o
E2: C_w * dT_w/dt = P_w - (T_w - T_o)/R_w
E3: x(t + dt) = exp(M * dt) * x(t), x = [T_o, T_w, 1]^T

M = [ -(1/R_o + 1/R_w)/C_o,   1/(R_w*C_o),   (P_o + T_a/R_o)/C_o ]
    [        1/(R_w*C_w),    -1/(R_w*C_w),             P_w/C_w    ]
    [              0,                 0,                   0      ]

E4: top_oil_rise = T_o - T_a; winding_hot_spot_gradient = T_w - T_o
```

T_o/T_w are idealized uniform oil/winding-node temperatures (K), T_a boundary
temperature (K), P_o/P_w explicit nonnegative heat inputs (W), C_o/C_w positive
thermal capacitances (J/K), R_o/R_w positive effective resistances (K/W), dt
elapsed event time (s). E3 is the exact affine-ODE flow for constant parameters
and held forcing, evaluated numerically to floating-point precision. Current
forcing is held for the **next** interval; previous forcing drives the elapsed
interval. Internal state is initialized only from explicit case temperatures.

The project's hot_spot_temperature output denotes the explicitly declared
idealized winding-node proxy, not a resolved maximum within a real winding.
top_oil_temperature similarly denotes an idealized node, not proven physical
sensor equivalence. Warnings preserve this restriction. No FEM is used.

PROJECT_CURRENT_SQUARED_LOSS_V1:

```text
L1: load_loss = rated_load_loss * mean((I_phase / rated_current)^2)
L2: total_loss = no_load_loss + load_loss
```

I_phase/rated_current are A on the same documented RMS line-current side;
losses are W. The model requires a documented fixed reference-temperature
loss basis, energized configuration and explicit equal-effective-phase
assumption. No resistance-temperature correction, stray-loss decomposition,
voltage/frequency correction or heat-location partition is inferred. Negative
RMS magnitudes are invalid. Zero supported current gives the declared no-load
loss; missing current does not become zero. The approximation is code-derived
from REPO-LOSS, with constant-forcing L1 rather than interval interpolation.
It does not automatically feed the thermal nodes: heat partition requires
separate explicit P_o/P_w case inputs.

## Ageing blockers

No ageing equation is implemented. The selected IEC/IEEE laws and constants
are unverified; actual liquid/insulation applicability and eligible winding
hot-spot history are absent. Controlled lumped-node temperatures cannot
establish real insulation exposure. ageing_acceleration_factor and
equivalent_ageing_hours remain null with explicit reasons. No normal-life
budget, RUL, failure probability or empirical calibration is introduced.

Numerical unit tests verify these implemented equations and state rules, not
their fidelity to equipment. Independent measurements, equipment-specific
parameter evidence and applicable standards text are still required for
operational hot-spot estimation or ageing.

## Phase 3 independent conduction reference

Checked 10 October 2026 before coding. [fem_reference.md](fem_reference.md)
records F1–F4, synthetic inputs, analytical target, discretization and acceptance
criteria. This steady conduction benchmark does not use an IEEE/IEC law.

| Reference ID | Exact verified locator | Use / limits |
|---|---|---|
| MIT-FOURIER | MIT Thermodynamics and Propulsion, [§16.2 equations 16.6–16.8](https://web.mit.edu/16.unified/www/SPRING/propulsion/notes/node116.html). | Fourier flux and conductivity units. Isotropic vector extension and steady source balance are explicitly project derivations; no material-table values used. |
| FEM-WEAK | Langtangen/Logg, adapted by Dokken, FEniCSx [Poisson equations (2)–(5)](https://jsdokken.com/dolfinx-tutorial/chapter1/fundamentals.html); [coefficient PDE / variational-form section](https://jsdokken.com/dolfinx-tutorial/chapter3/robin_neumann_dirichlet.html#the-pde-problem-and-variational-formulation). | Trial/test spaces and coefficient weak form. Own P1 assembly; full Dirichlet only. No FEniCS dependency or borrowed implementation. |
| FEM-ERROR | Same authors, [Computing error norms / Computing convergence rates](https://jsdokken.com/dolfinx-tutorial/chapter4/convergence.html). | Integrated field/gradient errors and logarithmic mesh-rate definition. Project-specific tolerances are not standards criteria. |
| SCIPY-SPARSE | [SciPy 1.16.2 spsolve](https://docs.scipy.org/doc/scipy-1.16.2/reference/generated/scipy.sparse.linalg.spsolve.html), function signature, permc_spec / use_umfpack parameters. | Existing sparse direct solver; explicit COLAMD and use_umfpack=False select SuperLU. Residual and heat balance verified separately. |

The sine and quadratic verification solutions are differentiated analytically
in the project specification/tests, independent of the estimator and numerical
assembly. Mesh convergence is numerical verification, not equipment validation.
