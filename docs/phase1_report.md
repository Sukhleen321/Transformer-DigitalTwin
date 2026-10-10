# Phase 1 — contract and physical model specification

Date: 10 October 2026 (Asia/Calcutta). Branch main, baseline HEAD
`3bf835c7e373565300e395ddaca4007773ef542e`.

## Scope and prior-phase review

Reviewed the complete canonical
[Transformer_DigitalTwin_Physics_First_Implementation_Plan.md](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md),
[Phase 0 report](phase0_report.md), [current architecture](architecture_current.md)
and physics draft against the existing schemas, acquisition/configuration
validators, ingestion service, loading and energy-loss code. Phase 0's audit
exit criteria pass; user approval is recorded. Its baseline is not green.

The canonical filename now exists; the former unified filename is absent.
No second plan was created and the canonical plan was not edited. The Phase 0
report keeps its historical filename finding with a post-approval clarification.

Only Phase 1 contract artifacts and checks are added. No application module,
API response, database schema, simulator configuration, frontend/style,
dependency/lockfile, fitted artifact, estimator or FEM solver is changed.

## Finalized contract

[physics_contract.md](physics_contract.md) is now version 1.0.0. It specifies:

- Five input categories with leaf-level unit, verification, evidence,
  applicability, effective time, uncertainty and range requirements.
- SI-based internal units and explicit exact conversions while retaining
  legacy public units/names. Unknown units and unsupported semantic conversions
  are ineligible; temperature differences never receive an absolute offset.
- A separate future physics result envelope/resource, ten fixed component
  names, public units and provenance kinds. Legacy telemetry/ML/latest schemas
  and native enums remain unchanged. The reserved route is not implemented.
- Independent READY/INITIALIZING/INSUFFICIENT_DATA/INVALID_CONFIGURATION/
  MODEL_ERROR statuses; unavailable values are null and failures carry reasons.
  All required causes remain visible with deterministic status precedence.
- Event-time dt, stale/gap/range/history/initialization policies with no guessed
  numerical defaults; reset/split behavior on effective configuration changes.
- Separate model/parameter/configuration/preprocessing/equation identities,
  immutable evidence requirements, coverage and controlled synthetic context.
- Ageing/history eligibility, FEM verification/convergence evidence and
  comparison-compatibility gates. None asserts field accuracy or RUL.
- An equation/source ledger distinguishing code-derived empirical behavior,
  project loss approximation, verified unit definitions and unverified
  candidate standards/FEM equations.

The result JSON Schema checks representable structure; prose specifies
physical eligibility and invariants that require later runtime implementation.
Unit-vector evaluation and result-fixture checks are test-only, independent of
the production pipeline. Production unit adapters, state and solvers belong to
later phases. Hypothetical READY fixtures are not physical validation evidence.

## Verified sources and limits

The official BIPM [SI Brochure](https://www.bipm.org/en/publications/si-brochure),
9th edition, English V4.01 June 2026, verifies Celsius/kelvin absolute versus
interval treatment (§2.3.1 p129), derived-unit definitions (§2.3.4 Tables 4–5),
prefixes (§3 Table 7) and hour/second conversion (§4 Table 8). The registry
records exact conversion constants; percent normalization is a project
mathematical convention. These references do not verify real sensor units.

The official [IEC catalog](https://webstore.iec.ch/en/publication/34351) verifies
IEC 60076-7:2018, edition 2.0, and mineral-oil scope. The official
[IEEE catalog](https://standards.ieee.org/ieee/C57.91/7163/) lists C57.91-2025 as
active, published 2026-03-05 and superseding 2011. Only catalog metadata/scope
was verified: no full-text thermal/ageing equation clauses were reviewed or
adopted. Phase 2 must record the applicable edition and exact equation locators;
no standards-compliance claim is made.

Repository sources and baseline revision identify existing empirical
coefficients, loading semantics and approximate loss behavior. They do not
restore the missing fitted release or supply real transformer specifications.

## Remaining decisions by evidence owner

The full D01–D12 lineage is grouped in the
[contract decision register](physics_contract.md#decision-register--all-unresolved-questions-by-evidence-owner).

| Requested category | Resolved / remaining |
|---|---|
| 1. Existing repository | Resolved filename authority, current units/type rules, WTI restriction, fictional configurations, native states/history, late ingestion behavior, new interface placement/status/provenance. |
| 2. Standards/technical references | Catalog editions/scopes and SI definitions verified. Full equation clauses, applicability, thermal/ageing methods and heat-conduction/FEM reference still required. |
| 3. Real equipment/sensors | Real type/fluid/insulation/cooling, nameplates, sensor meaning/units/location/scaling/clock, loss tests, thermal constants, geometry/materials/boundaries and independent reference measurements still unavailable. Explicit required paths/gates replace guessed values. |
| 4. Configurable/unavailable later | Stale/gap/range/init/history thresholds, synthetic FEM case/solver/mesh, aggregate/relative metrics, persistence/evidence encoding and additional hot-spot observation remain deferred with defined unavailable behavior. |
| 5. Unrelated failures/artifacts | Phase 0 backend failures, import/dependency issues, missing fitted artifacts and lint failures remain unresolved. No fabrication, dependency install or unrelated fixes. |

No operational physical-parameter default was approved. A later explicit
synthetic case may carry fictional inputs and must remain distinguishable from
real equipment evidence. No estimate is labelled a measurement.

## Files changed during Phase 1

- [physics_contract.md](physics_contract.md): finalized shared interface,
  source ledger and five-category decision register.
- [architecture_current.md](architecture_current.md): canonical plan link and
  Phase 1 compatibility note only.
- [phase0_report.md](phase0_report.md): historical/canonical filename clarification.
- [physics-result-v1.schema.json](contracts/physics-result-v1.schema.json):
  machine-readable future result contract.
- [physics-units-v1.json](contracts/physics-units-v1.json): exact unit registry.
- [cases.json](../tests/fixtures/physics/cases.json),
  [validate.py](../tests/fixtures/physics/validate.py) and
  [README.md](../tests/fixtures/physics/README.md): contract-only vectors/examples,
  negative checks and reproducible invocation.
- [phase1_report.md](phase1_report.md): this report.

All three Phase 0 documents and the canonical plan were untracked on entry;
Phase 1 changes within them are identified above. Existing runtime logs are
untouched. No commit is created.

## Actual verification commands/results

All commands below ran from the repository root using the existing .venv.
No dependencies were installed. The normal Windows sandbox helper remained
unavailable; commands used the approved elevated execution fallback.

| Command | Actual result |
|---|---|
| `.venv/Scripts/python.exe tests/fixtures/physics/validate.py` (first run) | Exit 1: the negative invalid-calendar timestamp case was unexpectedly accepted by the installed JSON Schema format checker. Added explicit standard-library calendar validation; no application behavior changed. |
| Same command after correction | Exit 0: **9 unit rules, 18 exact vectors plus inverses, 13 unit rejection cases, 6 result fixtures, 31 result rejection cases, 3 JSON rejection cases, 80 local documentation links** pass. No production physics/solver exercised. |
| `.venv/Scripts/python.exe tests/fixtures/hackathon/validate.py` | Exit 0: strict parsing of 15 files; **10 schemas/57 examples**, 13 RUL/energy arithmetic/eligibility cases, 10 ingestion traces, 3 semantic hash vectors, bounded-query checks and 17 documentation links pass. Existing contract fixtures unchanged. |
| `.venv/Scripts/python.exe -m ruff check tests/fixtures/physics/validate.py` (first run) | 2 B023 loop-variable binding errors in the new checker; corrected explicit lambda bindings. |
| `.venv/Scripts/python.exe -m ruff format --check tests/fixtures/physics/validate.py` (first run) | New checker would be reformatted. Applied formatter to this new file only. |
| `.venv/Scripts/python.exe -m ruff format tests/fixtures/physics/validate.py` | Exit 0; 1 new file reformatted. No existing application/test file reformatted. |
| `.venv/Scripts/python.exe -m ruff check tests/fixtures/physics/validate.py` (final) | Exit 0; all checks passed. |
| `.venv/Scripts/python.exe -m ruff format --check tests/fixtures/physics/validate.py` (final) | Exit 0; 1 file already formatted. |
| `git diff --exit-code` | Exit 0; tracked application/configuration/frontend/test files unchanged. New/edited untracked documentation and fixture files are listed above. |
| `git status --short` | Only the canonical plan, original four logs, three Phase 0 documents and new Phase 1 contract/report/fixtures are untracked; no tracked modification. |

Source/file inspection and official-source browsing were investigative checks,
not application test passes.

The complete backend/ML/simulator suites and frontend build were not repeated
for this contract-only change. Their actual **Phase 0** results remain in the
baseline report (including 15 backend diagnostic failures, 95 ML failures,
missing pymodbus and existing lint failures). This phase neither resolves them
nor claims a newly green complete suite or exhaustive UI verification.

## Phase 1 exit criteria

| Criterion | Assessment |
|---|---|
| Contract stable enough for independent modules | PASS: input quantity records/maps, fixed output schema, unit registry, component status/null/coverage/version/provenance rules and compatibility boundary are finalized. Missing equation/model selections use explicit configuration eligibility, not schema guesses. |
| Every numeric field has a unit and provenance | PASS at specification level: telemetry/configuration inventory and new input/output quantities include units/evidence. Unknown real units remain explicitly unknown/ineligible. Unit definitions are tested; operational source verification is not fabricated. |
| Unknown/missing required data has defined behavior | PASS: per-path missing reasons, unavailable null values, configuration/data distinction, event-time policy, history/initialization/reset and ageing/FEM/comparison gates are explicit. |
| Estimates do not imply measurement | PASS: fixed result kinds; oil sensor, hot-spot estimate, FEM reference and synthetic origin remain distinct. Synthetic inputs cannot become OPERATIONAL READY results or measured equipment temperatures. |

**Phase 1 exit criteria PASS for contract/specification work.** Production
enforcement, sourced equation implementation, FEM numerical verification,
integration and field validation remain unimplemented. The project's full
definition of done is not yet satisfied.

Work stops here. Phase 2 is the next sequential phase and requires user
review/approval. Authoritative equation access and actual equipment/sensor
evidence remain open; absent evidence must continue to produce explicit
unavailable results.
