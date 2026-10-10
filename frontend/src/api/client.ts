import { z } from 'zod';
import * as c from './contracts';
import { physicsSchema } from './physics';
import { livePhysicsDemoSchema } from './livePhysicsDemo';

export class ApiError extends Error {
  constructor(message: string, public status: number, public code: string) { super(message); }
}
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001').replace(/\/$/, '');
async function parseRequest<T>(path: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try { response = await fetch(`${API_BASE_URL}/api/v1${path}`, { signal, headers: { Accept: 'application/json' } }); }
  catch (error) { if (signal?.aborted) throw error; throw new ApiError('API disconnected or unreachable', 0, 'DISCONNECTED'); }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const error = z.object({ error: z.object({ code: z.string(), message: z.string() }) }).safeParse(body);
    // This demo route has three safe public setup diagnostics in the existing
    // error envelope. Other endpoints retain their established error behavior.
    const diagnostic = path.startsWith('/demo/transformers/') && response.status === 404
      ? z.object({ error: z.object({ details: z.object({ message: z.enum([
        'Live physics demo is disabled for this environment', 'No live simulation event available', 'Transformer not found',
      ]) }) }) }).safeParse(body) : null;
    if (diagnostic?.success) throw new ApiError(diagnostic.data.error.details.message, response.status, error.success ? error.data.error.code : 'HTTP_ERROR');
    throw new ApiError(error.success ? error.data.error.message : `API HTTP ${response.status}`, response.status, error.success ? error.data.error.code : 'HTTP_ERROR');
  }
  const value: unknown = await response.json().catch(() => null);
  const result = schema.safeParse(value);
  if (!result.success) throw new ApiError('API response does not match the expected contract', response.status, 'INVALID_RESPONSE');
  return result.data;
}
export async function request<T>(path: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 10000);
  try { return await parseRequest(path, schema, controller.signal); }
  catch (error) {
    if (controller.signal.aborted && !signal?.aborted) throw new ApiError('API request timed out', 0, 'TIMEOUT');
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
const assetPath = (id: string) => `/transformers/${encodeURIComponent(id)}`;
const pageQuery = (offset: number, limit: number) => new URLSearchParams({ limit: String(limit), offset: String(offset) });
function resourceIdentity<T extends { transformer_id: string }>(value: T, id: string): T {
  if (value.transformer_id !== id) throw new ApiError('Asset identity mismatch', 200, 'IDENTITY_MISMATCH');
  return value;
}
export const api = {
  livePhysicsDemo: async (id: string, signal?: AbortSignal) => resourceIdentity(await request(`/demo${assetPath(id)}/physics`, livePhysicsDemoSchema, signal), id),
  physics: async (id: string, signal?: AbortSignal) => resourceIdentity(await request(`${assetPath(id)}/physics`, physicsSchema, signal), id),
  registry: (signal?: AbortSignal, offset = 0) => request(`/transformers?${pageQuery(offset, 50)}`, c.pageSchema(c.assetSchema), signal),
  latest: async (id: string, signal?: AbortSignal) => {
    const value = await request(`${assetPath(id)}/latest`, c.latestSchema, signal);
    if (value.transformer.id !== id || (value.telemetry && value.telemetry.transformer_id !== id) || (value.analytics?.transformer_id && value.analytics.transformer_id !== id)) throw new ApiError('Asset identity mismatch', 200, 'IDENTITY_MISMATCH');
    return value;
  },
  telemetry: (id: string, query: URLSearchParams, signal?: AbortSignal) => request(`${assetPath(id)}/telemetry?${query}`, c.pageSchema(c.telemetrySchema), signal),
  analytics: (id: string, query: URLSearchParams, signal?: AbortSignal) => request(`${assetPath(id)}/analytics?${query}`, c.pageSchema(c.analyticsPointSchema), signal),
  trends: (id: string, query: URLSearchParams, signal?: AbortSignal) => request(`${assetPath(id)}/trends?${query}`, c.trendSchema, signal),
  alerts: async (id: string, query: URLSearchParams, signal?: AbortSignal) => {
    const page = await request(`${assetPath(id)}/alerts?${query}`, c.pageSchema(c.alertSchema), signal);
    page.items.forEach(item => resourceIdentity(item, id)); return page;
  },
  maintenance: async (id: string, query: URLSearchParams, signal?: AbortSignal) => {
    const page = await request(`${assetPath(id)}/maintenance?${query}`, c.pageSchema(c.maintenanceSchema), signal);
    page.items.forEach(item => resourceIdentity(item, id)); return page;
  },
  mqtt: (signal?: AbortSignal) => request('/ingest/mqtt/status', c.mqttSchema, signal),
  // H06 persisted analytics resources; no browser calculation fallback.
  projection: async (id: string, signal?: AbortSignal) => resourceIdentity(await request(`${assetPath(id)}/rul/projection`, c.projectionSchema, signal),id),
  rul: async (id: string, signal?: AbortSignal) => resourceIdentity(await request(`${assetPath(id)}/rul`, c.rulResourceSchema, signal),id),
  energy: async (id: string, signal?: AbortSignal, query = new URLSearchParams({window:'1h',anchor:'latest'})) => resourceIdentity(await request(`${assetPath(id)}/energy?${query}`, c.energySchema, signal),id),
};

export function historyWindow(timestamp: string | null): URLSearchParams {
  const end = timestamp ? new Date(timestamp) : new Date();
  return new URLSearchParams({ from: new Date(end.getTime() - 3600000).toISOString(), to: end.toISOString(), anchor: 'latest', order: 'asc', limit: '100', offset: '0' });
}
