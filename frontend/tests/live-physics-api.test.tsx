/** Explicit real-API check; no browser, screenshots, write requests or fixtures. */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { writeFileSync } from 'node:fs';

const origin = process.env.LIVE_PHYSICS_TEST_BASE_URL;
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs(); vi.resetModules(); });

it.skipIf(!origin)('shared client and hook consume changing real API results without cross-asset or inactive polling', async () => {
  vi.stubEnv('VITE_API_BASE_URL', origin!);
  vi.stubEnv('VITE_LIVE_PHYSICS_DEMO_ENABLED', 'true');
  vi.stubEnv('VITE_LIVE_PHYSICS_POLL_INTERVAL_MS', '4000');
  vi.resetModules();
  const requests = vi.spyOn(globalThis, 'fetch'); // call through to the real API
  const { api } = await import('../src/api/client');
  const { usePhysics } = await import('../src/hooks/usePhysics');
  const { result, rerender, unmount } = renderHook(({id, enabled}) => usePhysics(id, enabled, true), {initialProps:{id:'LIVE-DEMO-A',enabled:true}});
  await waitFor(() => expect(result.current.data?.status).toBe('READY'), {timeout:10000});
  const first = result.current.data!;
  await waitFor(() => expect(result.current.data && 'sequence' in result.current.data ? result.current.data.sequence : 0).toBeGreaterThan('sequence' in first ? first.sequence : 0), {timeout:15000,interval:200});
  const second = result.current.data!;
  expect(first.transformer_id).toBe('LIVE-DEMO-A');
  expect(second.transformer_id).toBe('LIVE-DEMO-A');
  expect(second.timestamp).not.toBe(first.timestamp);
  const expectedUnits = ['DEG_C','DEG_C','DEG_C','K','K','W','1','h','DEG_C','K'];
  const {physicsComponentNames} = await import('../src/api/livePhysicsDemo');
  physicsComponentNames.forEach((name,i) => {
    const component = second.components[name];
    expect(component.status).toBe('READY');
    expect(typeof component.value).toBe('number');
    expect(Number.isFinite(component.value)).toBe(true);
    expect(component.unit).toBe(expectedUnits[i]);
    expect(component.provenance).toBe('SYNTHETIC_SIMULATED');
    if (name !== 'hot_spot_difference') expect(component.value).not.toBe(first.components[name].value);
  });
  if (process.env.LIVE_PHYSICS_TEST_EVIDENCE) writeFileSync(process.env.LIVE_PHYSICS_TEST_EVIDENCE,JSON.stringify({first,second},null,2));
  rerender({id:'LIVE-DEMO-B',enabled:true});
  expect(result.current.data).toBeNull();
  await waitFor(() => expect(result.current.data?.transformer_id).toBe('LIVE-DEMO-B'), {timeout:10000});
  rerender({id:'LIVE-DEMO-B',enabled:false});
  expect(result.current.data).toBeNull();
  const count = requests.mock.calls.length;
  await act(async () => { await new Promise(resolve => setTimeout(resolve,4200)); });
  expect(requests).toHaveBeenCalledTimes(count);
  expect(result.current.data).toBeNull();
  await expect(api.livePhysicsDemo('MISSING')).rejects.toMatchObject({status:404,message:expect.stringContaining('not found')});
  const production = await api.physics('LIVE-DEMO-A');
  expect(Object.values(production.components).every(c=>c.value===null)).toBe(true);
  unmount();
}, 40000);
