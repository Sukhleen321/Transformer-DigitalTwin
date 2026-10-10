import { useCallback, useRef, useState } from 'react';
import { api, ApiError, API_BASE_URL } from '../api/client';
import type { PhysicsResult } from '../api/physics';
import type { LivePhysicsDemoResult } from '../api/livePhysicsDemo';
import { usePolling } from './usePolling';

/** Production is one-shot; opt-in demo polls only in enabled monitoring/thermal views.
 * Revision keys remove old values immediately, including failed refreshes. */
export function usePhysics(id: string, enabled: boolean, demo = import.meta.env.VITE_LIVE_PHYSICS_DEMO_ENABLED === 'true') {
  const [revision, setRevision] = useState(0);
  const watermarks = useRef(new Map<string, { run: string; sequence: number; time: number }>());
  const load = useCallback(async (signal: AbortSignal): Promise<PhysicsResult | LivePhysicsDemoResult> => {
    if (!demo) return api.physics(id, signal);
    let result: LivePhysicsDemoResult;
    try { result = await api.livePhysicsDemo(id, signal); }
    catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        const explanation = error.message.includes('disabled') ? 'Backend demo configuration is disabled.'
          : error.message.includes('No live simulation event') ? `No simulation event exists yet for ${id}; check that the producer is running.`
          : error.message.includes('Transformer not found') ? `Asset ${id} is not registered in this demo backend.`
          : 'The demo route or selected asset is unavailable; the backend may be an older build.';
        throw new Error(`${explanation} API: ${API_BASE_URL || 'same origin'}. Start backend/scripts/Start-TenTransformerDemo.ps1 for the MQTT fleet, or Start-LivePhysicsDemo.ps1 for the standalone model; open its printed frontend URL and select a registered synthetic asset (requested: ${id}). (${error.message})`);
      }
      throw error;
    }
    if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    const previous = watermarks.current.get(id);
    const time = Date.parse(result.timestamp);
    if (previous && (time < previous.time || (previous.run === result.run_id && result.sequence < previous.sequence) || (previous.run !== result.run_id && time <= previous.time))) throw new Error('Older simulation event rejected; values unavailable');
    if (!previous && watermarks.current.size >= 128) throw new Error('Demo asset watermark capacity reached; reload this demo session');
    watermarks.current.set(id, { run: result.run_id, sequence: result.sequence, time });
    return result;
  }, [id, demo]);
  const active = enabled && !!id;
  const configuredInterval = Number(import.meta.env.VITE_LIVE_PHYSICS_POLL_INTERVAL_MS);
  const interval = Number.isFinite(configuredInterval) && configuredInterval >= 1000 && configuredInterval <= 10000 ? configuredInterval : 4000;
  const state = usePolling(`physics:${id}:${demo}:${active}:${revision}`, load, demo ? interval : 0, active);
  const retry = useCallback(() => setRevision(v => v + 1), []);
  return { ...state, data: active && !state.loading && !state.error ? state.data : null, retry };
}
