import { z } from 'zod';

// Separate v1 contract: legacy analytics readiness/units are not physics evidence.
const utc = z.iso.datetime().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/);
const id = z.string().min(1);
const ids = z.array(id).refine(v => new Set(v).size === v.length, 'Duplicate references');
const diagnostic = z.strictObject({ code: z.string().regex(/^[A-Z][A-Z0-9_]*$/), message: id, paths: ids });
const coverage = z.strictObject({
  start: utc.nullable(), end: utc.nullable(), covered_seconds: z.number().finite().nonnegative().nullable(),
  expected_seconds: z.number().finite().nonnegative().nullable(), fraction: z.number().min(0).max(1).nullable(),
  gap_count: z.number().int().nonnegative(), missing_fields: ids,
}).superRefine((v, ctx) => {
  if (v.start && v.end && Date.parse(v.start) > Date.parse(v.end)) ctx.addIssue({ code: 'custom', message: 'Reversed coverage' });
  if (v.covered_seconds !== null && v.expected_seconds !== null && v.covered_seconds > v.expected_seconds) ctx.addIssue({ code: 'custom', message: 'Coverage exceeds window' });
  if ((v.expected_seconds === 0 || v.expected_seconds === null) && v.fraction !== null) ctx.addIssue({ code: 'custom', message: 'Undefined coverage fraction' });
});
const provenance = z.strictObject({
  model_id: id.nullable(), equation_ids: ids, input_paths: ids, evidence_references: ids,
  case_id: id.nullable(), comparison_id: id.nullable(), numerical_verification_reference: id.nullable(), mesh_convergence_reference: id.nullable(),
});
function component(unit: 'DEG_C' | 'K' | 'W' | '1' | 'h', kind: 'MEASURED_TELEMETRY' | 'CALCULATED_ESTIMATE' | 'SIMULATED_REFERENCE') {
  const number = unit === 'DEG_C' ? z.number().finite().min(-273.15) : unit === 'K' ? z.number().finite() : z.number().finite().nonnegative();
  return z.strictObject({
    value: number.nullable(), unit: z.literal(unit), result_kind: z.literal(kind),
    status: z.enum(['READY', 'INITIALIZING', 'INSUFFICIENT_DATA', 'INVALID_CONFIGURATION', 'MODEL_ERROR']),
    reasons: z.array(diagnostic), missing_inputs: ids, warnings: z.array(diagnostic),
    assumptions: z.array(z.strictObject({ message: id, reference: id })), coverage, provenance,
  }).superRefine((v, ctx) => {
    if (v.status !== 'READY') {
      if (v.value !== null || !v.reasons.length) ctx.addIssue({ code: 'custom', message: 'Unavailable component needs null and reasons' });
    } else if (v.value === null || v.reasons.length || v.missing_inputs.length || !v.provenance.evidence_references.length || !v.provenance.input_paths.length) {
      ctx.addIssue({ code: 'custom', message: 'Ready component requires a value and evidence' });
    } else if (kind !== 'MEASURED_TELEMETRY' && (!v.provenance.model_id || !v.provenance.equation_ids.length)) {
      ctx.addIssue({ code: 'custom', message: 'Derived value requires model and equations' });
    }
  });
}
export const physicsSchema = z.strictObject({
  physics_contract_version: z.literal('1.0.0'), transformer_id: id.max(128).regex(/^\S(?:.*\S)?$/),
  timestamp: utc.nullable(), evaluated_at: utc, context: z.enum(['OPERATIONAL', 'CONTROLLED_SIMULATION']),
  lineage: z.strictObject({
    source_kind: z.enum(['LIVE', 'REPLAYED', 'SIMULATED', 'UNKNOWN']), origin_kind: z.enum(['LIVE', 'SIMULATED', 'UNKNOWN']),
    input_verification: z.enum(['VERIFIED', 'UNVERIFIED', 'SYNTHETIC', 'MIXED', 'UNKNOWN']),
    acquisition_reference: id.nullable(), origin_transformer_id: id.nullable(), replay_run_id: id.nullable(), evidence_references: ids,
  }),
  versions: z.strictObject({ model_version: id.nullable(), parameter_version: id.nullable(), configuration_version: id.nullable(), preprocessing_version: id.nullable(), equation_registry_version: id.nullable() }),
  components: z.strictObject({
    measured_oil_temperature: component('DEG_C', 'MEASURED_TELEMETRY'),
    top_oil_temperature: component('DEG_C', 'CALCULATED_ESTIMATE'), hot_spot_temperature: component('DEG_C', 'CALCULATED_ESTIMATE'),
    top_oil_rise: component('K', 'CALCULATED_ESTIMATE'), winding_hot_spot_gradient: component('K', 'CALCULATED_ESTIMATE'),
    total_loss: component('W', 'CALCULATED_ESTIMATE'), ageing_acceleration_factor: component('1', 'CALCULATED_ESTIMATE'),
    equivalent_ageing_hours: component('h', 'CALCULATED_ESTIMATE'), fem_hot_spot_temperature: component('DEG_C', 'SIMULATED_REFERENCE'),
    hot_spot_difference: component('K', 'CALCULATED_ESTIMATE'),
  }),
}).superRefine((v, ctx) => {
  for (const [name, c] of Object.entries(v.components)) {
    if (c.status !== 'READY') continue;
    const reject = (message: string) => ctx.addIssue({ code: 'custom', path: ['components', name], message });
    if (!v.timestamp) reject('Ready result needs event time');
    if (c.result_kind === 'MEASURED_TELEMETRY') {
      if (v.context !== 'OPERATIONAL' || !v.versions.preprocessing_version) reject('Measured result requires operational context and source map');
    } else if (Object.values(v.versions).some(x => !x)) reject('Derived result requires all version identities');
    if (v.context === 'OPERATIONAL' && (v.lineage.origin_kind !== 'LIVE' || v.lineage.input_verification !== 'VERIFIED')) reject('Operational result needs verified live origin');
    if (v.context === 'CONTROLLED_SIMULATION' && (v.lineage.origin_kind !== 'SIMULATED' || !c.provenance.case_id)) reject('Controlled result needs simulated origin and case');
    if (['top_oil_temperature', 'hot_spot_temperature', 'top_oil_rise', 'winding_hot_spot_gradient'].includes(name) && v.context !== 'CONTROLLED_SIMULATION') reject('Current thermal model supports controlled simulation only');
    // Match current backend release eligibility; the frozen structural schema alone
    // also describes future capabilities that this release does not provide.
    if (['ageing_acceleration_factor', 'equivalent_ageing_hours', 'fem_hot_spot_temperature', 'hot_spot_difference'].includes(name)) reject('Unsupported in this release');
  }
});
export type PhysicsResult = z.infer<typeof physicsSchema>;
export type PhysicsComponentName = keyof PhysicsResult['components'];
