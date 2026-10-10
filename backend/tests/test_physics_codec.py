"""Finite, strict, bounded codec and frozen runtime response contract."""

import copy
from datetime import UTC, datetime

import pytest
from ml.physics import PhysicsEstimator
from pydantic import ValidationError

from app.schemas.physics import PhysicsResult
from app.services import physics_codec as codec
from app.services.physics_service import unavailable_snapshot


def test_empty_result_is_finite_frozen_and_deterministic():
    now = datetime(2026, 10, 10, tzinfo=UTC)
    result = PhysicsEstimator().evaluate(unavailable_snapshot("asset", None, now))
    model = PhysicsResult.model_validate(result)
    assert model.model_dump(mode="json") == result
    assert len(result["components"]) == 10
    assert all(c["value"] is None and c["reasons"] for c in result["components"].values())
    assert codec.digest(result) == codec.digest(copy.deepcopy(result))
    for name in result["components"]:
        bad = copy.deepcopy(result)
        bad["components"][name]["value"] = 0.0
        with pytest.raises(ValidationError):
            PhysicsResult.model_validate(bad)
        bad = copy.deepcopy(result)
        bad["components"][name]["unit"] = "J"
        with pytest.raises(ValidationError):
            PhysicsResult.model_validate(bad)


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), object(), {1: "bad"}, "x" * 65537],
    ids=["nan", "infinity", "object", "key", "oversize"],
)
def test_codec_rejects_nonfinite_unsupported_and_oversize(value):
    with pytest.raises(codec.CodecError):
        codec.canonical(value)


@pytest.mark.parametrize("value", [None, "", " x", "x" * 129, "bad\nidentity", "../invalid"])
def test_identity_rejects_ambiguous_and_unbounded(value):
    with pytest.raises(codec.CodecError):
        codec.identity(value)


@pytest.mark.parametrize("value", ["2026-10-10T00:00:00", 1791590400, "yesterday"])
def test_timestamp_decoder_requires_aware_iso(value):
    with pytest.raises(ValidationError):
        codec.time(value)


def test_snapshot_roundtrip_and_exact_members():
    snap = unavailable_snapshot("asset", None, datetime(2026, 10, 10, tzinfo=UTC))
    encoded = codec.encode(snap)
    assert codec.encode(codec.snapshot(encoded)) == encoded
    with pytest.raises(codec.CodecError):
        codec.snapshot(encoded | {"new_field": 1})
    encoded["evidence"] = {str(i): {} for i in range(65)}
    with pytest.raises(codec.CodecError):
        codec.snapshot(encoded)


def test_checkpoint_codec_rejects_malformed_state():
    from ml.physics.types import ThermalState

    now = datetime(2026, 10, 10, tzinfo=UTC)
    valid = codec.encode(
        ThermalState(now, now, 300.0, 300.0, 300.0, 0.0, 0.0, "a" * 64, "b" * 64, ("ref",), 0)
    )
    assert codec.encode(codec.thermal_state(valid)) == valid
    for key, value in [
        ("oil_k", True),
        ("winding_k", -1),
        ("ambient_k", float("inf")),
        ("identity", "short"),
        ("gap_count", True),
        ("evidence_references", [{}]),
        ("evidence_references", ["ref", "ref"]),
    ]:
        with pytest.raises(codec.CodecError):
            codec.thermal_state(valid | {key: value})


@pytest.mark.parametrize("change", ["context", "lineage", "time"])
def test_snapshot_rejects_invalid_transport_metadata(change):
    snap = unavailable_snapshot("asset", None, datetime(2026, 10, 10, tzinfo=UTC))
    encoded = codec.encode(snap)
    if change == "context":
        encoded["context"] = "unsupported"
    elif change == "lineage":
        encoded["lineage"]["input_verification"] = "unsupported"
    else:
        encoded["evaluation_time"] = None
    with pytest.raises(codec.CodecError):
        codec.snapshot(encoded)
