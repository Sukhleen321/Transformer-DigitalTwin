# Phase 3 — independent synthetic 2D conduction reference

This specification was written before solver implementation on 10 October
2026, under the sole [canonical plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md).
The approved [physics contract](physics_contract.md) and controlled-only
[Phase 2 estimator](physics_model.md) remain in force. This is a model
specification, not a competing implementation plan.

## Geometry, material, sources and boundary data

The benchmark is a homogeneous rectangle, 0 <= x <= Lx, 0 <= y <= Ly, with
constant out-of-plane thickness d. It is **SYNTHETIC**, not a transformer
cross-section or a material datasheet. Its fully declared case is
[synthetic_sine_v1.json](../ml/fem/synthetic_sine_v1.json).
The extruded interpretation assumes temperature independent of z and zero
normal heat flux on the two out-of-plane faces; there is no face-cooling term.

| Declared benchmark input | Value / unit | Provenance and applicability |
|---|---|---|
| Lx, Ly, d | Each 1 m | Project-selected verification geometry only |
| k | 1 W/(m K) | Synthetic constant, isotropic conductivity; no real material identity |
| Tb | 300 K | Prescribed temperature on all four exterior edges |
| A | 10 K (temperature difference) | Manufactured temperature amplitude |
| Source q''' | k A pi^2 (Lx^-2 + Ly^-2) sin(pi x/Lx) sin(pi y/Ly), W/m^3 | Deliberately manufactured volumetric heating; nonnegative in this rectangle |
| Initial condition | Not applicable | Steady state; no time integration or initial-temperature claim |
| Density / specific heat | Not required and not supplied | No transient storage term |

No nameplate, transformer dimensions, oil/copper/steel properties, heat
partition, cooling coefficients or sensor values are inferred. The declared
thickness multiplies both stiffness and load. It changes integrated power,
but cancels from this uniform steady temperature problem.

## Governing equations and exact verification target

```text
F1: heat flux j = -k grad(T)                         [W/m^2]
F2: -div(k grad(T)) = q''' in Omega                  [W/m^3]
F3: T = Tb on the full boundary                      [K]

Manufactured exact solution:
T*(x,y) = Tb + A sin(pi x/Lx) sin(pi y/Ly)            [K]
grad(T*) = [A pi/Lx cos(pi x/Lx) sin(pi y/Ly),
            A pi/Ly sin(pi x/Lx) cos(pi y/Ly)]        [K/m]
P* = integral_Omega q''' d dOmega
   = 4 k A d (Ly/Lx + Lx/Ly)                        [W]
```

The exact solution follows by differentiating the declared function twice;
it is independent of both numerical assembly and the two-node estimator.
The synthetic domain maximum is Tb+A at the rectangle center. An additional
affine patch test and a quadratic manufactured field with nonconstant edge
temperatures verify boundary elimination and avoid relying on this one sine
case. No coefficients are tuned to match the estimator.

Verified technical sources (checked 10 October 2026):

- MIT Unified Engineering, Thermodynamics and Propulsion,
  [§16.2 equations 16.6–16.8](https://web.mit.edu/16.unified/www/SPRING/propulsion/notes/node116.html):
  Fourier conduction law, flux and conductivity units. No tabulated material
  values are reused. F2 is the project steady energy balance using F1.
- Langtangen/Logg, adapted by Dokken, FEniCSx tutorial,
  [Poisson formulation equations (2)–(5)](https://jsdokken.com/dolfinx-tutorial/chapter1/fundamentals.html)
  and [coefficient PDE / variational-form section](https://jsdokken.com/dolfinx-tutorial/chapter3/robin_neumann_dirichlet.html#the-pde-problem-and-variational-formulation).
  These establish the weak-form construction. This implementation uses
  constant k, full Dirichlet data and its own P1 assembly; no FEniCS code or
  library dependency is copied or required.
- Same authors, [error norms and convergence-rate sections](https://jsdokken.com/dolfinx-tutorial/chapter4/convergence.html):
  integrated temperature/gradient errors and mesh-rate definition. The
  synthetic tolerances below are project acceptance criteria, not standards.
- [SciPy 1.16.2 spsolve](https://docs.scipy.org/doc/scipy-1.16.2/reference/generated/scipy.sparse.linalg.spsolve.html),
  API/parameter definitions: sparse direct linear solve. Existing NumPy/SciPy
  dependencies suffice; no added numerical package.

IEEE/IEC thermal/ageing clauses remain unverified as recorded in
[physics_references.md](physics_references.md). They are not authority for this
synthetic benchmark and no standards-compliance claim is made.

## Discretization and solver strategy

Use continuous piecewise-linear (P1) triangles on an nx-by-ny uniform
rectangle grid, two counterclockwise triangles per cell, fixed southwest to
northeast diagonal. No finite-difference stencil substitutes for element
assembly. Test functions vanish on the prescribed boundary:

```text
F4: integral_Omega d k grad(T_h).grad(v_h) = integral_Omega d q''' v_h
K_e[i,j] = d k area_e grad(N_i).grad(N_j)               [W/K]
F_e[i] = integral_triangle d q''' N_i                  [W]
K_ff T_f = F_f - K_fd T_D
```

Element shape gradients/stiffness are exact for constant k. Load and error
integrals use tensor Gauss-Legendre quadrature after a Duffy map from a unit
square to the reference triangle, order 6 in each coordinate. Quadrature is
not exact for sine functions; a separate order-8 check bounds its effect.
No borrowed triangle-rule constants or material constants are used.

Boundary values are imposed by eliminating boundary degrees of freedom.
The solve uses a constant temperature shift derived from the supplied
boundary values to reduce cancellation; it is an algebraic change of variable,
not an initialization or calibration. SciPy sparse SuperLU is selected with
COLAMD ordering and use_umfpack=False. No iterative tolerance is asserted.
Post-solve diagnostics include the free-equation residual and boundary
reactions. Summed outward reaction power equals integrated source power;
this is the discrete weak balance, not an independent physical measurement.

Declared acceptance criteria before execution:

- Meshes nx=ny=8,16,32,64; h is maximum triangle edge (m).
- Temperature L2 error sqrt(integral (T_h-T*)^2 dOmega), unit K m, must
  decrease on every refinement; each rate log(E_old/E_new)/log(h_old/h_new)
  must be >=1.8. Final L2 error <=0.005 K m.
- Gradient H1 seminorm error sqrt(integral |grad(T_h)-grad(T*)|^2 dOmega),
  unit K in this 2D norm, must decrease; each rate >=0.9.
- Final domain-maximum error <=0.01 K; this is a benchmark scalar tolerance,
  not a field uncertainty bound or transformer accuracy claim.
- Free-equation scaled backward residual <=1e-10 (dimensionless), and
  source/reaction imbalance <=1e-8 W on every benchmark mesh.
- Source quadrature versus P* <=1e-6 W; order-6/order-8 final L2 norms differ
  by <=1e-8 K m.

The acceptance numbers are explicit synthetic verification policies and do
not become universal solver, sensor or material limits. Failure withholds a
READY reference and reports actual diagnostics; criteria are not loosened
after observing results. Invalid/nonfinite data cannot silently become zero.

## Outputs, reproducibility and comparison boundary

The isolated ml.fem package returns a mesh and temperature field in SI units.
`rectangle_mesh(Lx, Ly, nx, ny)` constructs the reference grid;
`solve_steady` requires explicit conductivity, thickness, source function,
boundary-temperature function, quadrature order and residual policy. Functions
take point arrays with final dimension 2 and return numeric arrays of the
matching leading shape (W/m^3 or K respectively). `error_norms` also takes an
analytic gradient function returning matching 2-vector arrays (K/m). Output
mesh/temperature arrays are read-only and Solution labels SIMULATED_REFERENCE.
Core invalid-input/numerical paths raise FEMError; only the benchmark runner's
full verification can publish READY. No history or estimator state is read.
The command below runs the declared case, all refinement levels and acceptance
checks, then emits deterministic JSON (no wall-clock timestamps/runtime in the
artifact). Case digest, solver/equation IDs, mesh, quadrature, source, numerical
verification and convergence records accompany scalar quantities. Every FEM
artifact has SIMULATED_REFERENCE, SIMULATED origin, SYNTHETIC verification and
CONTROLLED_SIMULATION context. Failed checks give MODEL_ERROR and a null
published reference maximum; invalid case inputs give INVALID_CONFIGURATION.

```powershell
.venv/Scripts/python.exe -m ml.fem
.venv/Scripts/python.exe -m pytest ml/tests/test_fem.py -q
```

The FEM synthetic-domain maximum is **not** exported as the frozen API's
fem_hot_spot_temperature yet. The two-node estimator has no matching spatial
geometry or location mapping and its effective R/C heat partitions differ
from this PDE. No estimator-versus-FEM errors, ageing or operational outputs
are produced in Phase 3. A later authorized comparison requires explicit
same-target, source, boundary, geometry, time/steady-state and parameter
compatibility records. The application, API and estimator remain untouched.

Only homogeneous constant-k steady conduction and fully prescribed boundaries
are supported. No transient, radiation, convection/Robin, fluid flow, anisotropy,
contact resistance, real winding layout or 3D behavior is established. Arrays
and sparse matrix costs grow with nx*ny; mesh limits bound this small reference
implementation. Actual results and measured runtime belong to the Phase 3
report, not to this predeclared specification.

The default run has 4,225 nodes (3,969 free degrees of freedom) and 8,192
triangles at its finest level. The observed final CLI wall time was 1.791 s on
the current environment, including Python startup. The initial in-process
benchmark took 0.947 s. These are observations, not runtime guarantees. Sparse
factorization has additional fill-in costs; native peak memory was not measured.
The explicit resource cap is 128 subdivisions per direction (32,768 triangles).
Python execution was verified on 3.12.7 with NumPy 1.26.4 / SciPy 1.16.2;
the declared Python 3.10 minimum was linted but not executed separately.

The artifact includes the complete quantity/evidence case and dependency
versions. Saved [regression fixtures](../tests/fixtures/fem/README.md) and
[Phase 3 results](phase3_report.md) complement the independent analytic checks.
