# Transformer Digital Twin — Unified Phase-by-Phase Implementation Plan

## Purpose

Upgrade the existing Transformer-DigitalTwin repository into a physics-first digital twin that estimates important internal transformer states from available telemetry, validates its calculations against an independent simplified finite-element method (FEM) reference, and presents results in the existing application.

This is one sequential implementation plan for a Codex agent. Do not divide the work into person-specific tasks. Implement one phase at a time, test it, report the result, and only proceed after its exit criteria pass.

## Non-negotiable rules

1. **Inspect before editing.** Read the repository structure, README, dependency files, current API contracts, telemetry schema, current thermal calculations, tests, and frontend entry points before deciding where code belongs.
2. **Preserve working functionality.** Extend the current architecture where practical. Do not replace the application, rewrite unrelated modules, or remove existing features without a demonstrated need.
3. **Freeze interfaces before parallelizable implementation.** Create and maintain `docs/physics_contract.md` before integrating new modules. Use the repository's existing naming conventions where possible.
4. **Never invent physics inputs.** Every physical parameter must have a documented source, unit, applicability, and default/availability policy. If a necessary parameter is unavailable, expose the assumption or report that the estimate cannot be produced.
5. **Do not confuse data types.** Distinguish measured telemetry, calculated estimates, simulated FEM reference values, and synthetic/demo data in code, API responses, and UI.
6. **Missing is not zero.** Missing, stale, invalid, or out-of-range measurements must not silently become zero or produce deceptively valid outputs.
7. **No unsupported accuracy claims.** FEM is a numerical reference, not ground-truth field data. Do not claim validated real-world hot-spot accuracy without independent measured reference data.
8. **Standards and citations.** Use the relevant editions and applicable guidance of IEEE C57.91 and IEC 60076-7 where appropriate. Verify the equations and assumptions against accessible authoritative sources or provided project materials. Record exact source title, edition/year, section/table/equation where verified. Do not fabricate citations or copy a formula from memory and label it standards-compliant without verification.
9. **Keep the existing frontend appearance.** Preserve the current layout, visual language, colors, navigation, spacing, and components as far as possible. Make targeted additions only where needed.
10. **Every control must work.** Every visible button, toggle, tab, dropdown, and form control must have a real, clear action. Remove it if unnecessary, or implement and test its behavior. Do not add decorative controls.
11. **No silent success.** API failures, invalid inputs, unavailable estimates, and simulation errors must be surfaced clearly in logs and appropriate UI states.
12. **Small, reviewable changes.** Prefer focused commits/patches and avoid mixing unrelated formatting or refactoring with physics implementation.

---

## Target outcome

The existing application should continue to ingest/display its current telemetry and monitoring outputs, while adding a traceable physics-based path for estimating internal thermal state and (when supported) insulation ageing. A simplified 2D FEM model provides a separately labelled numerical reference for controlled cases. The application compares outputs only when their assumptions, geometry, parameters, units, and boundary conditions make that comparison meaningful.

### Expected capabilities

- Explicit, validated telemetry and configuration inputs.
- Electrical-loss calculations only to the extent supported by available inputs and a documented model.
- A documented dynamic thermal model.
- Hot-spot estimation with units, status, assumptions, and provenance.
- Insulation ageing calculation only when the required thermal history and model inputs are available.
- A simplified 2D thermal FEM reference solver with reproducible cases and mesh-convergence checks.
- Physics-versus-FEM comparison and error metrics for comparable test cases.
- Automated unit, integration, API, frontend, and numerical regression tests.
- UI states for valid, initializing, insufficient-data, invalid-configuration, and failed-model scenarios.
- Documentation of limitations and a reproducible demo workflow.

### Explicit non-goals for this iteration

- Do not claim a complete industrial-grade 3D electromagnetic, thermal-fluid, and CFD solver.
- Do not claim actual hidden winding temperature is directly measured if it is estimated.
- Do not claim remaining useful life (RUL), failure probability, or fault probability unless a separately validated method and appropriate data exist.
- Do not optimize for a high ML score at the expense of physical correctness.
- Do not add unrelated features or redesign the frontend.
- Do not treat a close agreement between two models as proof of field accuracy; two models can share assumptions or errors.

---

## Phase 0 — Repository audit and baseline

### Tasks

1. Inspect repository structure and identify:
   - backend framework and startup command;
   - frontend framework, entry point, styling system, and current page structure;
   - telemetry schema and units;
   - existing thermal model and all coefficients/assumptions;
   - existing health/anomaly/fault logic and any explicit gating;
   - current API routes and response formats;
   - data fixtures, simulator, and existing tests;
   - environment variables and deployment configuration.
2. Run the existing tests and available lint/build commands before modifying anything.
3. Record baseline results and current known failures. Do not “fix” unrelated issues without explaining the scope.
4. Draw a small architecture/data-flow diagram in `docs/architecture_current.md`.
5. Create `docs/physics_contract.md` with the initial input/output contract, status enum, units, data provenance labels, error semantics, and parameter provenance requirements.
6. Add a decision log for unresolved questions, such as transformer type, cooling mode, available sensors, rated data, and source telemetry units. Do not guess these values.
7. Capture a brief description of the current frontend appearance and identify where new values can fit without redesign.

### Exit criteria

- Baseline test/build results are recorded.
- Existing telemetry/API contracts are documented.
- Contract draft exists and uses existing field names where appropriate.
- Unknown units and unsupported physical parameters are explicitly listed.
- No application behavior has been removed.

---

## Phase 1 — Contract and physical model specification

### Tasks

1. Finalize `docs/physics_contract.md` before building dependent modules.
2. Define normalized internal units, while preserving the current public API contract where possible. Every conversion must be explicit and tested.
3. Define input categories:
   - observed telemetry;
   - equipment nameplate/configuration parameters;
   - model parameters;
   - environmental/boundary conditions;
   - optional simulation configuration.
4. Define output categories:
   - measured values;
   - calculated estimates;
   - simulated reference values;
   - warnings, assumptions, and unavailable inputs.
5. Define statuses, using existing conventions if present. If no equivalent exists, use a documented set such as:
   - `READY`
   - `INITIALIZING`
   - `INSUFFICIENT_DATA`
   - `INVALID_CONFIGURATION`
   - `MODEL_ERROR`
6. Specify the semantics of `null`, timestamps, stale measurements, out-of-range values, and partial results.
7. Specify versioning for the model and its parameter configuration.
8. Write the equation plan with source references to be verified in Phase 2. Keep a distinction between standards-derived formulas, simplified approximations, and project-specific assumptions.

### Exit criteria

- Contract is stable enough for independent modules to implement against it.
- Every numeric field has a unit and provenance.
- Unknown or missing required data has a defined behavior.
- No field implies a measurement when it is actually an estimate.

---

## Phase 2 — Physics foundation and thermal estimator

### Tasks

1. Verify the applicable thermal-model equations and ageing guidance against the selected editions of IEEE C57.91 and/or IEC 60076-7. Record the exact source and applicability in `docs/physics_references.md`. If authoritative access is unavailable, mark the equation as unverified and do not claim standards compliance.
2. Implement a small, isolated physics package following repository conventions. Avoid embedding core equations directly inside API route handlers.
3. Implement only the loss calculations supported by the actual available inputs and documented equipment assumptions. Do not fabricate rated losses, load, resistance, oil constants, winding constants, or cooling parameters.
4. Implement the selected thermal model with explicit state, timestep, initialization, and missing-data behavior. Make any empirical or calibrated coefficients traceable and configurable.
5. Implement hot-spot estimation as a clearly labelled calculated estimate. Document which measurements and parameters influence it.
6. If the model requires historical input, handle irregular sampling, missing intervals, stale data, and initialization explicitly. Do not assume uniform sampling without checking.
7. Implement insulation ageing only after its thermal input and model applicability are established. Require the necessary thermal history and parameters; otherwise return an unavailable status with an explanation.
8. Keep output schema compatible with `docs/physics_contract.md`.
9. Add unit tests for equations, unit conversions, state evolution, initialization, missing values, invalid values, limiting cases, and deterministic repeatability.
10. Add documentation explaining equations, variables, units, assumptions, and limits.

### Exit criteria

- Physics calculations are isolated from transport/UI code.
- Formula sources and model limitations are documented.
- Unit and edge-case tests pass.
- Missing inputs cannot silently produce a valid-looking estimate.
- The API contract has not drifted.

---

## Phase 3 — Simplified FEM reference model

### Tasks

1. Define a deliberately small and documented 2D thermal-conduction problem. Choose geometry and boundary conditions that can be explained and reproduced. Do not present the simplified geometry as an exact model of the actual transformer unless supported by equipment-specific drawings and properties.
2. Implement the governing heat equation appropriate to the selected problem, with all terms and units documented. For transient conduction, verify the material properties, time integration, source term, and boundary-condition treatment.
3. Implement the FEM discretization using a suitable, maintainable numerical library already available in the repository where practical. If adding a dependency, justify it and update dependency/lock files.
4. Create a simple analytical or manufactured-solution case, where feasible, to test the numerical implementation independently of the transformer model.
5. Add mesh-refinement/convergence tests and record the mesh, solver tolerance, residual or convergence criterion, and numerical limitations.
6. Keep FEM outputs labelled `SIMULATED_REFERENCE`; they must not be represented as measured telemetry.
7. Define which quantities can legitimately be compared with the physics estimator. Align geometry, input heat/load assumptions, boundary conditions, time window, and units before calculating errors.
8. Save reproducible reference fixtures and provide a deterministic command to run the simulation.
9. Document computational cost and assumptions. Do not expand to a full 3D coupled electromagnetic/CFD solver in this iteration.

### Exit criteria

- FEM tests include at least one independent numerical verification case and a mesh-convergence check.
- Simulation is reproducible and its parameters are explicit.
- FEM output provenance is preserved.
- Any model-to-model comparison is restricted to physically comparable quantities.

---

## Phase 4 — Validation and comparison

### Tasks

1. Build a validation harness that feeds controlled, documented inputs to the physics estimator and FEM reference.
2. Compare results only where the two models share compatible assumptions, units, boundary conditions, and target quantities.
3. Report absolute error and relative error where mathematically appropriate; avoid division by near-zero values and document metric definitions.
4. Test qualitative physical behavior:
   - increased heat input should not unexpectedly reduce temperature under otherwise identical steady-state conditions;
   - increased cooling should have the expected effect under the chosen model's assumptions;
   - thermal response should be consistent with the model's documented time constants;
   - results should remain finite and physically plausible within the documented operating envelope.
5. Check conservation/balance behavior where relevant to the implemented equations.
6. Separate numerical verification, comparison between models, and validation against real equipment data. Do not call these interchangeable.
7. Document discrepancies. Fix the cause where justified; do not tune parameters solely to make the two models agree.
8. Add regression fixtures to prevent unintended numerical changes.

### Exit criteria

- Validation results are reproducible.
- Numerical and physics sanity checks pass or have explicitly documented, justified exceptions.
- Known discrepancies and limits are recorded.
- No claims of real-world accuracy are made without independent measurements.

---

## Phase 5 — Backend/API integration

### Tasks

1. Integrate the physics module into the existing backend using the shared contract.
2. Add or extend API routes only as needed. Preserve existing endpoints and response fields unless a versioned, documented change is necessary.
3. Integrate the FEM reference in a controlled way suitable for its runtime cost. Do not run expensive simulations on every page refresh if cached or explicitly triggered execution is more appropriate.
4. Return model version, parameter version, units, provenance, status, assumptions, warnings, and missing-input details as defined by the contract.
5. Validate inputs at the API boundary and handle exceptions without returning fake zero values.
6. Add request/response schema tests, integration tests, and regression tests for existing routes.
7. Ensure logs provide useful diagnostics without leaking secrets or environment variables.
8. Verify startup, configuration, and deployment behavior using the repository's current approach. Do not expose secrets or hard-code credentials.

### Exit criteria

- Existing API tests and relevant new tests pass.
- Responses match the shared contract.
- Invalid/missing inputs return meaningful statuses and explanations.
- The backend can start using the documented commands.

---

## Phase 6 — Frontend integration without redesign

### Tasks

1. Inspect the current frontend and preserve its existing look: layout, colors, typography, navigation, spacing, cards, and chart style.
2. Add the smallest necessary UI changes to display:
   - hot-spot temperature estimate with units and status;
   - relevant thermal inputs and model provenance;
   - ageing indicator only when valid;
   - FEM reference/comparison only when available and appropriate;
   - assumptions, warnings, and missing-data explanations.
3. Clearly distinguish measured telemetry, calculated estimates, simulated references, and demo data.
4. Add explicit loading, empty, insufficient-data, invalid-configuration, and error states.
5. Connect every visible button, tab, dropdown, and toggle to a meaningful action and test it. Remove any unused control rather than leaving it inert.
6. Avoid clutter, duplicate metrics, unsupported precision, and decorative charts with fabricated values.
7. Reuse existing components and styling. Do not rebuild the page or introduce a new design system.
8. Check responsive behavior and readability using the existing frontend tooling.
9. Add or update UI tests where available.

### Exit criteria

- The existing design remains recognizably unchanged.
- New values are labelled with units and provenance.
- No control is inert.
- Loading, unavailable-data, and error states work.
- Frontend build and applicable tests pass.

---

## Phase 7 — End-to-end validation and release readiness

### Tasks

1. Run the full test suite, lint/type checks, backend tests, frontend build/tests, physics tests, FEM tests, and validation harness.
2. Run the app using the repository's documented local setup and verify the main user journey.
3. Verify that existing features still work.
4. Test edge cases: missing telemetry, stale samples, bad units, invalid configuration, insufficient history, simulation failure, and API failure.
5. Confirm that no secrets, local machine paths, large generated outputs, or unintended data files have been committed.
6. Update README with setup, environment variables, commands, architecture, physics assumptions, test commands, demo workflow, and limitations.
7. Add a concise model card or `docs/model_limitations.md` describing intended use, excluded use cases, input requirements, validation evidence, and known failure modes.
8. Provide a final report with:
   - files changed;
   - commands executed and their results;
   - numerical verification and convergence results;
   - API/UI verification results;
   - unresolved issues;
   - claims that are and are not supported by the evidence.

### Exit criteria

- All required tests pass, or every remaining failure is clearly reported with cause and impact.
- Existing application behavior is preserved.
- Demo steps are reproducible.
- Model outputs and limitations are communicated honestly.

---

## Shared API/data-contract checklist

The exact schema must be based on the existing repository. Do not blindly add duplicate fields if equivalent ones already exist. At minimum, the contract must define:

- input timestamp and sampling behavior;
- each telemetry field, unit, source, and validation range;
- equipment/configuration parameters and their source;
- estimated hot-spot value and unit;
- optional ageing output and its interpretation;
- optional FEM reference value and provenance;
- model and parameter versions;
- status, warnings, assumptions, and missing inputs;
- behavior for invalid, missing, stale, and insufficient data.

`null` means unavailable/unknown, not zero. Never label a calculated value as a sensor measurement. Never label a simulation as real-world validation.

---

## Codex execution protocol

Use this protocol throughout the project.

### Before each phase

1. Read this file and the relevant repository docs.
2. Inspect the current code that the phase will touch.
3. State a short plan and list the files expected to change.
4. Identify dependencies on earlier phases and check their exit criteria.
5. If a required physical parameter, unit, source, or design decision is unknown, do not guess. Document it and either implement a safe unavailable state or ask for the missing decision.

### During each phase

1. Make focused changes only for the active phase.
2. Follow the existing architecture and coding style.
3. Add tests alongside the implementation.
4. Run relevant tests after each meaningful change.
5. Do not silently change the contract. If the contract must change, update its documentation and affected tests together.
6. Do not start later phases merely to appear productive if the current phase is failing.

### At the end of each phase

Report:
- what was implemented;
- exact files changed;
- commands/tests run and their actual results;
- assumptions and source references;
- known limitations and unresolved questions;
- whether the exit criteria pass;
- the recommended next phase.

Stop at the phase boundary and wait for the user to review/approve before proceeding. Do not claim tests passed unless they were actually run and passed.

---

## Master prompt to start Codex

Paste this into Codex from the root of the existing Transformer-DigitalTwin repository:

> Read `Transformer_DigitalTwin_Physics_First_Implementation_Plan.md` completely and treat it as the project specification. First inspect the repository and complete Phase 0 only. Do not start implementation phases yet. Preserve all existing behavior and frontend appearance. Run the available baseline tests/build commands, document the current architecture and API/telemetry contracts, identify unknown units and physical parameters, and create the initial `docs/physics_contract.md` and `docs/architecture_current.md`. Do not invent parameters or claim standards compliance without verifying the relevant sources. At the end, report changed files, commands and real results, unresolved decisions, and whether Phase 0 exit criteria pass. Stop and wait for approval.

## Prompt to continue after each review

> Re-read the unified implementation plan and review the previous phase's report and repository state. Check that the previous phase's exit criteria are satisfied. Implement only the next phase in sequence. Inspect affected code before editing, preserve existing APIs and frontend appearance, add appropriate tests, and run them. Do not guess missing physical parameters or source references. At the end, report files changed, commands and actual test results, assumptions, limitations, and whether the phase exit criteria pass. Stop and wait for approval before moving to the next phase.

## Final integration prompt

Use this only after all phases have been implemented:

> Perform a final integration and release-readiness review of the Transformer-DigitalTwin repository against the unified implementation plan. Do not redesign the frontend or make unrelated refactors. Run the complete available test/build/lint suite, physics unit tests, FEM numerical verification and mesh-convergence tests, API integration tests, and end-to-end checks. Verify contract consistency, units, provenance labels, missing-data behavior, preservation of existing features, and that every visible control works. Review the documentation and confirm that all standards references and equations are traceable. Distinguish numerical verification, model-to-model comparison, and real-world validation. Do not claim real-world accuracy, failure probability, or RUL without evidence. Fix only demonstrable integration issues, rerun affected tests, and produce a final report with actual commands/results, changed files, unresolved failures, limitations, and reproducible demo steps.

---

## Definition of done

- [ ] Existing repository and working features were preserved.
- [ ] Baseline and final test results are documented.
- [ ] `docs/physics_contract.md` is consistent across modules.
- [ ] Physics equations, parameters, units, and sources are documented.
- [ ] Missing or invalid data cannot silently become zero.
- [ ] Hot-spot estimates are clearly identified as estimates.
- [ ] Ageing is unavailable when required inputs are unsupported or missing.
- [ ] FEM results are identified as simulated references.
- [ ] FEM has independent numerical verification and a mesh-convergence check.
- [ ] Comparisons use compatible assumptions and units.
- [ ] Frontend appearance is preserved and every control works.
- [ ] README and limitations documentation are updated.
- [ ] The final report states actual test outcomes and does not overclaim accuracy.
