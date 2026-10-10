# Consolidated backend API

Default Compose base URL: `http://127.0.0.1:8001`; local uvicorn can use another port.
Interactive documentation: `/docs`; JSON contract: `/openapi.json`; alternative UI: `/redoc`.
The endpoint table below is generated from the running service's OpenAPI, including
path/query/header parameters and defaults. Runtime-configured caps below still apply.

## Canonical data and interpretation

All timestamps require an explicit timezone and normalize to UTC ISO-8601. TIMESTAMPTZ
is used in PostgreSQL. Null means missing and stays null; measured zero stays zero.
Only the exact canonical names in [CONTEXT.md](CONTEXT.md), plus source_name and scenario_id
metadata, are accepted. The three line-to-line voltage fields identified as excluded
in CONTEXT.md, raw source names and unknown keys are rejected. Canonical protection
flags accept 0/1/true/false/null; floats must be finite; phase power factors use [-1,1].
Thermal and oil units are unverified; the backend performs no unit conversion or numeric
range checks on those measurements. No transformer rating is supplied by default.

Risk and predicted-fault labels mean **proxy risk (alarm/trip-based prediction)**.
The stub's numbers are placeholders. Stress without protection flags remains healthy
in the stub; it does not estimate a physical thermal twin. Missing oil_temperature or
oil_level produces INSUFFICIENT_DATA and null analytics. MISSING_CRITICAL means at least
one of oil_temperature, three currents or three phase voltages is null; it is a data
completeness warning, not a protection indication. Single ingestion returns this warning;
batches report completeness in run statistics rather than per-row warnings.

`latest` attaches only the newest telemetry row's own analytics, and exposes data_source,
demo_mode and schema/feature/model versions. For an empty known asset, telemetry and
analytics are null. Demo mode is true for non-null scenario_id or configured case-insensitive
source prefixes (defaults simulator,replay,demo,seed,mqtt,mqtt-simulator,analytics-backfill).
Use it to label the dashboard. These source labels do not change ingestion or ML rules.

## Windows, paging, trends and limits

For telemetry/health/analytics/trends and alert/maintenance lists, use `anchor=latest`
for historical demo data. Default anchor is now. Without explicit from/to, latest
anchoring ends at the asset's newest telemetry timestamp. Explicit bounds take precedence.
Without bounds, the default window is 24 hours (DEFAULT_WINDOW_HOURS); from alone ends
at now, to alone starts 24 hours earlier. Bounds are inclusive, from < to, maximum
MAX_WINDOW_DAYS=31. Literal + in query timestamps must be encoded; use client params.

Pages contain items,total,limit,offset; default limit=500, MAX_PAGE_LIMIT=5000, offset>=0.
Time series use order=asc by default, with deterministic timestamp/ID ties; desc is allowed.
Alerts and maintenance lists ascend by timestamp/ID. Their optional severity/status filters
apply before counts/paging. Scenarios are all-time, sorted by scenario_id. Page totals
are filtered counts before pagination. Concurrent writes can shift offset pages.

Telemetry fields projection accepts canonical identity/measurements plus id, source_name,
scenario_id,is_missing_critical,data_quality_score. Timestamp is always retained; selected
nulls are preserved. schema_version appears in full records but is not selectable.
Unknown, excluded, raw or empty selections are 422. Health/analytics series omit internal
IDs and error_detail and retain null insufficient results.

Trends require comma-separated signals (maximum 8), canonical numeric measurements
excluding protection flags, or anomaly_score,health_index,fault_risk,thermal_residual,
loading_percent. window defaults 24h; presets 1h/6h/24h/7d use 15/120/300/3600-second
buckets. Explicit windows adapt bucket width to at most 301 buckets. Each bucket has
bucket_start,avg,min,max,count. Count is non-null observations; gaps stay null, never
zero-filled. no_data_signals identifies entirely missing signals. protection_events
are separate flagged records, ascending, capped at 500; flags are never averaged.

MAX_BATCH_SIZE defaults 5000. Batch records validate individually, valid rows still
persist, and at most 20 rejected samples identify row_index/field/message without full
payloads. Protection/power-factor failures count as out_of_range_count; non-finite values
and other schema errors count as parse_error_count. Chunks commit 1000 valid records;
a later failure retains committed chunks and marks the run FAILED.

## Writes, lifecycle and replay

POST telemetry returns 201 for new rows, with telemetry_id, analytics and warnings;
an existing (transformer_id,timestamp) returns 200 with duplicate=true and the original
ID, without repeating ML/hooks. run_ml=false stores telemetry only. Batch source_name
query defaults api and fills missing per-record metadata. Single source defaults api.
ML failures still persist telemetry and insufficient analytics, with ML_UNAVAILABLE and
short error_detail. Hook failures preserve telemetry/analytics and report ALERT_HOOK_FAILED.

Transformer POST requires id/name; duplicate IDs are 409. Nameplate fields are nullable
and optional. PATCH distinguishes omitted fields from explicit nulls; name cannot be null.

Alert timestamp is the first occurrence, last_seen_at the last triggering evidence.
Repeated evidence only escalates severity and resets clear_count. OPEN/ACKNOWLEDGED
participate in dedupe. Five eligible clear records resolve by default; late evidence
cannot rewind active alerts. Protection still evaluates insufficient rows; ML rules do
not. Acknowledge OPEN -> ACKNOWLEDGED; repeated acknowledgement is 200, RESOLVED -> 409.
Resolve is idempotent. Latest open_alerts_count counts OPEN only. PLAN/URGENT maintenance
persists once per open priority/reason set; URGENT can coexist with PLAN. Maintenance
remains open after alerts resolve; DONE/DISMISSED requires OPEN, otherwise 409.

Replay POST requires exactly one of records/from_stored, returns 202 run_id and runs in
BackgroundTasks. speed_multiplier=0 avoids delays; positive values scale gaps capped at
five seconds each. Records sort chronologically and commit individually. from_stored
fills only missing analytics, retaining telemetry and existing results. GET replay status
also accepts batch run IDs. See [ingestion.md](ingestion.md) for run quality/gap fields.

## MQTT and reset

Compose broker: localhost:51885, topic `transformer/TX-001/telemetry`, QoS 1. The consumer
subscribes transformer/+/telemetry. Publish canonical JSON object or array; a missing
transformer_id comes from the topic wildcard, and a present ID must match it. Explicit
source_name/scenario_id stay unchanged; missing source defaults mqtt. Invalid array
members reject the whole message before writes. Retries must retain the same timestamp.
The status endpoint reports connection, queue depth, counters and recent sanitized
rejections. Acknowledgement precedes database commit; retain source records for replay.
Counters reset on process restart, and demo database reset does not reset them.

POST /api/v1/admin/demo/reset is 404 unless DEMO_RESET_ENABLED=true. When enabled it
requires X-Admin-Token matching non-empty DEMO_ADMIN_TOKEN; missing/bad/unconfigured token
is 403. ENV=production always refuses reset (403). Optional include_transformers=true
deletes assets too; default false. It deletes all telemetry/analytics/alerts/maintenance/
runs across all assets in one transaction. Stop publishers and finish replays before reset.
This token protects only this destructive demo operation; other endpoints have no auth.
CLI reset requires --yes and also refuses production. See [docker.md](docker.md).

## Errors and readiness

Errors use {error:{code,message,details}}. Validation is 422 with code VALIDATION_ERROR
and a list of location/message/type objects, followed by request_id. Expected HTTP errors
use HTTP_ERROR (404 missing asset/run/id, 409 lifecycle/config conflict). Unexpected errors
are 500 INTERNAL_ERROR with a generic message and no exception/traceback text. All responses
carry X-Request-ID; a safe supplied ID is accepted, otherwise generated. Request logs
contain metadata only. Detail objects contain request_id; null/string details are safely
wrapped. CORS exposes X-Request-ID and allows configured Streamlit origins.

/health returns 200 even when its database check is degraded. /health/ready returns 200
only after startup with working DB, matching Alembic heads and ML ready/explicitly unchecked;
failures are 503 with sanitized details. Stub is ready, Python checks entrypoint importability,
HTTP probes bounded HEAD/GET without inference/body download. MQTT connectivity is reported
separately and is not a readiness requirement. See [hardening.md](hardening.md).

Regenerate the complete reference and captured samples after resetting with
-IncludeTransformers and reseeding:

```powershell
./scripts/demo.ps1 reset -Yes -IncludeTransformers
./scripts/demo.ps1 seed
.venv/Scripts/python.exe scripts/capture_samples.py --base-url http://127.0.0.1:8001
```

This intentionally creates TX-CAPTURE for write/lifecycle examples. Reset including transformers, then reseed before
running it again; it refuses to reuse that asset. The default 2000-row demo is required
for the fixed segment samples.


## All API operations

| Method / path | Parameters and defaults | Success response |
| --- | --- | --- |
| GET `/health` | none | 200 |
| GET `/health/ready` | none | 200 |
| POST `/api/v1/admin/demo/reset` | include_transformers (query, false); X-Admin-Token (header, optional) | 200 |
| POST `/api/v1/telemetry` | run_ml (query, true); JSON body: TelemetryIn | 201 |
| POST `/api/v1/telemetry/batch` | run_ml (query, true); source_name (query, "api"); JSON body: RawTelemetryBatchIn | 200 |
| POST `/api/v1/simulate/replay` | JSON body: ReplayIn | 202 |
| GET `/api/v1/simulate/replay/{run_id}` | run_id (path, required) | 200 |
| GET `/api/v1/ingest/mqtt/status` | none | 200 |
| GET `/api/v1/transformers` | limit (query, 500); offset (query, 0) | 200 |
| POST `/api/v1/transformers` | JSON body: TransformerIn | 201 |
| GET `/api/v1/transformers/{id}` | id (path, required) | 200 |
| PATCH `/api/v1/transformers/{id}` | id (path, required); JSON body: TransformerPatch | 200 |
| GET `/api/v1/transformers/{id}/latest` | id (path, required) | 200 |
| GET `/api/v1/transformers/{id}/telemetry` | id (path, required); order (query, "asc"); fields (query, optional); from (query, optional); to (query, optional); anchor (query, "now"); limit (query, 500); offset (query, 0) | 200 |
| GET `/api/v1/transformers/{id}/health` | id (path, required); order (query, "asc"); from (query, optional); to (query, optional); anchor (query, "now"); limit (query, 500); offset (query, 0) | 200 |
| GET `/api/v1/transformers/{id}/analytics` | id (path, required); order (query, "asc"); from (query, optional); to (query, optional); anchor (query, "now"); limit (query, 500); offset (query, 0) | 200 |
| GET `/api/v1/transformers/{id}/trends` | id (path, required); signals (query, required); window (query, "24h"); from (query, optional); to (query, optional); anchor (query, "now") | 200 |
| GET `/api/v1/scenarios` | limit (query, 500); offset (query, 0) | 200 |
| GET `/api/v1/transformers/{id}/alerts` | id (path, required); severity (query, optional); status (query, optional); from (query, optional); to (query, optional); anchor (query, "now"); limit (query, 500); offset (query, 0) | 200 |
| GET `/api/v1/transformers/{id}/maintenance` | id (path, required); status (query, optional); from (query, optional); to (query, optional); anchor (query, "now"); limit (query, 500); offset (query, 0) | 200 |
| GET `/api/v1/alerts/{id}` | id (path, required) | 200 |
| PATCH `/api/v1/alerts/{id}/acknowledge` | id (path, required) | 200 |
| PATCH `/api/v1/alerts/{id}/resolve` | id (path, required) | 200 |
| GET `/api/v1/maintenance/{id}` | id (path, required) | 200 |
| PATCH `/api/v1/maintenance/{id}` | id (path, required); JSON body: MaintenancePatch | 200 |

## Captured demo responses

These JSON values were captured from the seeded Compose demo by scripts/capture_samples.py. The full bodies are in [samples/api-responses.json](samples/api-responses.json). Page examples retain the first item; trends retain their first populated bucket. These are real response selections. Write samples use TX-CAPTURE; TX-001 is unchanged.

### liveness (HTTP 200)

```json
{
  "status": "ok",
  "db": "ok",
  "schema_version": "1.0.0"
}
```

### ready (HTTP 200)

```json
{
  "status": "ready",
  "db": "ready",
  "migrations": "ready",
  "ml": "ready",
  "details": {}
}
```

### latest (HTTP 200)

```json
{
  "transformer": {
    "rated_power_kva": null,
    "rated_voltage_hv": null,
    "rated_voltage_lv": null,
    "rated_current_a": null,
    "cooling_class": null,
    "oil_type": null,
    "id": "TX-001",
    "name": "Demo transformer",
    "created_at": "2026-10-07T11:56:55.400418Z",
    "updated_at": "2026-10-07T11:56:55.400418Z"
  },
  "telemetry": {
    "transformer_id": "TX-001",
    "timestamp": "2026-01-01T16:39:30Z",
    "phase_voltage_l1": 229.979917,
    "phase_voltage_l2": 229.857268,
    "phase_voltage_l3": 229.970592,
    "current_l1": 84.698494,
    "current_l2": 84.749556,
    "current_l3": 84.634453,
    "neutral_current": 0.115103,
    "oil_temperature": 42.0,
    "winding_temperature": 45.0,
    "ambient_temperature": 22.0,
    "oil_level": 8.0,
    "oil_temp_alarm": 0,
    "oil_temp_trip": 0,
    "magnetic_oil_gauge_alarm": 0,
    "active_power_total": 55.501555,
    "apparent_power_total": 58.422689,
    "reactive_power_total": 18.242479,
    "energy_kwh": 1383.752512,
    "power_factor_l1": 0.95,
    "power_factor_l2": 0.95,
    "power_factor_l3": 0.95,
    "source_name": "seed",
    "scenario_id": "SCN_FAULT",
    "id": 4001,
    "is_missing_critical": false,
    "data_quality_score": 1.0,
    "schema_version": "1.0.0"
  },
  "analytics": {
    "transformer_id": "TX-001",
    "timestamp": "2026-01-01T16:39:30Z",
    "inference_status": "OK",
    "missing_features": [],
    "loading_percent": null,
    "thermal_model_temperature": null,
    "thermal_residual": null,
    "thermal_state": null,
    "anomaly_score": 0.1,
    "anomaly_flag": false,
    "health_index": 90.0,
    "health_components": {
      "thermal": 90.0,
      "electrical": 90.0,
      "loading": 90.0,
      "oil": 90.0,
      "alarm": 90.0,
      "anomaly": 90.0
    },
    "health_reason_codes": [],
    "fault_risk": 0.05,
    "predicted_fault": null,
    "prediction_confidence": null,
    "maintenance_priority": "NORMAL",
    "maintenance_recommendation": "Continue routine monitoring.",
    "reason_codes": [],
    "schema_version": "1.0.0",
    "feature_version": "1.0.0",
    "model_version": "stub-0.0.0",
    "error_detail": null
  },
  "open_alerts_count": 0,
  "demo_mode": true,
  "data_source": {
    "source_name": "seed",
    "scenario_id": "SCN_FAULT"
  },
  "schema_version": "1.0.0",
  "feature_version": "1.0.0",
  "model_version": "stub-0.0.0"
}
```

### telemetry_projection (HTTP 200)

```json
{
  "items": [
    {
      "timestamp": "2026-01-01T00:00:00Z",
      "current_l1": 85.024504,
      "oil_temperature": 42.0,
      "source_name": "seed"
    }
  ],
  "total": 2000,
  "limit": 3,
  "offset": 0
}
```

### health (HTTP 200)

```json
{
  "items": [
    {
      "timestamp": "2026-01-01T00:00:00Z",
      "health_index": 90.0,
      "health_components": {
        "thermal": 90.0,
        "electrical": 90.0,
        "loading": 90.0,
        "oil": 90.0,
        "alarm": 90.0,
        "anomaly": 90.0
      },
      "health_reason_codes": [],
      "inference_status": "OK"
    }
  ],
  "total": 2000,
  "limit": 3,
  "offset": 0
}
```

### alerts (HTTP 200)

```json
{
  "items": [
    {
      "id": 9,
      "transformer_id": "TX-001",
      "analytics_id": 3881,
      "telemetry_id": 3881,
      "timestamp": "2026-01-01T11:40:00Z",
      "severity": "CRITICAL",
      "alert_type": "ANOMALOUS_PATTERN",
      "trigger": "anomaly_flag",
      "evidence": {
        "anomaly_flag": true,
        "anomaly_score": 0.95
      },
      "threshold_or_reason": "anomaly_flag=true; ALERT_ANOMALY_CRITICAL=0.9",
      "recommended_action": "Review the anomalous pattern and available sensor evidence.",
      "status": "RESOLVED",
      "last_seen_at": "2026-01-01T15:39:30Z",
      "created_at": "2026-10-07T11:57:03.069859Z",
      "resolved_at": "2026-01-01T15:42:00Z",
      "acknowledged_at": null
    }
  ],
  "total": 8,
  "limit": 3,
  "offset": 0
}
```

### maintenance (HTTP 200)

```json
{
  "items": [
    {
      "id": 3,
      "transformer_id": "TX-001",
      "analytics_id": 3402,
      "timestamp": "2026-01-01T11:40:00Z",
      "priority": "PLAN",
      "recommendation": "Plan an inspection of the indicated protection condition.",
      "reason_codes": [
        "HIGH_OIL_TEMP",
        "OIL_TEMP_ALARM"
      ],
      "status": "OPEN",
      "created_at": "2026-10-07T11:57:03.069859Z"
    }
  ],
  "total": 2,
  "limit": 3,
  "offset": 0
}
```

### segment_alarm (HTTP 200)

```json
{
  "items": [
    {
      "transformer_id": "TX-001",
      "timestamp": "2026-01-01T12:05:00Z",
      "phase_voltage_l1": 227.088529,
      "phase_voltage_l2": 227.000666,
      "phase_voltage_l3": 226.887762,
      "current_l1": 185.099371,
      "current_l2": 185.210407,
      "current_l3": 185.022727,
      "neutral_current": 0.18768,
      "oil_temperature": 67.25261,
      "winding_temperature": 74.461378,
      "ambient_temperature": 22.0,
      "oil_level": 8.0,
      "oil_temp_alarm": 1,
      "oil_temp_trip": 0,
      "magnetic_oil_gauge_alarm": 0,
      "active_power_total": 119.753411,
      "apparent_power_total": 126.056222,
      "reactive_power_total": 39.361043,
      "energy_kwh": 852.6342,
      "power_factor_l1": 0.95,
      "power_factor_l2": 0.95,
      "power_factor_l3": 0.95,
      "source_name": "seed",
      "scenario_id": "SCN_FAULT",
      "id": 3452,
      "is_missing_critical": false,
      "data_quality_score": 1.0,
      "schema_version": "1.0.0"
    }
  ],
  "total": 1,
  "limit": 1,
  "offset": 0
}
```

### segment_trip (HTTP 200)

```json
{
  "items": [
    {
      "transformer_id": "TX-001",
      "timestamp": "2026-01-01T14:35:00Z",
      "phase_voltage_l1": 225.781268,
      "phase_voltage_l2": 225.945676,
      "phase_voltage_l3": 226.105224,
      "current_l1": 215.252418,
      "current_l2": 214.170457,
      "current_l3": 215.1183,
      "neutral_current": 1.081961,
      "oil_temperature": 74.768267,
      "winding_temperature": 83.229645,
      "ambient_temperature": 22.0,
      "oil_level": 8.0,
      "oil_temp_alarm": 0,
      "oil_temp_trip": 1,
      "magnetic_oil_gauge_alarm": 0,
      "active_power_total": 138.348713,
      "apparent_power_total": 145.630224,
      "reactive_power_total": 45.473023,
      "energy_kwh": 1175.070392,
      "power_factor_l1": 0.95,
      "power_factor_l2": 0.95,
      "power_factor_l3": 0.95,
      "source_name": "seed",
      "scenario_id": "SCN_FAULT",
      "id": 3752,
      "is_missing_critical": false,
      "data_quality_score": 1.0,
      "schema_version": "1.0.0"
    }
  ],
  "total": 1,
  "limit": 1,
  "offset": 0
}
```

### telemetry_post (HTTP 201)

```json
{
  "telemetry_id": 4002,
  "analytics": {
    "transformer_id": "TX-CAPTURE",
    "timestamp": "2026-01-01T00:21:00Z",
    "inference_status": "OK",
    "missing_features": [],
    "loading_percent": null,
    "thermal_model_temperature": null,
    "thermal_residual": null,
    "thermal_state": null,
    "anomaly_score": 0.75,
    "anomaly_flag": true,
    "health_index": 55.0,
    "health_components": {
      "thermal": 55.0,
      "electrical": 90.0,
      "loading": 90.0,
      "oil": 90.0,
      "alarm": 55.0,
      "anomaly": 25.0
    },
    "health_reason_codes": [
      "OIL_TEMP_ALARM",
      "HIGH_OIL_TEMP"
    ],
    "fault_risk": 0.6,
    "predicted_fault": "THERMAL_STRESS",
    "prediction_confidence": 0.8,
    "maintenance_priority": "PLAN",
    "maintenance_recommendation": "Plan an inspection of the indicated protection condition.",
    "reason_codes": [
      "OIL_TEMP_ALARM",
      "HIGH_OIL_TEMP"
    ],
    "schema_version": "1.0.0",
    "feature_version": "1.0.0",
    "model_version": "stub-0.0.0",
    "error_detail": null
  },
  "warnings": []
}
```

### telemetry_duplicate (HTTP 200)

```json
{
  "duplicate": true,
  "telemetry_id": 4002
}
```

### telemetry_batch (HTTP 200)

```json
{
  "run_id": 10,
  "row_count": 1,
  "inserted_count": 1,
  "duplicate_count": 0,
  "parse_error_count": 0,
  "out_of_range_count": 0,
  "errors_sample": []
}
```

### replay_start (HTTP 202)

```json
{
  "run_id": 11
}
```

### mqtt_status (HTTP 200)

```json
{
  "enabled": true,
  "connected": true,
  "host": "mqtt",
  "port": 1883,
  "topic": "transformer/+/telemetry",
  "qos": 1,
  "queue_depth": 0,
  "received_count": 1,
  "ingested_count": 1,
  "duplicate_count": 0,
  "rejected_count": 0,
  "dropped_count": 0,
  "error_count": 0,
  "last_message_at": "2026-10-07T11:57:00.141560Z",
  "last_error": null,
  "recent_rejections": []
}
```

### validation_error (HTTP 422)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "location": [
          "query",
          "limit"
        ],
        "message": "Input should be greater than 0",
        "type": "greater_than"
      },
      {
        "request_id": "5dc3a9b2-4388-448f-8cbc-9482de3c8798"
      }
    ]
  }
}
```

### Four-signal trends (selected buckets)

```json
{
  "start": "2025-12-31T16:39:30Z",
  "end": "2026-01-01T16:39:30Z",
  "bucket_seconds": 300,
  "signals": {
    "oil_temperature": [
      {
        "bucket_start": "2025-12-31T23:59:30Z",
        "avg": 42.0,
        "min": 42.0,
        "max": 42.0,
        "count": 9
      }
    ],
    "current_l1": [
      {
        "bucket_start": "2025-12-31T23:59:30Z",
        "avg": 84.971392,
        "min": 84.500138,
        "max": 85.248396,
        "count": 9
      }
    ],
    "health_index": [
      {
        "bucket_start": "2025-12-31T23:59:30Z",
        "avg": 90.0,
        "min": 90.0,
        "max": 90.0,
        "count": 9
      }
    ],
    "fault_risk": [
      {
        "bucket_start": "2025-12-31T23:59:30Z",
        "avg": 0.049999999999999996,
        "min": 0.05,
        "max": 0.05,
        "count": 9
      }
    ]
  },
  "no_data_signals": [],
  "protection_events": [
    {
      "timestamp": "2026-01-01T11:40:00Z",
      "oil_temp_alarm": 1,
      "oil_temp_trip": 0,
      "magnetic_oil_gauge_alarm": 0
    }
  ]
}
```

## Operational fleet scope (10 October 2026)

`GET /api/v1/transformers` defaults to `scope=active`. When
`OPERATIONAL_FLEET_FILE` is configured, total/limit/offset use only that ordered
roster. This demo references `simulator/config/operational-fleet.json`, shared with
the source/bridge. `scope=all` retains the complete historical registry; individual
lookup/history/receipts still accept historical IDs. Without a configured fleet,
legacy all-registry behavior is retained. Invalid fleet configuration fails closed.
There is no database deletion, relabelling, active-flag migration or ingestion
restriction on preserved legacy spool records. New source startup idempotently
registers fictional nameplates; conflicting existing values are not overwritten.
See [the current fleet report](../../docs/hackathon_readiness/execution/TEN_TRANSFORMER_FLEET.md).

## Physics read resource

GET `/api/v1/transformers/{transformer_id}/physics` returns the separate frozen
physics envelope 1.0.0. Optional `at` is an aware event cutoff; search is bounded
to the preceding 31 days and one matching telemetry/physics event. All ten
components retain units, status, reasons, coverage and provenance. Unavailable
values are null. Existing public-read authentication, X-Request-ID and error
envelopes apply: 404 unknown asset, 409 source identity conflict, 422 invalid
query, sanitized 500 internal failure. There is no write operation.

Controlled thermal results are synthetic two-node proxies. Operational thermal,
ageing, FEM hot-spot and comparison remain unavailable. Integration disabled
or no explicit profile/result gives a complete unavailable envelope. Full rules:
[physics integration](../../docs/physics_integration.md).
