# Phase 4 synthetic regression fixture

[reference_v1.json](reference_v1.json) snapshots the approved explicit
[manifest](../../../ml/validation/cases_v1.json) through the isolated
[harness](../../../ml/validation/harness.py). Its digest identifies all
parameters, policies, perturbations, sample times and the approved FEM case.
Elapsed times are seconds, temperatures absolute kelvin, relative maximum-rise
error dimensionless; the file declares these units and synthetic provenance.

This snapshot is **numerical regression**, not an independent oracle, equipment
data, calibration or model-to-model agreement. Independent references remain
the derived modal solution and manufactured FEM solution, with acceptance
declared in [validation_reference.md](../../../docs/validation_reference.md).
Do not regenerate the fixture merely to silence a failing comparison/test.

Reproduce from repository root:

```powershell
.venv/Scripts/python.exe -m ml.validation
.venv/Scripts/python.exe -m pytest ml/tests/test_validation.py -q
```

The CLI JSON contains per-node within-model rise metrics, complete estimator
envelopes, FEM refinement/scaling checks and explicit unavailable cross-model
metrics. Regression tolerances are 1e-8 K for temperatures and 1e-9 for the
dimensionless FEM maximum-rise metric. They protect these supported synthetic
cases; they do not assert field accuracy.
