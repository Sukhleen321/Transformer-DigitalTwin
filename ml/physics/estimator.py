"""Isolated physics result/state orchestration. No API/DB/legacy ML imports."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal

from .equations import current_squared_loss, two_node_step
from .types import (
    Evidence,
    InputIssue,
    Policy,
    Provenance,
    Quantity,
    Snapshot,
    ThermalState,
    iso,
    utc,
)
from .units import convert_value, normalize

MODEL_ID = "PROJECT_TWO_NODE_RC_V1"
LOSS_ID = "PROJECT_CURRENT_SQUARED_LOSS_V1"
REGISTRY_VERSION = "physics-equations-1.0.0"
STANDARDS = {"IEC_60076_7_2018", "IEEE_C57_91_2025"}
OUTPUTS = {
    "measured_oil_temperature": ("DEG_C", "MEASURED_TELEMETRY"),
    "top_oil_temperature": ("DEG_C", "CALCULATED_ESTIMATE"),
    "hot_spot_temperature": ("DEG_C", "CALCULATED_ESTIMATE"),
    "top_oil_rise": ("K", "CALCULATED_ESTIMATE"),
    "winding_hot_spot_gradient": ("K", "CALCULATED_ESTIMATE"),
    "total_loss": ("W", "CALCULATED_ESTIMATE"),
    "ageing_acceleration_factor": ("1", "CALCULATED_ESTIMATE"),
    "equivalent_ageing_hours": ("h", "CALCULATED_ESTIMATE"),
    "fem_hot_spot_temperature": ("DEG_C", "SIMULATED_REFERENCE"),
    "hot_spot_difference": ("K", "CALCULATED_ESTIMATE"),
}
THERMAL = (
    "top_oil_temperature",
    "hot_spot_temperature",
    "top_oil_rise",
    "winding_hot_spot_gradient",
)


def issue(status, code, path, message):
    return status, {"code": code, "message": message, "paths": [path] if path else []}


def coverage(state=None):
    if state is None:
        return dict(
            start=None,
            end=None,
            covered_seconds=None,
            expected_seconds=None,
            fraction=None,
            gap_count=0,
            missing_fields=[],
        )
    seconds = (state.timestamp - state.started_at).total_seconds()
    return dict(
        start=iso(state.started_at),
        end=iso(state.timestamp),
        covered_seconds=seconds,
        expected_seconds=seconds,
        fraction=1.0 if seconds > 0 else None,
        gap_count=state.gap_count,
        missing_fields=[],
    )


def component(
    name,
    issues,
    *,
    value=None,
    model_id=None,
    paths=(),
    references=(),
    case_id=None,
    state=None,
    assumptions=(),
    warnings=(),
):
    status = "READY"
    if issues:
        order = {
            "INVALID_CONFIGURATION": 0,
            "INSUFFICIENT_DATA": 1,
            "INITIALIZING": 2,
            "MODEL_ERROR": 3,
        }
        status = min(issues, key=lambda entry: order[entry[0]])[0]
        value = None
    unit, result_kind = OUTPUTS[name]
    missing = sorted({path for _, reason in issues for path in reason["paths"]})
    cov = coverage(state)
    cov["missing_fields"] = missing
    return dict(
        value=value,
        unit=unit,
        result_kind=result_kind,
        status=status,
        reasons=[reason for _, reason in issues],
        missing_inputs=missing,
        warnings=list(warnings),
        assumptions=list(assumptions),
        coverage=cov,
        provenance=dict(
            model_id=model_id,
            equation_ids=[model_id] if model_id else [],
            input_paths=list(paths),
            evidence_references=sorted(set(references)),
            case_id=case_id,
            comparison_id=None,
            numerical_verification_reference=None,
            mesh_convergence_reference=None,
        ),
    )


def digest(value):
    def encode(item):
        if isinstance(item, datetime):
            return iso(item)
        if isinstance(item, Decimal) and item.is_finite():
            return str(item)
        raise TypeError("Unsupported identity record.")

    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=encode
        ).encode()
    ).hexdigest()


class Inputs:
    def __init__(self, snapshot, initial=()):
        self.snapshot = snapshot
        self.issues = list(initial)
        self.quantities = {}
        self.references = set()

    def add(self, code, path, message, configuration=False, status=None):
        self.issues.append(
            issue(
                status or ("INVALID_CONFIGURATION" if configuration else "INSUFFICIENT_DATA"),
                code,
                path,
                message,
            )
        )

    def reference(self, reference, path, configuration=False):
        if not isinstance(reference, str) or not reference.strip():
            self.add(
                "EVIDENCE_MISSING", path, "A named evidence reference is required.", configuration
            )
            return False
        record = self.snapshot.evidence.get(reference)
        if not isinstance(record, Evidence) or not all(
            isinstance(value, str) and value.strip()
            for value in (record.title, record.locator, record.applicability)
        ):
            self.add(
                "EVIDENCE_MISSING",
                path,
                "An accessible evidence record is required.",
                configuration,
            )
            return False
        if record.kind not in (
            "EQUIPMENT_RECORD",
            "SENSOR_RECORD",
            "SYNTHETIC_CASE",
            "TECHNICAL_REFERENCE",
        ):
            self.add("EVIDENCE_UNSUPPORTED", path, "Unknown evidence kind.", configuration)
            return False
        if self.snapshot.context == "OPERATIONAL" and record.kind == "SYNTHETIC_CASE":
            self.add(
                "SYNTHETIC_NOT_OPERATIONAL",
                path,
                "Synthetic evidence is not equipment evidence.",
                configuration,
            )
            return False
        self.references.add(reference)
        return True

    def read(
        self,
        path,
        unit,
        kind,
        *,
        configuration=False,
        minimum=None,
        positive=False,
        semantics=None,
        required_range=False,
    ):
        group, key = path.split(".", 1)
        quantity = getattr(self.snapshot, group).get(key)
        if not isinstance(quantity, Quantity):
            self.add("MISSING_INPUT", path, "Required quantity is unavailable.", configuration)
            return None
        if not isinstance(quantity.provenance, Provenance):
            self.add("PROVENANCE_MISSING", path, "A provenance record is required.", configuration)
            return None
        if quantity.verification not in ("VERIFIED", "SYNTHETIC"):
            self.add(
                "UNIT_UNVERIFIED", path, "Unit/value verification is unsupported.", configuration
            )
        if quantity.verification == "SYNTHETIC":
            if self.snapshot.context != "CONTROLLED_SIMULATION":
                self.add(
                    "SYNTHETIC_NOT_OPERATIONAL",
                    path,
                    "Synthetic input is not operational.",
                    configuration,
                )
            elif quantity.provenance.source_id != self.snapshot.lineage.case_id:
                self.add(
                    "CASE_ID_MISMATCH",
                    path,
                    "Synthetic quantity must identify its case.",
                    configuration,
                )
        reference_ok = self.reference(quantity.provenance.evidence_reference, path, configuration)
        if (
            reference_ok
            and quantity.verification == "SYNTHETIC"
            and self.snapshot.evidence[quantity.provenance.evidence_reference].kind
            != "SYNTHETIC_CASE"
        ):
            self.add(
                "EVIDENCE_UNSUPPORTED",
                path,
                "Synthetic quantity requires case evidence.",
                configuration,
            )
        if reference_ok:
            record = self.snapshot.evidence[quantity.provenance.evidence_reference]
            if record.applicability != quantity.provenance.applicability:
                self.add(
                    "APPLICABILITY_MISMATCH",
                    path,
                    "Quantity applicability differs from its evidence.",
                    configuration,
                )
            if record.kind == "SYNTHETIC_CASE" and quantity.verification == "VERIFIED":
                self.add(
                    "VERIFICATION_INCONSISTENT",
                    path,
                    "Synthetic evidence cannot verify equipment data.",
                    configuration,
                )
        if not all(
            isinstance(value, str) and value.strip()
            for value in (quantity.provenance.source_id, quantity.provenance.applicability)
        ):
            self.add(
                "PROVENANCE_MISSING",
                path,
                "Source identity and applicability are required.",
                configuration,
            )
        if semantics and quantity.provenance.semantics != semantics:
            self.add(
                "SEMANTICS_UNSUPPORTED",
                path,
                "Quantity target/basis is incompatible.",
                configuration,
            )
        try:
            effective = utc(quantity.effective_at)
            event = None
            try:
                event = utc(self.snapshot.timestamp)
            except InputIssue:
                pass  # classified once as missing/invalid event data, not bad parameters
            if event is not None and effective > event:
                self.add("NOT_YET_EFFECTIVE", path, "Quantity is not yet effective.", configuration)
            is_observation = group in ("observed", "environment") or (
                group == "simulation" and key.endswith("heat_input")
            )
            if event is not None and is_observation and effective != event:
                self.add("OBSERVATION_TIME_MISMATCH", path, "Observation must belong to the event.")
        except InputIssue as exc:
            self.add(exc.code, path, str(exc), configuration)
        if required_range and quantity.valid_range is None:
            self.add(
                "RANGE_UNSPECIFIED",
                path,
                "This model requires a declared input range.",
                configuration,
            )
        if quantity.uncertainty is not None:
            self.add(
                "UNCERTAINTY_UNSUPPORTED",
                path,
                "This release does not propagate uncertainty; retain the source record.",
                configuration,
            )
        try:
            normalized = normalize(quantity, unit, kind)
            value = normalized.value
            if (positive and value <= 0) or (minimum is not None and value < minimum):
                raise InputIssue("OUT_OF_RANGE", "Value is outside the model's supported range.")
        except InputIssue as exc:
            self.add(exc.code, path, str(exc), configuration)
            return None
        self.quantities[path] = normalized
        return value


class PhysicsEstimator:
    """One explicitly owned stream per asset. Caller must serialize stream writes.

    No global singleton, persisted checkpoint, API route or implicit history read.
    The simplified thermal path is controlled-case only; ageing remains disabled.
    """

    def __init__(self):
        self._states = {}
        self._last_components = {}
        self._identities = {}
        self._version_records = {}
        self._evidence_records = {}

    def state(self, transformer_id):
        return self._states.get(transformer_id)

    def _clear(self, transformer_id):
        self._states.pop(transformer_id, None)
        self._last_components.pop(transformer_id, None)

    def evaluate(self, snapshot: Snapshot):
        if not isinstance(snapshot, Snapshot):
            raise InputIssue("SNAPSHOT_INVALID", "A typed input snapshot is required.")
        if (
            not isinstance(snapshot.transformer_id, str)
            or not snapshot.transformer_id.strip()
            or snapshot.transformer_id != snapshot.transformer_id.strip()
            or len(snapshot.transformer_id) > 128
            or any(ord(char) < 32 for char in snapshot.transformer_id)
        ):
            raise InputIssue("ASSET_ID_INVALID", "A canonical transformer identity is required.")
        evaluated = iso(snapshot.evaluated_at)  # malformed server metadata is a caller error
        global_inputs = Inputs(snapshot)
        try:
            event = utc(snapshot.timestamp)
        except InputIssue as exc:
            event = None
            global_inputs.add(exc.code, "timestamp", str(exc))
        try:
            evaluation_time = utc(snapshot.evaluation_time)
        except InputIssue as exc:
            evaluation_time = None
            global_inputs.add(exc.code, "evaluation_time", str(exc))
        if event is not None and evaluation_time is not None and event > evaluation_time:
            global_inputs.add("FUTURE_EVENT", "timestamp", "Event exceeds evaluation time.")
        lineage = asdict(snapshot.lineage)
        lineage.pop("timezone_status")
        lineage.pop("case_id")
        if snapshot.context not in ("OPERATIONAL", "CONTROLLED_SIMULATION"):
            raise InputIssue("CONTEXT_INVALID", "Unknown evaluation context.")
        allowed = {
            "source_kind": {"LIVE", "REPLAYED", "SIMULATED", "UNKNOWN"},
            "origin_kind": {"LIVE", "SIMULATED", "UNKNOWN"},
            "input_verification": {"VERIFIED", "UNVERIFIED", "SYNTHETIC", "MIXED", "UNKNOWN"},
        }
        for name, labels in allowed.items():
            if not isinstance(lineage[name], str) or lineage[name] not in labels:
                global_inputs.add(
                    "LINEAGE_UNSUPPORTED", "lineage." + name, "Unsupported lineage label."
                )
                lineage[name] = "UNKNOWN"
        lineage["evidence_references"] = list(lineage["evidence_references"])
        for name in ("acquisition_reference", "origin_transformer_id", "replay_run_id"):
            value = lineage[name]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                global_inputs.add(
                    "LINEAGE_UNSUPPORTED", "lineage." + name, "Invalid source identity."
                )
                lineage[name] = None
        if any(
            not isinstance(value, str) or not value.strip()
            for value in lineage["evidence_references"]
        ):
            global_inputs.add(
                "EVIDENCE_MISSING",
                "lineage.evidence_references",
                "Named source references are required.",
            )
            lineage["evidence_references"] = []
        if snapshot.context == "OPERATIONAL":
            if (
                lineage["origin_kind"] != "LIVE"
                or lineage["source_kind"] not in ("LIVE", "REPLAYED")
                or lineage["input_verification"] != "VERIFIED"
                or snapshot.lineage.timezone_status != "VERIFIED"
            ):
                global_inputs.add(
                    "OPERATIONAL_PROVENANCE_REQUIRED",
                    "lineage",
                    "Verified live-origin evidence and event time are required.",
                )
        elif (
            lineage["origin_kind"] != "SIMULATED"
            or lineage["source_kind"] not in ("SIMULATED", "REPLAYED")
            or lineage["input_verification"] not in ("SYNTHETIC", "MIXED")
            or snapshot.lineage.timezone_status not in ("VERIFIED", "DECLARED_UTC")
            or not snapshot.lineage.case_id
        ):
            global_inputs.add(
                "CASE_PROVENANCE_REQUIRED",
                "lineage",
                "Explicit controlled case provenance is required.",
            )
        if lineage["source_kind"] == "REPLAYED" and (
            not lineage["origin_transformer_id"] or not lineage["replay_run_id"]
        ):
            global_inputs.add(
                "REPLAY_LINEAGE_REQUIRED", "lineage", "Replay run and origin asset are required."
            )
            # Keep the unavailable envelope schema-valid even for malformed lineage.
            lineage["source_kind"] = "UNKNOWN"
        if not lineage["acquisition_reference"]:
            global_inputs.add(
                "ACQUISITION_REFERENCE_REQUIRED",
                "lineage.acquisition_reference",
                "Source event identity is required.",
            )
        for reference in lineage["evidence_references"]:
            global_inputs.reference(reference, "lineage.evidence_references")
        if not lineage["evidence_references"]:
            global_inputs.add(
                "EVIDENCE_MISSING", "lineage.evidence_references", "Source evidence is required."
            )
        versions = asdict(snapshot.versions)
        for key, value in versions.items():
            if value is not None and (not isinstance(value, str) or not value.strip()):
                versions[key] = None
        policy_inputs, ages = self._policy(snapshot)
        global_inputs.issues.extend(policy_inputs.issues)
        if (
            event is not None
            and not global_inputs.issues
            and (evaluation_time - event).total_seconds() > ages[0]
        ):
            global_inputs.add(
                "STALE_OBSERVATION", "timestamp", "Event exceeds the declared maximum age."
            )
        base = dict(
            physics_contract_version="1.0.0",
            transformer_id=snapshot.transformer_id,
            timestamp=iso(event),
            evaluated_at=evaluated,
            context=snapshot.context,
            lineage=lineage,
            versions=versions,
            components={},
        )
        oil_inputs = Inputs(snapshot, global_inputs.issues)
        if snapshot.context == "CONTROLLED_SIMULATION":
            oil_inputs.add(
                "SYNTHETIC_NOT_MEASURED",
                "observed.oil_temperature",
                "Synthetic input is not measured equipment temperature.",
            )
            oil = None
        else:
            oil = oil_inputs.read(
                "observed.oil_temperature", "K", "absolute_temperature", semantics="OIL_SENSOR"
            )
        if not versions["preprocessing_version"]:
            oil_inputs.add(
                "VERSION_MISSING",
                "versions.preprocessing_version",
                "Source mapping version is required.",
                True,
            )
        self._check_versions(snapshot, oil_inputs, measured_only=True)
        base["components"]["measured_oil_temperature"] = component(
            "measured_oil_temperature",
            oil_inputs.issues,
            value=None if oil is None else oil - 273.15,
            paths=oil_inputs.quantities,
            references=oil_inputs.references,
        )
        if not oil_inputs.issues:
            base["components"]["measured_oil_temperature"]["coverage"] = dict(
                start=iso(event),
                end=iso(event),
                covered_seconds=0,
                expected_seconds=0,
                fraction=None,
                gap_count=0,
                missing_fields=[],
            )
        derived = list(global_inputs.issues)
        if any(value is None for value in versions.values()):
            derived.append(
                issue(
                    "INVALID_CONFIGURATION",
                    "VERSION_MISSING",
                    "versions",
                    "All derived-result version identities are required.",
                )
            )
        if snapshot.versions.equation_registry_version != REGISTRY_VERSION:
            derived.append(
                issue(
                    "INVALID_CONFIGURATION",
                    "EQUATION_REGISTRY_UNSUPPORTED",
                    "versions.equation_registry_version",
                    "No verified implementation for this registry version.",
                )
            )
        if snapshot.versions.model_version != "1.0.0":
            derived.append(
                issue(
                    "INVALID_CONFIGURATION",
                    "MODEL_VERSION_UNSUPPORTED",
                    "versions.model_version",
                    "This module implements model version 1.0.0 only.",
                )
            )
        base["components"]["total_loss"] = self._loss(snapshot, derived)
        self._thermal(snapshot, event, ages, derived, base)
        for name in ("ageing_acceleration_factor", "equivalent_ageing_hours"):
            base["components"][name] = component(
                name,
                [
                    issue(
                        "INVALID_CONFIGURATION",
                        "EQUATION_UNVERIFIED",
                        "model_parameters.ageing_law",
                        "Selected standards ageing equations are unverified.",
                    ),
                    issue(
                        "INVALID_CONFIGURATION",
                        "AGEING_PREREQUISITES_UNESTABLISHED",
                        "equipment.insulation_type",
                        "Applicable insulation/liquid and eligible hot-spot history "
                        "are not established.",
                    ),
                ],
            )
        for name in ("fem_hot_spot_temperature", "hot_spot_difference"):
            base["components"][name] = component(
                name,
                [
                    issue(
                        "INVALID_CONFIGURATION",
                        "MODEL_NOT_CONFIGURED",
                        "simulation.fem",
                        "FEM/comparison is not implemented in Phase 2.",
                    )
                ],
            )
        return base

    def _policy(self, snapshot):
        inputs = Inputs(snapshot)
        policy = snapshot.policy
        if not isinstance(policy, Policy):
            inputs.add(
                "POLICY_MISSING",
                "policy",
                "Explicit event-time and state policies are required.",
                True,
            )
            return inputs, (None, None, None)
        # Policy quantities follow the same provenance/unit validation as parameters.
        values = []
        for name in ("max_sample_age_seconds", "max_gap_seconds", "required_history_seconds"):
            proxy = replace(snapshot, model_parameters={name: getattr(policy, name)})
            reader = Inputs(proxy)
            value = reader.read(
                "model_parameters." + name,
                "s",
                "duration",
                configuration=True,
                minimum=0,
                positive=name != "required_history_seconds",
            )
            inputs.issues.extend(reader.issues)
            inputs.references.update(reader.references)
            values.append(value)
        for name in ("initialization_reference", "range_policy_reference", "forcing_reference"):
            inputs.reference(getattr(policy, name), "policy." + name, True)
        if (
            policy.initialization_policy != "EXPLICIT_INITIAL_TEMPERATURES"
            or policy.forcing_policy != "PREVIOUS_SAMPLE_HOLD"
        ):
            inputs.add(
                "POLICY_UNSUPPORTED",
                "policy",
                "This release requires explicit initial temperatures and previous-sample hold.",
                True,
            )
        return inputs, tuple(values)

    def _check_versions(self, snapshot, inputs, measured_only=False):
        """Resolve caller IDs to immutable content within this owned process."""
        if inputs.issues:
            return False
        try:
            values = {
                "parameter_version": {
                    key: asdict(value) for key, value in snapshot.model_parameters.items()
                },
                "configuration_version": dict(
                    selection=asdict(snapshot.selection),
                    policy=asdict(snapshot.policy),
                    equipment={key: asdict(value) for key, value in snapshot.equipment.items()},
                    context=snapshot.context,
                    case=snapshot.lineage.case_id,
                ),
                "preprocessing_version": {
                    path: dict(
                        unit=value.unit,
                        original_unit=value.provenance.original_unit,
                        kind=value.quantity_kind,
                        source=value.provenance.source_id,
                        semantics=value.provenance.semantics,
                        conversion=value.provenance.conversion_id,
                    )
                    for path, value in inputs.quantities.items()
                    if path.startswith(("observed.", "environment.", "simulation."))
                },
            }
            if measured_only:
                values = {"preprocessing_version": values["preprocessing_version"]}
            # Mapping definitions may cover different component subsets. Each
            # path has its own immutable definition under one preprocessing ID.
            staged = {}
            for name, definition in values.items():
                version = getattr(snapshot.versions, name)
                records = (
                    definition.items()
                    if name == "preprocessing_version"
                    else (("bundle", definition),)
                )
                for path, record in records:
                    key = (snapshot.transformer_id, name, version, path)
                    content = digest(record)
                    if key in self._version_records and self._version_records[key] != content:
                        inputs.add(
                            "VERSION_CONTENT_CHANGED",
                            "versions." + name,
                            "An immutable version ID was reused with changed content.",
                            True,
                        )
                    staged[key] = content
            evidence = {
                reference: digest(asdict(snapshot.evidence[reference]))
                for reference in inputs.references
            }
            for reference, content in evidence.items():
                key = (snapshot.transformer_id, reference)
                if key in self._evidence_records and self._evidence_records[key] != content:
                    inputs.add(
                        "EVIDENCE_CONTENT_CHANGED",
                        "evidence." + reference,
                        "A published evidence ID was reused with changed content.",
                        True,
                    )
            if inputs.issues:
                return False
            self._version_records.update(staged)
            self._evidence_records.update(
                {(snapshot.transformer_id, key): value for key, value in evidence.items()}
            )
            return True
        except (ValueError, TypeError, InputIssue):
            inputs.add(
                "IDENTITY_RECORD_INVALID", "versions", "Version records cannot be resolved.", True
            )
            return False

    def _loss(self, snapshot, initial):
        inputs = Inputs(snapshot, initial)
        selection = snapshot.selection
        if selection.loss_enabled is not True:
            return component(
                "total_loss",
                [
                    issue(
                        "INVALID_CONFIGURATION",
                        "MODEL_NOT_CONFIGURED",
                        "selection.loss_enabled",
                        "Loss approximation is not selected.",
                    )
                ],
            )
        if (
            selection.measurement_side not in ("HV", "LV")
            or selection.current_basis != "RMS_LINE_CURRENT"
            or selection.energized is not True
        ):
            inputs.add(
                "LOSS_APPLICABILITY_UNSUPPORTED",
                "selection",
                "Energized, compatible-side RMS line-current basis is required.",
                True,
            )
        inputs.reference(selection.loss_basis_reference, "selection.loss_basis_reference", True)
        ir = inputs.read(
            "equipment.rated_current_a", "A", "current", configuration=True, positive=True
        )
        po = inputs.read(
            "model_parameters.no_load_loss", "W", "active_power", configuration=True, minimum=0
        )
        pr = inputs.read(
            "model_parameters.rated_load_loss", "W", "active_power", configuration=True, minimum=0
        )
        inputs.read(
            "model_parameters.loss_reference_temperature",
            "K",
            "absolute_temperature",
            configuration=True,
        )
        currents = [
            inputs.read(
                "observed.current_l" + str(index),
                "A",
                "current",
                minimum=0,
                required_range=True,
                semantics="RMS_LINE_CURRENT_" + str(selection.measurement_side),
            )
            for index in (1, 2, 3)
        ]
        value = None
        if self._check_versions(snapshot, inputs):
            try:
                value = current_squared_loss(currents, ir, po, pr)
            except (ArithmeticError, ValueError):
                inputs.add(
                    "NUMERICAL_FAILURE",
                    "total_loss",
                    "Loss calculation failed.",
                    status="MODEL_ERROR",
                )
        result = component(
            "total_loss",
            inputs.issues,
            value=value,
            model_id=LOSS_ID,
            paths=inputs.quantities,
            references=inputs.references,
            case_id=snapshot.lineage.case_id,
            assumptions=[
                dict(
                    message="Fixed-temperature, equal-effective-phase loss approximation; "
                    "no heat partition inferred.",
                    reference=selection.loss_basis_reference or "REPO-LOSS",
                )
            ],
        )
        if not inputs.issues:
            result["coverage"] = dict(
                start=iso(snapshot.timestamp),
                end=iso(snapshot.timestamp),
                covered_seconds=0,
                expected_seconds=0,
                fraction=None,
                gap_count=0,
                missing_fields=[],
            )
        return result

    def _thermal(self, snapshot, event, ages, initial, base):
        inputs = Inputs(snapshot, initial)
        selected = snapshot.selection.thermal_model_id
        if selected != MODEL_ID:
            inputs.add(
                "EQUATION_UNVERIFIED" if selected in STANDARDS else "MODEL_NOT_CONFIGURED",
                "selection.thermal_model_id",
                "No verified implementation for the selected thermal model.",
                True,
            )
            for name in THERMAL:
                base["components"][name] = component(name, inputs.issues)
            self._clear(snapshot.transformer_id)
            return
        if snapshot.context != "CONTROLLED_SIMULATION":
            inputs.add(
                "MODEL_NOT_VALIDATED_FOR_EQUIPMENT",
                "selection.thermal_model_id",
                "The simplified node proxy is restricted to controlled cases.",
                True,
            )
        specs = (
            ("oil_thermal_resistance", "K/W", "thermal_resistance"),
            ("winding_thermal_resistance", "K/W", "thermal_resistance"),
            ("oil_thermal_capacitance", "J/K", "thermal_capacitance"),
            ("winding_thermal_capacitance", "J/K", "thermal_capacitance"),
        )
        parameters = [
            inputs.read(
                "model_parameters." + name,
                unit,
                kind,
                configuration=True,
                positive=True,
                required_range=True,
            )
            for name, unit, kind in specs
        ]
        lower = inputs.read(
            "model_parameters.minimum_temperature", "K", "absolute_temperature", configuration=True
        )
        upper = inputs.read(
            "model_parameters.maximum_temperature", "K", "absolute_temperature", configuration=True
        )
        if lower is not None and upper is not None and lower >= upper:
            inputs.add(
                "RANGE_INVALID", "model_parameters", "Temperature envelope is invalid.", True
            )
        ta = inputs.read(
            "environment.ambient_temperature", "K", "absolute_temperature", required_range=True
        )
        po = inputs.read(
            "simulation.oil_heat_input", "W", "heat_rate", minimum=0, required_range=True
        )
        pw = inputs.read(
            "simulation.winding_heat_input", "W", "heat_rate", minimum=0, required_range=True
        )
        state = self.state(snapshot.transformer_id)
        if event is not None and state is not None and event < state.timestamp:
            inputs.add("LATE_OBSERVATION", "timestamp", "Late event cannot advance forward state.")
            self._emit_thermal(snapshot, inputs, base, None)
            return
        if inputs.issues:
            self._clear(snapshot.transformer_id)
            self._emit_thermal(snapshot, inputs, base, None)
            return
        if not self._check_versions(snapshot, inputs):
            self._clear(snapshot.transformer_id)
            self._emit_thermal(snapshot, inputs, base, None)
            return
        configuration = dict(
            selection=asdict(snapshot.selection),
            policy=asdict(snapshot.policy),
            model_parameters={
                key: asdict(value) for key, value in snapshot.model_parameters.items()
            },
            equipment={key: asdict(value) for key, value in snapshot.equipment.items()},
            case=snapshot.lineage.case_id,
            input_mapping={
                key: dict(
                    original_unit=value.provenance.original_unit,
                    kind=value.quantity_kind,
                    source_id=value.provenance.source_id,
                    semantics=value.provenance.semantics,
                    conversion=value.provenance.conversion_id,
                )
                for key, value in inputs.quantities.items()
                if key.startswith(("environment.", "simulation."))
            },
        )
        try:
            identity = digest(dict(versions=asdict(snapshot.versions), configuration=configuration))
            version_key = (snapshot.transformer_id, tuple(asdict(snapshot.versions).values()))
            if version_key in self._identities and self._identities[version_key] != identity:
                inputs.add(
                    "VERSION_CONTENT_CHANGED",
                    "versions",
                    "An immutable version identity was reused with changed configuration.",
                    True,
                )
                self._emit_thermal(snapshot, inputs, base, None)
                return
            request_id = digest(
                dict(
                    timestamp=event,
                    acquisition=snapshot.lineage.acquisition_reference,
                    forcing=[ta, po, pw],
                    initial={
                        key: asdict(value)
                        for key, value in snapshot.simulation.items()
                        if key.startswith("initial_")
                    },
                )
            )
        except (ValueError, TypeError, InputIssue):
            inputs.add(
                "IDENTITY_RECORD_INVALID",
                "versions",
                "Configuration/source identity cannot be resolved.",
                True,
            )
            self._clear(snapshot.transformer_id)
            self._emit_thermal(snapshot, inputs, base, None)
            return
        if state is not None and event == state.timestamp:
            if request_id == state.request_identity and identity == state.identity:
                for name in THERMAL:
                    base["components"][name] = copy.deepcopy(
                        self._last_components[snapshot.transformer_id][name]
                    )
            else:
                inputs.add(
                    "SEMANTIC_CONFLICT",
                    "timestamp",
                    "Equal-time event identity differs; state is unchanged.",
                )
                self._emit_thermal(snapshot, inputs, base, None)
            return
        self._identities[version_key] = identity
        gap_count = 0 if state is None else state.gap_count
        reset_code = "COLD_START"
        if state is not None and state.identity != identity:
            state = None
            reset_code = "CONFIGURATION_RESET"
        elif state is not None and (event - state.timestamp).total_seconds() > ages[1]:
            state = None
            gap_count += 1
            reset_code = "GAP_RESET"
        if state is None:
            seeds = []
            for key in ("initial_oil_temperature", "initial_winding_temperature"):
                path = "simulation." + key
                quantity = snapshot.simulation.get(key)
                if quantity is None or quantity.value is None:
                    inputs.add(
                        "INITIAL_STATE_REQUIRED",
                        path,
                        "Explicit current-event initial temperature is required.",
                        status="INITIALIZING",
                    )
                    seeds.append(None)
                else:
                    seeds.append(inputs.read(path, "K", "absolute_temperature", configuration=True))
                    try:
                        if utc(quantity.effective_at) != event:
                            inputs.add(
                                "INITIAL_STATE_TIME_MISMATCH",
                                path,
                                "Initial condition must match the reset event.",
                                True,
                            )
                    except InputIssue:
                        pass  # read already records this invalid timestamp
            if not inputs.issues and any(value < lower or value > upper for value in seeds):
                inputs.add(
                    "OUT_OF_RANGE",
                    "simulation.initial_temperature",
                    "Initial conditions exceed the declared model envelope.",
                    True,
                )
            if not inputs.issues:
                state = ThermalState(
                    event,
                    event,
                    seeds[0],
                    seeds[1],
                    ta,
                    po,
                    pw,
                    identity,
                    request_id,
                    tuple(sorted(inputs.references)),
                    gap_count,
                )
                self._states[snapshot.transformer_id] = state
            else:
                self._clear(snapshot.transformer_id)
            inputs.add(
                reset_code,
                "",
                "Initial state is withheld until supported time evolution.",
                status="INITIALIZING",
            )
        else:
            try:
                oil, winding = two_node_step(
                    state.oil_k,
                    state.winding_k,
                    state.ambient_k,
                    state.oil_heat_w,
                    state.winding_heat_w,
                    *parameters,
                    (event - state.timestamp).total_seconds(),
                )
                if not lower <= oil <= upper or not lower <= winding <= upper:
                    raise ValueError("Model range exceeded.")
                state = ThermalState(
                    event,
                    state.started_at,
                    oil,
                    winding,
                    ta,
                    po,
                    pw,
                    identity,
                    request_id,
                    tuple(sorted(set(state.evidence_references) | inputs.references)),
                    gap_count,
                )
                self._states[snapshot.transformer_id] = state
                if (event - state.started_at).total_seconds() < ages[2]:
                    inputs.add(
                        "HISTORY_WARMUP",
                        "history",
                        "Required supported history is incomplete.",
                        status="INITIALIZING",
                    )
            except (ArithmeticError, ValueError, RuntimeError):
                self._clear(snapshot.transformer_id)
                state = None
                inputs.add(
                    "NUMERICAL_FAILURE",
                    "thermal_model",
                    "Calculation failed or exceeded the declared model envelope.",
                    status="MODEL_ERROR",
                )
        self._emit_thermal(snapshot, inputs, base, state)
        if state is not None:
            self._last_components[snapshot.transformer_id] = {
                name: copy.deepcopy(base["components"][name]) for name in THERMAL
            }

    def _emit_thermal(self, snapshot, inputs, base, state):
        values = {name: None for name in THERMAL}
        if state is not None:
            values = dict(
                top_oil_temperature=convert_value(
                    state.oil_k, "K", "DEG_C", "absolute_temperature"
                ),
                hot_spot_temperature=convert_value(
                    state.winding_k, "K", "DEG_C", "absolute_temperature"
                ),
                top_oil_rise=state.oil_k - state.ambient_k,
                winding_hot_spot_gradient=state.winding_k - state.oil_k,
            )
        warning = dict(
            code="SIMPLIFIED_NODE_PROXY",
            message="Idealized controlled-case node estimate; "
            "not a real winding maximum or standards model.",
            paths=[],
        )
        assumptions = [
            dict(
                message="Uniform nodes, constant positive R/C "
                "and explicit previous-sample heat/boundary hold.",
                reference="PROJECT_TWO_NODE_RC_V1",
            )
        ]
        for name in THERMAL:
            base["components"][name] = component(
                name,
                inputs.issues,
                value=values[name],
                model_id=MODEL_ID,
                paths=inputs.quantities,
                references=state.evidence_references if state else inputs.references,
                case_id=snapshot.lineage.case_id,
                state=state,
                warnings=[warning],
                assumptions=assumptions,
            )
