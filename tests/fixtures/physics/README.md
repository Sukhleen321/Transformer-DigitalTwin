# Physics v1 contract fixtures — Phase 1 only

These files check the [finalized contract](../../../docs/physics_contract.md),
[result schema](../../../docs/contracts/physics-result-v1.schema.json) and
[unit registry](../../../docs/contracts/physics-units-v1.json). They do not
implement or exercise a thermal estimator, ageing law, API route or FEM solver.

From the repository root, using the existing environment:

```powershell
.venv/Scripts/python.exe tests/fixtures/physics/validate.py
```

The checker uses the same installed `jsonschema` dependency as the existing
hackathon contract checks. No service, database, network or fitted model is
needed. It exits nonzero on an invalid schema/vector/fixture/link or a rejected
case that unexpectedly passes. It rejects duplicate JSON keys and nonfinite
constants. No production package imports are used.

`cases.json` contains a base envelope, component defaults/overrides and named
positive-case path replacements. Paths are arrays of object keys. The checker
copies the base for each case; a replacement never changes another case.
Unit vectors use exact decimal strings for expected values to distinguish the
273.15 absolute-temperature offset from temperature differences. Every
registered conversion and its inverse has a vector. Unsupported units,
unverified/synthetic operational inputs, nulls, strings, booleans and nonfinite
values are tested as rejections. Declared synthetic conversions are accepted
only for the controlled-simulation context.

**All READY values, LIVE/VERIFIED labels, model/equation IDs and verification
references in these fixtures are hypothetical examples.** They are not real
sensor records, sourced physical parameters, computed thermal results,
standards equations or numerical-verification evidence. An example showing a
FEM READY shape does not satisfy Phase 3 numerical verification. Structural
validation cannot establish applicability or the truth of an evidence label.

The checker validates structural and cross-field result invariants (null/status,
units/kinds, evidence/version presence, replay lineage, synthetic origin,
coverage and comparison operands). Required-input eligibility, time policies,
equation correctness, immutable evidence resolution and state evolution must
be implemented and tested in the later authorized phases. These fixtures must
remain aligned with the shared contract when those implementations are added.
