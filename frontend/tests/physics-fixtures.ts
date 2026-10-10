// Hypothetical UI status variants only; never imported by application code.
import controlled from './physics-controlled.json';
import { physicsSchema, type PhysicsComponentName, type PhysicsResult } from '../src/api/physics';

export function controlledResult(id = 'HX-A'): PhysicsResult {
  return physicsSchema.parse({ ...structuredClone(controlled), transformer_id: id });
}
export function unavailableResult(code = 'PHYSICS_DISABLED', message = 'Physics integration is disabled.', id = 'HX-A'): PhysicsResult {
  const result = controlledResult(id);
  for (const c of Object.values(result.components)) {
    c.value = null; c.status = 'INVALID_CONFIGURATION'; c.reasons = [{ code, message, paths: [] }];
  }
  result.timestamp = null;
  return physicsSchema.parse(result);
}
export function unavailableComponent(result: PhysicsResult, name: PhysicsComponentName, status: 'INITIALIZING' | 'INSUFFICIENT_DATA' | 'INVALID_CONFIGURATION' | 'MODEL_ERROR', code = status) {
  const c = result.components[name]; c.value = null; c.status = status;
  c.reasons = [{ code, message: `Component ${status.toLowerCase().replaceAll('_', ' ')}`, paths: [] }];
  return result;
}
