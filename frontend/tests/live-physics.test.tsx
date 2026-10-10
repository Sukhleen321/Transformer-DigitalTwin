import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import { livePhysicsDemoSchema, physicsComponentNames } from '../src/api/livePhysicsDemo';
import { PhysicsPanel } from '../src/components/console/PhysicsPanel';
import { usePhysics } from '../src/hooks/usePhysics';
import computed from './live-physics-computed.json';

function fixture(id = 'DEMO-A', sequence = 3) {
  const data = structuredClone(computed);
  data.transformer_id = id; data.sequence = sequence;
  data.timestamp = new Date(Date.now() - 100).toISOString(); data.published_at = data.timestamp;
  data.evaluated_at = new Date().toISOString();
  return livePhysicsDemoSchema.parse(data);
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.useRealTimers(); });

it.each([
  ['Live physics demo is disabled for this environment', 'Backend demo configuration is disabled'],
  ['No live simulation event available', 'check that the producer is running'],
  ['Transformer not found', 'not registered in this demo backend'],
  ['Not Found', 'backend may be an older build'],
])('explains actual demo API 404: %s', async (message, diagnostic) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'HTTP_ERROR', message: 'Request failed', details: { message, request_id: 'test-only' } } }), {status:404})));
  const { result } = renderHook(() => usePhysics('LIVE-DEMO-A', true, true));
  await waitFor(() => expect(result.current.error).toContain(diagnostic));
  expect(result.current.error).toContain('open its printed frontend URL');
  expect(result.current.error).toContain('LIVE-DEMO-A');
  expect(result.current.data).toBeNull();
});

it('rejects a demo response belonging to a different selected asset', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture('OTHER')), {status:200})));
  await expect(api.livePhysicsDemo('LIVE-DEMO-A')).rejects.toMatchObject({code:'IDENTITY_MISMATCH'});
});

it('does not expose arbitrary backend exception details or change production error behavior', async () => {
  const envelope = {error:{code:'HTTP_ERROR',message:'Request failed',details:{message:'private internals'}}};
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope),{status:404})));
  await expect(api.livePhysicsDemo('LIVE-DEMO-A')).rejects.toMatchObject({message:'Request failed'});
  envelope.error.details.message = 'Live physics demo is disabled for this environment';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope),{status:404})));
  await expect(api.physics('LIVE-DEMO-A')).rejects.toMatchObject({message:'Request failed'});
});

it.each([['2000', 2000], ['invalid', 4000], ['0', 4000], ['11000', 4000]])('uses bounded demo polling configuration %s', async (configured, expected) => {
  vi.stubEnv('VITE_LIVE_PHYSICS_POLL_INTERVAL_MS', configured);
  vi.useFakeTimers();
  const request = vi.spyOn(api, 'livePhysicsDemo').mockImplementation(async () => fixture());
  const { unmount } = renderHook(() => usePhysics('DEMO-A', true, true));
  await act(async () => {});
  expect(request).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(expected - 1));
  expect(request).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(request).toHaveBeenCalledTimes(2);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it('displays ten computed numeric values, units, models, synthetic provenance and times', () => {
  const data = fixture();
  render(<PhysicsPanel state={{ data, loading: false, error: null, retry: vi.fn(), lastSuccess: Date.now() }}/>);
  const rows = screen.getAllByRole('row').slice(1);
  expect(rows).toHaveLength(10);
  expect(screen.getByText('LIVE SIMULATION')).toBeVisible();
  expect(screen.getByText(/Latest update/)).toHaveTextContent('Sequence 3');
  const units = ['°C','°C','°C','K','K','W','1','h','°C','K'];
  rows.forEach((r, i) => {
    const value = r.querySelectorAll('td')[1].textContent!;
    expect(value).toMatch(/\d/); expect(value.endsWith(` ${units[i]}`)).toBe(true);
    expect(r).toHaveTextContent('SYNTHETIC_SIMULATED');
    fireEvent.click(r.querySelector('summary')!);
    expect(r).toHaveTextContent(data.components[physicsComponentNames[i]].model_id);
  });
  expect(screen.getByText(/not insulation life/)).toBeVisible();
});

it.each(['unit', 'target', 'provenance', 'extra', 'missing', 'null-ready', 'stale', 'version'])('rejects invalid demo %s', flaw => {
  const raw = JSON.parse(JSON.stringify(fixture()));
  const c = raw.components.fem_hot_spot_temperature;
  if (flaw === 'unit') c.unit = 'K';
  if (flaw === 'target') c.target = 'RECTANGLE_MAXIMUM';
  if (flaw === 'provenance') c.provenance = 'MEASURED';
  if (flaw === 'extra') raw.components.extra = c;
  if (flaw === 'missing') delete raw.components.hot_spot_difference;
  if (flaw === 'null-ready') c.value = null;
  if (flaw === 'stale') raw.evaluated_at = new Date(Date.parse(raw.timestamp) + 16000).toISOString();
  if (flaw === 'version') raw.demo_contract_version = '2.0.0';
  expect(livePhysicsDemoSchema.safeParse(raw).success).toBe(false);
});

it('polls changing responses only while active, cancels asset/view requests and rejects old events', async () => {
  vi.useFakeTimers(); let sequence = 3;
  const signals: AbortSignal[] = [];
  const spy = vi.spyOn(api, 'livePhysicsDemo').mockImplementation(async (id, signal) => {
    signals.push(signal!); const r = fixture(id, sequence);
    r.components.top_oil_temperature.value! += sequence;
    return r;
  });
  const { result, rerender, unmount } = renderHook(({ id, enabled }) => usePhysics(id, enabled, true), { initialProps: { id: 'DEMO-A', enabled: true } });
  await act(async () => {}); expect(result.current.data?.transformer_id).toBe('DEMO-A');
  const first = result.current.data?.components.top_oil_temperature.value;
  sequence++;
  await act(async () => vi.advanceTimersByTimeAsync(4000));
  expect(result.current.data?.components.top_oil_temperature.value).not.toBe(first);
  sequence = 2;
  await act(async () => vi.advanceTimersByTimeAsync(4000));
  expect(result.current.data).toBeNull(); expect(result.current.error).toContain('Older simulation event');
  sequence = 5; act(() => result.current.retry()); await act(async () => {});
  expect(result.current.data).not.toBeNull();
  const oldSignal = signals.at(-1)!;
  rerender({ id: 'DEMO-B', enabled: true }); expect(oldSignal.aborted).toBe(true);
  expect(result.current.data).toBeNull(); await act(async () => {});
  expect(result.current.data?.transformer_id).toBe('DEMO-B');
  sequence = 3; rerender({ id: 'DEMO-A', enabled: true }); await act(async () => {});
  expect(result.current.data).toBeNull(); expect(result.current.error).toContain('Older simulation event');
  rerender({ id: 'DEMO-B', enabled: false }); const count = spy.mock.calls.length;
  expect(result.current.data).toBeNull(); expect(signals.at(-1)?.aborted).toBe(true);
  await act(async () => vi.advanceTimersByTimeAsync(16000)); expect(spy).toHaveBeenCalledTimes(count);
  unmount(); expect(vi.getTimerCount()).toBe(0);
});

it('withholds numeric data on failed refresh and preserves retry', async () => {
  let fail = false;
  vi.spyOn(api, 'livePhysicsDemo').mockImplementation(async () => { if (fail) throw new Error('Service stopped'); return fixture(); });
  const { result } = renderHook(() => usePhysics('DEMO-A', true, true));
  await waitFor(() => expect(result.current.data).not.toBeNull());
  fail = true; act(() => result.current.retry()); expect(result.current.data).toBeNull();
  await waitFor(() => expect(result.current.error).toBe('Service stopped'));
  expect(result.current.data).toBeNull();
});

it('expires the displayed event even when transport/polling is delayed', async () => {
  vi.useFakeTimers(); const data = fixture();
  render(<PhysicsPanel state={{ data, loading: false, error: null, retry: vi.fn() }}/>);
  expect(screen.getAllByRole('row')[1]).not.toHaveTextContent('Unavailable');
  await act(async () => vi.advanceTimersByTimeAsync(16000));
  screen.getAllByRole('row').slice(1).forEach(row => expect(row).toHaveTextContent('Unavailable'));
  expect(screen.getByRole('status')).toHaveTextContent('stale');
});
