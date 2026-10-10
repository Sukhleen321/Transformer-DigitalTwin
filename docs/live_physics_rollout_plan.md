# Proposed rollout after local success — not executed

This follow-up deployment checklist supplements the canonical implementation
plan; it does not add a phase or revise approved reports. Local demonstration
success does not release operational transformer physics.

1. Build a reviewed, immutable source snapshot into a **new** backend image.
   Candidate tag: `transformer-backend:live-physics-demo-v1`; record its actual
   image digest and the source revision/content manifest at build time. This tag
   has **not** been built or pushed by this task: the verified local instance ran
   directly from current source with existing dependencies. Never reuse or
   restart the retained image to substitute for a source build.
2. Provision a separate database/service identity with least privileges and a
   new `live_physics_demo_<uuid hex>` name. Apply migration `0006` only to this
   newly created database. Review migration downgrade: it drops the entire demo
   event ledger; export approved evidence first if needed. The safe rollback is
   to stop the producer, disable demo flags, switch traffic away, and dispose of
   that isolated environment. No retained-data migration is authorized.
3. Configure the demo service with `ENV=local-demo`, `PHYSICS_ENABLED=true`,
   `LIVE_PHYSICS_DEMO_ENABLED=true`, MQTT/reset false, one worker and a dedicated
   source build. Keep real fleet/policy paths unset. The guard requires matching
   configured/bound disposable database names. A production environment cannot
   enable this demo by the boolean flag alone. Secrets belong in the service's
   secret mechanism, never an image or frontend variable.
4. Build an explicitly separate demo frontend with
   `VITE_LIVE_PHYSICS_DEMO_ENABLED=true` and `VITE_API_BASE_URL` set to the approved
   demo backend origin, **without** `/api/v1`. Configure backend CORS for the exact
   browser origin, including scheme/host/port. Production frontend builds retain
   a false/unset demo flag and their existing backend configuration. Vite values
   are build-time settings; restarting a container does not update built assets.
5. Check `/health/ready` and OpenAPI for both physics GET routes. Inspect the
   browser's Network request origin, not merely the configured build variable.
   Smoke-test two successive demo events: changed timestamps/sequences/current
   and computed temperatures, ten numeric components, units, synthetic labels,
   and stale withholding when the producer stops. Check that ordinary physics
   still returns unavailable for assets without eligible production results.
6. Disable safely by stopping the separate producer, setting the demo backend
   flag false, and replacing the demo frontend with its normal build. Confirm
   the demo route returns disabled 404 and all production profiles/telemetry are
   unchanged. Keep demo events out of telemetry, empirical analytics, training
   datasets and operational assets. Discard the dedicated database when its
   approved demonstration ends. Do not remove the synthetic UI labels.

Before any execution, obtain explicit approval for the exact image, environment,
database, migration and traffic changes. Remaining operational blockers: actual
equipment/sensor evidence, verified units and physical parameters, eligible
temperature history, standards full-text equations/applicability, independent
field validation, insulation ageing prerequisites, and a transformer-specific FEM
model with a defensible physical hot-spot target. The known unrelated Phase 7
baseline failures and absent fitted artifacts also remain release blockers for
their respective existing paths. None was fixed or suppressed here.
