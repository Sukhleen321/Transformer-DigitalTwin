import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import { api } from '../src/api/client';
import { physicsSchema } from '../src/api/physics';
import { usePhysics } from '../src/hooks/usePhysics';
import { PhysicsPanel } from '../src/components/console/PhysicsPanel';
import { App } from '../src/App';
import { controlledResult, unavailableResult, unavailableComponent } from './physics-fixtures';
import { makeLatest, page } from './fixtures';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { resolve, promise }; }
const state = (data = controlledResult()) => ({ data, loading: false, error: null, retry: vi.fn() });

it('parses the real serialized controlled result and all frozen keys, units and kinds', () => {
  const result = controlledResult();
  const frozen = JSON.parse(fs.readFileSync('../docs/contracts/physics-result-v1.schema.json', 'utf8'));
  expect(Object.keys(result.components)).toEqual(frozen.properties.components.required);
  for (const [name, c] of Object.entries(result.components)) {
    const spec = frozen.properties.components.properties[name].allOf[1].properties;
    expect(c.unit).toBe(spec.unit.const); expect(c.result_kind).toBe(spec.result_kind.const);
  }
  expect(result.components.hot_spot_temperature.status).toBe('READY');
  expect(result.components.measured_oil_temperature.value).toBeNull();
});
it('parses an unknown-source unavailable envelope with null identities and no observation', () => {
  const fixtures = JSON.parse(fs.readFileSync('../tests/fixtures/physics/cases.json', 'utf8'));
  const v = { ...fixtures.base_envelope, components: Object.fromEntries(Object.entries(fixtures.components).map(([name, c]) => [name, { ...fixtures.component_defaults, ...(c as object) }])) };
  const result = physicsSchema.parse(v);
  expect(result.timestamp).toBeNull(); expect(result.versions.model_version).toBeNull();
  expect(Object.values(result.components).every(c => c.value === null && c.status !== 'READY')).toBe(true);
});

it.each(['missing component', 'extra member', 'version', 'status', 'unit', 'kind', 'string', 'boolean', 'nonfinite', 'null ready', 'nonready number', 'ready missing evidence', 'ready missing inputs', 'ready missing model', 'missing versions', 'naive time', 'bad date', 'negative loss', 'below absolute zero', 'coverage'])('rejects malformed physics: %s', mode => {
  const v: any = controlledResult(); const c = v.components.hot_spot_temperature;
  switch (mode) {
    case 'missing component': delete v.components.total_loss; break;
    case 'extra member': v.confidence = 1; break;
    case 'version': v.physics_contract_version = '2.0.0'; break;
    case 'status': c.status = 'AVAILABLE'; break;
    case 'unit': c.unit = 'K'; break;
    case 'kind': c.result_kind = 'MEASURED_TELEMETRY'; break;
    case 'string': c.value = '37'; break;
    case 'boolean': c.value = true; break;
    case 'nonfinite': c.value = Infinity; break;
    case 'null ready': c.value = null; break;
    case 'nonready number': c.status = 'INITIALIZING'; break;
    case 'ready missing evidence': c.provenance.evidence_references = []; break;
    case 'ready missing inputs': c.provenance.input_paths = []; break;
    case 'ready missing model': c.provenance.model_id = null; break;
    case 'missing versions': v.versions.parameter_version = null; break;
    case 'naive time': v.timestamp = '2026-10-10T00:01:40'; break;
    case 'bad date': v.timestamp = '2026-02-30T00:00:00Z'; break;
    case 'negative loss': v.components.total_loss.value = -1; break;
    case 'below absolute zero': c.value = -274; break;
    case 'coverage': c.coverage.covered_seconds = c.coverage.expected_seconds + 1; break;
  }
  expect(physicsSchema.safeParse(v).success).toBe(false);
});

it.each(['ageing_acceleration_factor', 'equivalent_ageing_hours', 'fem_hot_spot_temperature', 'hot_spot_difference'] as const)('rejects unsupported READY %s in this release', name => {
  const v = controlledResult(); v.components[name] = { ...v.components[name], ...v.components.hot_spot_temperature, unit: v.components[name].unit, result_kind: v.components[name].result_kind };
  expect(physicsSchema.safeParse(v).success).toBe(false);
});
it('rejects operational thermal and synthetic measured claims', () => {
  const v = controlledResult(); v.context = 'OPERATIONAL'; v.lineage.origin_kind = 'LIVE'; v.lineage.input_verification = 'VERIFIED';
  expect(physicsSchema.safeParse(v).success).toBe(false);
  const synthetic = controlledResult(); synthetic.components.measured_oil_temperature = { ...synthetic.components.hot_spot_temperature, unit: 'DEG_C', result_kind: 'MEASURED_TELEMETRY' };
  expect(physicsSchema.safeParse(synthetic).success).toBe(false);
});
it('uses the shared read client, encoded identity, cancellation and no invented cutoff', async () => {
  const fetcher = vi.fn().mockResolvedValue(response(controlledResult('A/B'))); vi.stubGlobal('fetch', fetcher);
  await api.physics('A/B', new AbortController().signal);
  expect(fetcher.mock.calls[0][0]).toMatch(/\/api\/v1\/transformers\/A%2FB\/physics$/);
  expect(fetcher.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  expect(fetcher.mock.calls[0][1].headers).toEqual({ Accept: 'application/json' });
});
it('rejects cross-asset and malformed responses through existing API errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(controlledResult('OTHER'))).mockResolvedValueOnce(response({})));
  await expect(api.physics('HX-A')).rejects.toMatchObject({ code: 'IDENTITY_MISMATCH' });
  await expect(api.physics('HX-A')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
it.each([404, 409, 422, 500])('surfaces HTTP %s without fabricated physics or fallback', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ error: { code: `ERROR_${status}`, message: `Physics request failed (${status})` } }, status)));
  const { result } = renderHook(() => usePhysics('HX-A', true));
  await waitFor(() => expect(result.current.error).toBe(`Physics request failed (${status})`));
  render(<PhysicsPanel state={result.current}/>);
  expect(screen.getByRole('alert')).toHaveTextContent(`Physics request failed (${status})`);
  expect(screen.queryByRole('table')).not.toBeInTheDocument(); expect(result.current.data).toBeNull();
});

it('labels four simulated proxies, null outputs, units and event/evaluation provenance without field claims', () => {
  render(<PhysicsPanel state={state()}/>);
  const panel = screen.getByRole('region', { name: 'Physics results' });
  expect(within(panel).getAllByRole('row')).toHaveLength(11);
  expect(within(panel).getByText('Controlled-simulation estimates / simplified node proxies')).toBeVisible();
  expect(within(panel).getAllByText('Unavailable', { exact: true }).length).toBeGreaterThanOrEqual(6);
  expect(panel).toHaveTextContent('Simulated reference · numerical benchmark');
  expect(panel).toHaveTextContent('RUL and failure probability are unavailable');
  expect(panel.querySelector('time')).toHaveAttribute('datetime', '2026-10-10T00:01:40Z');
  const summary = within(panel).getByText('Physics identity and provenance'); fireEvent.click(summary);
  expect(summary.closest('details')).toHaveAttribute('open'); expect(panel).toHaveTextContent('physics-equations-1.0.0');
  const evidence = within(panel).getByText('Winding node temperature estimate evidence and assumptions'); fireEvent.click(evidence);
  expect(evidence.closest('details')).toHaveAttribute('open'); expect(panel).toHaveTextContent('SIMPLIFIED_NODE_PROXY');
  for (const summary of within(panel).getAllByText(/evidence and assumptions$/)) {
    if (summary.closest('details')!.open) fireEvent.click(summary);
    fireEvent.click(summary); expect(summary.closest('details')).toHaveAttribute('open');
    fireEvent.click(summary); expect(summary.closest('details')).not.toHaveAttribute('open');
  }
});
it('renders valid measured-only operational result independently of unavailable estimates', () => {
  const v = unavailableResult(); v.context = 'OPERATIONAL'; v.timestamp = '2026-10-10T00:00:00Z'; v.lineage.origin_kind = 'LIVE'; v.lineage.source_kind = 'LIVE'; v.lineage.input_verification = 'VERIFIED';
  const c = v.components.measured_oil_temperature; c.value = 0; c.status = 'READY'; c.reasons = []; c.missing_inputs = []; c.provenance.input_paths = ['observed.oil_temperature']; c.provenance.evidence_references = ['hypothetical-unit-test-sensor'];
  render(<PhysicsPanel state={state(physicsSchema.parse(v))}/>);
  expect(screen.getByRole('row', { name: /Measured oil sensor/ })).toHaveTextContent('0 °C');
  expect(screen.getByRole('row', { name: /Winding node temperature estimate/ })).toHaveTextContent('Unavailable');
  expect(screen.queryByText('Controlled-simulation estimates / simplified node proxies')).not.toBeInTheDocument();
});
it('honors initializing, insufficient, invalid and error statuses independently of ready loss including true zero', () => {
  const v = controlledResult();
  unavailableComponent(v, 'top_oil_temperature', 'INITIALIZING'); unavailableComponent(v, 'hot_spot_temperature', 'INSUFFICIENT_DATA');
  unavailableComponent(v, 'top_oil_rise', 'INVALID_CONFIGURATION'); unavailableComponent(v, 'winding_hot_spot_gradient', 'MODEL_ERROR');
  v.components.total_loss = { ...v.components.top_oil_temperature, ...controlledResult().components.hot_spot_temperature, unit: 'W', value: 0, result_kind: 'CALCULATED_ESTIMATE' };
  render(<PhysicsPanel state={state(physicsSchema.parse(v))}/>);
  expect(screen.getByRole('row', { name: /Current-squared loss estimate/ })).toHaveTextContent('0 W');
  expect(screen.getByRole('row', { name: /Winding node temperature estimate/ })).toHaveTextContent('Insufficient data');
  expect(screen.getByText('Initializing')).toBeVisible(); expect(screen.getByText('Model error', { exact: true })).toBeVisible();
});
it.each(['PHYSICS_DISABLED', 'PHYSICS_RESULT_UNAVAILABLE', 'MODEL_NOT_CONFIGURED', 'STALE_INPUT'])('shows %s with all unavailable components', code => {
  render(<PhysicsPanel state={state(unavailableResult(code, `${code} explanation`))}/>);
  expect(screen.getAllByText(`${code} explanation`)).toHaveLength(10);
  expect(screen.getAllByText('Unavailable', { exact: true }).length).toBeGreaterThanOrEqual(10);
});
it('shows explicit loading and empty states', () => {
  const { rerender } = render(<PhysicsPanel state={{ data: null, loading: true, error: null, retry: vi.fn() }}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Physics: loading');
  rerender(<PhysicsPanel state={{ data: null, loading: false, error: null, retry: vi.fn() }}/>);
  expect(screen.getByText('No physics result available.')).toBeVisible();
});
it('withholds an older READY snapshot when latest telemetry advances without adding automatic requests', () => {
  const s = state(); const { rerender } = render(<PhysicsPanel state={s} latestEvent="2026-10-10T00:01:40Z"/>);
  expect(screen.getByRole('row', { name: /Winding node temperature estimate/ })).toHaveTextContent('°C');
  rerender(<PhysicsPanel state={s} latestEvent="2026-10-10T00:01:41Z"/>);
  expect(screen.getByRole('status')).toHaveTextContent('Newer telemetry is available');
  expect(screen.getByRole('row', { name: /Winding node temperature estimate/ })).toHaveTextContent('Unavailable');
  expect(screen.getAllByText('Refresh required')).toHaveLength(10); expect(s.retry).not.toHaveBeenCalled();
});
it('clears old READY immediately on refresh, on failure and on a newer unavailable result', async () => {
  const pending = deferred<ReturnType<typeof controlledResult>>();
  const spy = vi.spyOn(api, 'physics').mockResolvedValueOnce(controlledResult()).mockImplementationOnce(() => pending.promise).mockResolvedValueOnce(unavailableResult('STALE_INPUT'));
  const { result } = renderHook(() => usePhysics('HX-A', true));
  await waitFor(() => expect(result.current.data).not.toBeNull());
  act(() => result.current.retry()); expect(result.current.data).toBeNull(); expect(result.current.loading).toBe(true);
  await act(async () => pending.resolve(unavailableResult())); expect(result.current.data?.components.hot_spot_temperature.value).toBeNull();
  act(() => result.current.retry()); expect(result.current.data).toBeNull();
  await waitFor(() => expect(result.current.data?.components.hot_spot_temperature.reasons[0].code).toBe('STALE_INPUT'));
  spy.mockRejectedValueOnce(new Error('offline')); act(() => result.current.retry());
  await waitFor(() => expect(result.current.error).toBe('offline')); expect(result.current.data).toBeNull();
});
it('cancels old asset/view requests, ignores late responses and does not poll physics', async () => {
  vi.useFakeTimers(); const old = deferred<ReturnType<typeof controlledResult>>(); const signals: AbortSignal[] = [];
  const spy = vi.spyOn(api, 'physics').mockImplementation((id, signal) => { signals.push(signal!); return id === 'HX-A' ? old.promise : Promise.resolve(controlledResult(id)); });
  const { result, rerender, unmount } = renderHook(({ id, enabled }) => usePhysics(id, enabled), { initialProps: { id: 'HX-A', enabled: true } });
  rerender({ id: 'HX-B', enabled: true }); expect(signals[0].aborted).toBe(true); expect(result.current.data).toBeNull();
  await act(async () => {}); expect(result.current.data?.transformer_id).toBe('HX-B');
  await act(async () => old.resolve(controlledResult())); expect(result.current.data?.transformer_id).toBe('HX-B');
  await act(async () => vi.advanceTimersByTimeAsync(120000)); expect(spy).toHaveBeenCalledTimes(2);
  rerender({ id: 'HX-B', enabled: false }); expect(signals[1].aborted).toBe(true); expect(result.current.data).toBeNull();
  rerender({ id: 'HX-B', enabled: true }); await act(async () => {}); expect(spy).toHaveBeenCalledTimes(3);
  unmount(); expect(signals[2].aborted).toBe(true); expect(vi.getTimerCount()).toBe(0);
});

it('keeps navigation/selector/chart working, requests only in thermal view and wires global refresh and error retry', async () => {
  let fail = false; const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    const u = new URL(input); const id = u.pathname.split('/')[4]; const latest = makeLatest(id);
    if (u.pathname === '/api/v1/transformers') return response(page(['HX-A', 'HX-B'].map(id => makeLatest(id).transformer), 50));
    if (u.pathname.endsWith('/mqtt/status')) return response({ enabled: false, connected: false, queue_depth: 0, committed_count: 0, conflicted_count: 0, dropped_count: 0, last_message_at: null, last_error: null });
    if (u.pathname.endsWith('/latest')) return response(latest);
    if (u.pathname.endsWith('/telemetry')) return response(page([latest.telemetry]));
    if (u.pathname.endsWith('/analytics')) return response(page([latest.analytics]));
    if (u.pathname.endsWith('/alerts') || u.pathname.endsWith('/maintenance')) return response(page([]));
    if (u.pathname.endsWith('/physics')) { calls.push(id); return fail ? response({ error: { code: 'SERVICE_ERROR', message: 'Physics service unavailable' } }, 500) : response(controlledResult(id)); }
    return response({}, 404);
  }));
  render(<App/>); await waitFor(() => expect(screen.getByRole('button', { name: 'Monitor HX-A' })).toBeVisible());
  fireEvent.click(screen.getByRole('button', { name: 'Monitor HX-A' }));
  await waitFor(() => expect(screen.getByRole('region', { name: 'Selected transformer measurements' })).toHaveTextContent('HX-A')); expect(calls).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: 'Thermal & loading', exact: true }));
  await waitFor(() => expect(screen.getByText('Controlled-simulation estimates / simplified node proxies')).toBeVisible()); expect(calls).toEqual(['HX-A']);
  fireEvent.change(screen.getByRole('combobox', { name: 'Trend channel' }), { target: { value: 'Phase currents' } });
  expect(screen.getByRole('img', { name: 'Phase currents event-time trend' })).toBeVisible();
  fireEvent.change(screen.getByRole('combobox', { name: 'Asset', exact: true }), { target: { value: 'HX-B' } });
  await waitFor(() => expect(calls).toEqual(['HX-A', 'HX-B']));
  fail = true; fireEvent.click(screen.getByRole('button', { name: /Refresh/ }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry physics' })).toBeVisible());
  expect(screen.queryByText('Controlled-simulation estimates / simplified node proxies')).not.toBeInTheDocument();
  fail = false; fireEvent.click(screen.getByRole('button', { name: 'Retry physics' }));
  await waitFor(() => expect(screen.getByText('Controlled-simulation estimates / simplified node proxies')).toBeVisible()); expect(calls).toEqual(['HX-A', 'HX-B', 'HX-B', 'HX-B']);
  fireEvent.click(screen.getByRole('button', { name: 'System / source health', exact: true })); expect(screen.queryByRole('region', { name: 'Physics results' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Overview', exact: true })); await waitFor(() => expect(screen.getByRole('button', { name: 'Monitor HX-B' })).toBeVisible()); expect(calls).toHaveLength(4);
});
