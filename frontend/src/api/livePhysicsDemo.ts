import { z } from 'zod';
import type { PhysicsComponentName } from './physics';

export const physicsComponentNames: PhysicsComponentName[] = ['measured_oil_temperature', 'top_oil_temperature',
  'hot_spot_temperature', 'top_oil_rise', 'winding_hot_spot_gradient', 'total_loss',
  'ageing_acceleration_factor', 'equivalent_ageing_hours', 'fem_hot_spot_temperature', 'hot_spot_difference'];

const units = ['DEG_C', 'DEG_C', 'DEG_C', 'K', 'K', 'W', '1', 'h', 'DEG_C', 'K'];
const component = z.object({
  value: z.number().finite().nullable(), unit: z.enum(['DEG_C', 'K', 'W', '1', 'h']),
  status: z.enum(['READY', 'INITIALIZING', 'UNAVAILABLE']),
  provenance: z.literal('SYNTHETIC_SIMULATED'), model_id: z.string().min(1),
  reference: z.literal('docs/live_physics_demo_model.md'), target: z.string().min(1),
}).strict().refine(c => (c.status === 'READY') === (c.value !== null), 'Invalid demo readiness');
const time = z.string().datetime({ offset: true });
export const livePhysicsDemoSchema = z.object({
  demo_contract_version: z.literal('1.0.0'), mode: z.literal('LIVE_SIMULATION'),
  transformer_id: z.string().min(1).max(128), run_id: z.string().regex(/^[0-9a-f]{32}$/),
  sequence: z.number().int().min(1), timestamp: time, published_at: time, evaluated_at: time,
  status: z.enum(['READY', 'INITIALIZING', 'UNAVAILABLE']), reason: z.string().nullable(),
  case_id: z.literal('LIVE_SYNTHETIC_TWO_LAYER_V1'),
  components: z.record(z.string(), component),
  inputs: z.object({ current_a: z.number().finite(), ambient_k: z.number().finite(), oil_heat_w: z.number().finite(), winding_heat_w: z.number().finite() }).strict(),
  maximum_age_seconds: z.literal(15),
}).strict().superRefine((r, ctx) => {
  const names = Object.keys(r.components);
  if (names.length !== 10 || physicsComponentNames.some(name => !names.includes(name))) ctx.addIssue({ code: 'custom', message: 'Exactly ten demo rows required' });
  physicsComponentNames.forEach((name, i) => {
    const c = r.components[name];
    if (!c || c.unit !== units[i]) ctx.addIssue({ code: 'custom', message: 'Demo unit mismatch' });
    if (['hot_spot_temperature', 'fem_hot_spot_temperature', 'hot_spot_difference'].includes(name) && c?.target !== 'AREA_MEAN_WINDING_PROXY') ctx.addIssue({ code: 'custom', message: 'Incompatible target' });
  });
  if (r.status === 'READY' && Object.values(r.components).some(c => c.status !== 'READY')) ctx.addIssue({ code: 'custom', message: 'READY requires ten values' });
  if (r.status === 'UNAVAILABLE' && (!r.reason || Object.values(r.components).some(c => c.value !== null))) ctx.addIssue({ code: 'custom', message: 'Unavailable must withhold values' });
  if (Date.parse(r.timestamp) > Date.parse(r.published_at) || Date.parse(r.published_at) > Date.parse(r.evaluated_at)) ctx.addIssue({ code: 'custom', message: 'Invalid event ordering' });
  if (r.status === 'READY' && Date.parse(r.evaluated_at) - Date.parse(r.timestamp) > 15000) ctx.addIssue({ code: 'custom', message: 'Stale demo result' });
});
export type LivePhysicsDemoResult = z.infer<typeof livePhysicsDemoSchema>;
