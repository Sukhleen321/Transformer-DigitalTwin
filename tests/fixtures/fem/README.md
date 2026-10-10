# Synthetic FEM regression fixture

[reference_v1.json](reference_v1.json) records bounded scalar diagnostics from
the declared [synthetic sine case](../../../ml/fem/synthetic_sine_v1.json), after
its manufactured-solution checks passed. The fixture includes case digest,
units and synthetic provenance. It prevents numerical regressions; its recorded
numbers are **not** an independent truth source or a transformer specification.

Independent verification uses analytic fields, exact element/energy checks and
affine/quadratic tests in [test_fem.py](../../../ml/tests/test_fem.py). Acceptance
criteria and governing equations were declared in
[fem_reference.md](../../../docs/fem_reference.md) before implementation.

```powershell
.venv/Scripts/python.exe -m ml.fem
.venv/Scripts/python.exe -m pytest ml/tests/test_fem.py -q
```

Both commands run from the repository root. The default CLI emits deterministic
JSON to stdout and exits nonzero when its case or verification fails. To retain
the output, redirect it to a file; `--case` accepts an explicitly supplied
synthetic case with the same supported manifest. There is no equipment fallback,
API/front-end integration or estimator comparison.
