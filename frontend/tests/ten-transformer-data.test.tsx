import { afterEach, expect, it, vi } from 'vitest';
import fleet from '../../simulator/config/operational-fleet.json';
import computed from './live-physics-computed.json';

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });

it.each(fleet.assets.map(asset => asset.transformer_id))('same-origin demo client handles %s with numeric synthetic data', async id => {
  vi.stubEnv('VITE_API_BASE_URL', '/');
  vi.resetModules();
  const data = structuredClone(computed);
  data.transformer_id = id;
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  const { api, API_BASE_URL } = await import('../src/api/client');
  expect(API_BASE_URL).toBe('');
  const result = await api.livePhysicsDemo(id);
  expect(fetch.mock.calls[0][0]).toBe(`/api/v1/demo/transformers/${id}/physics`);
  expect(result.transformer_id).toBe(id);
  expect(Object.values(result.components)).toHaveLength(10);
  Object.values(result.components).forEach(c => {
    expect(c.status).toBe('READY');
    expect(typeof c.value).toBe('number');
    expect(c.provenance).toBe('SYNTHETIC_SIMULATED');
  });
  data.transformer_id = 'DIFFERENT-ASSET';
  fetch.mockResolvedValue(new Response(JSON.stringify(data), { status: 200 }));
  await expect(api.livePhysicsDemo(id)).rejects.toMatchObject({ code: 'IDENTITY_MISMATCH' });
});
