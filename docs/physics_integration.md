# Phase 5 persistence and read boundary

Design recorded before implementation, 10 October 2026. The sole specification
is the [canonical plan](../Transformer_DigitalTwin_Physics_First_Implementation_Plan.md)
and frozen [physics contract](physics_contract.md). Approved Phase 2–4 numerical
code and restrictions remain intact; no frontend work in this phase.

## Storage and ownership

Use the existing PostgreSQL/SQLAlchemy/Alembic stack. Migration 0005 adds four
empty tables: asset-scoped immutable physics_records (model, equation-registry,
parameter, configuration, source-map and evidence identities), physics_profiles
(active configuration pointer), physics_events (normalized input and result),
and physics_checkpoints (event watermark and thermal state). No new dependency,
database, equation, physical default, fixture installation or legacy schema field.

PHYSICS_ENABLED defaults false. Apply migrations before enabling ingestion.
Unconfigured assets have no automatic profile. Publication is an internal
Python operation using an explicit typed Snapshot template and expected source;
no HTTP write resource. Synthetic templates cannot be published OPERATIONAL.
Published IDs cannot change content; conflicting reuse raises 409. PostgreSQL
triggers prevent record update/deletion and event-result updates. Activation
and immutable records publish together in the caller's transaction.

Ingestion uses the existing transformer row lock, stages each configured
asset's result/checkpoint in its telemetry transaction, and never mutates a
global physics runtime. A fresh estimator restores only its checked asset
state. SQL rollback removes all candidate writes; commit is the only durable
installation. Checkpoints bind asset, event, exact input/result digests, codec
and model versions. Recovery from restart reads SQL, not process memory.

Exact retries reuse stored events and never reintegrate; conflicting telemetry
timestamps preserve the existing 409 semantics. Late telemetry remains stored
under existing ingestion rules but cannot advance the physics state. An invalid
forward observation clears continuity rather than carrying a previous READY
temperature through it. Version/gap resets require a new explicit seed at the
reset event; old seeds are not moved to the current time. Corrupt/incompatible
checkpoints quarantine thermal outputs until deliberate profile reset/recovery.
GET also withholds thermal outputs when the selected checkpoint is corrupt.
An intervening accepted event without physics processing breaks continuity.

Records have a 64 KiB encoded-object cap, 64 evidence references per profile and
4096 immutable records per asset. Published records are retained permanently
for resolvability. Event retention is at most 4096 entries per asset and 31 days
of receipt time, preserving the current checkpoint event. These are storage
limits, not inferred equipment policies. No unlimited history is replayed.

## Read selection and eligibility

GET /api/v1/transformers/{transformer_id}/physics has optional `at` (aware UTC
event cutoff); omission uses trusted current UTC. It selects one telemetry row
in the preceding 31-day event window using the existing asset/time index and
one matching physics event. It never substitutes an older calculated event
when the newest selected telemetry is unprocessed, late or unavailable.
GET performs no publication, writes, state advance or FEM solve.

OPERATIONAL freshness uses trusted current time even for historical cutoffs;
CONTROLLED_SIMULATION uses the explicitly requested event cutoff, or current
time if omitted. Public evaluated_at is current server read time; event time
remains the source timestamp. Receipt time is stored separately and remains
available through existing telemetry/receipt resources, not a new frozen field.
Stale or unresolved data nulls affected outputs with reasons. Missing profile
or disabled integration returns a complete unavailable v1 envelope, not zero.

Source name/origin/replay identity and source-map identity are checked against
the profile. No raw OTI/ATI unit or winding-contact semantics are guessed. Source
unit/verification mismatches are ineligible. Boundary/observed values come from
their declared mapped telemetry fields; explicit constant controlled heat
inputs come from the synthetic profile, with current event timestamps and
previous-sample hold. Initial conditions retain their explicit seed times.
Profiles do not read fictional ratings from existing fleet defaults.

The route uses existing public-read/authentication, error-envelope and
X-Request-ID conventions: 404 unknown asset, 422 malformed query, 409 source
identity conflict, sanitized 500 internal failure. Successful 200 responses may
contain unavailable components. All ten keys and fixed units remain unchanged.

Two-node estimates retain SIMPLIFIED_NODE_PROXY warnings and controlled context.
Operational standard thermal estimates, ageing, RUL, probability, FEM hot-spot
and comparison remain unavailable. FEM stays an independent simulated reference;
the server never runs it on read or ingestion.

## Risks and limits

Migrate before enabling the hook. Downgrade destroys only new physics data;
published records intentionally block deletion/reuse of their IDs while active.
Retention can discard old retry diagnostics, but checkpoint/event barriers still
prevent late reintegration. No implicit backfill of already ingested observations.
Previously unprocessed latest telemetry is explicitly unavailable.

Profile publication is trusted operator work, not automatic verification of
sensor documents or URL contents. Digests detect accidental content corruption;
they are not signatures or a defence against a privileged database attacker.
Database access/roles and existing deployment authentication remain operator
responsibilities. No additional secrets or evidence bodies are exposed by GET.

Tests, exact examples, migration results, commands and remaining prerequisites
are recorded in the [Phase 5 report](phase5_report.md).

The protected checkpoint event counts toward the 4096-event cap, including
quarantine. Its receipt may exceed 31 days so restart recovery has its exact
pair; other old events are pruned on configured ingestion, not by a background
job. Immutable identities are never pruned. Asset totals and legacy telemetry
retention remain deployment responsibilities. Publication and ingestion both
serialize through the existing transformer row lock.

Profile recovery is an explicit operator transaction:

```python
from app.services.physics_service import publish_profile
# supplied_snapshot must use a NEW configuration ID and activation after the
# checkpoint watermark, with explicit seeds at the new event. No defaults.
publish_profile(session, supplied_snapshot, source_name=supplied_source, recover=True)
session.commit()
```

Model/registry records include byte digests of the approved foundation sources.
A different runtime source, even with equivalent formatting, is incompatible
with that published identity and withholds results. This requires deliberate
release/version review; it is not automatic code migration. Version IDs are
asset-scoped, each kind in a separate namespace. Configuration records retain
all evidence IDs, not just lineage references. The codec is `physics-state-v1`.

Legacy demo reset/seed workflows already have unresolved receipt-FK failures.
Physics publication also intentionally retains asset/evidence ownership and
blocks asset deletion while immutable records exist; do not use demo reset as
a physics recovery mechanism. No changes to those existing reset endpoints
were made. Default-disabled/unconfigured ingestion has no physics side effects.

