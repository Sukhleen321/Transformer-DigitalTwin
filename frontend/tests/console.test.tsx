import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { FeaturePanels } from '../src/components/console/TelemetryPanels';
import { loadPortfolio, loadRegistry } from '../src/hooks/useConsoleData';
import { trendPath, operatingState } from '../src/components/console/presentation';
import { api } from '../src/api/client';
import { makeLatest, page } from './fixtures';
import fleet from '../../simulator/config/operational-fleet.json';
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function fixtureFetch(override?: (url: URL) => Promise<Response> | undefined) {
  const json = (value: unknown) => Promise.resolve(new Response(JSON.stringify(value)));
  vi.stubGlobal('fetch', vi.fn((input: string) => {
    const u = new URL(input), custom = override?.(u); if (custom) return custom;
    if (u.pathname === '/api/v1/transformers') return json(page([makeLatest('HX-A').transformer, makeLatest('HX-B').transformer], 50));
    if (u.pathname.endsWith('/mqtt/status')) return json({enabled:true,connected:true,queue_depth:0,committed_count:10,conflicted_count:0,dropped_count:0,last_message_at:null,last_error:null});
    const id = u.pathname.split('/')[4], latest = makeLatest(id);
    if (u.pathname.endsWith('/latest')) return json(latest);
    if (u.pathname.endsWith('/telemetry')) return json(page([latest.telemetry]));
    if (u.pathname.endsWith('/analytics')) return json(page([latest.analytics]));
    if (u.pathname.endsWith('/alerts') || u.pathname.endsWith('/maintenance')) return json(page([]));
    return Promise.resolve(new Response('{}', {status:404}));
  }));
}
it('opens directly into the API registry overview and changes to equipment monitoring', async () => {
  fixtureFetch(); render(<App/>);
  expect(screen.getByRole('heading', {name:'Transformer overview'})).toBeVisible();
  expect(screen.queryByText(/48 hours|Winning Pitch|grid failures/i)).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button',{name:'Monitor HX-B'})).toBeVisible());
  fireEvent.click(screen.getByRole('button',{name:'Monitor HX-B'}));
  await waitFor(() => expect(screen.getByRole('region',{name:'Selected transformer measurements'})).toHaveTextContent('0 A'));
  expect(screen.getByRole('combobox',{name:'Asset',exact:true})).toHaveValue('HX-B');
  expect(within(screen.getByRole('region',{name:'Transformer monitoring features'})).getAllByRole('article')).toHaveLength(16);
  expect(screen.getByText(/No pressure measurement/)).toBeVisible();
  expect(screen.getByText(/Trip: Cleared/)).toBeVisible();
});
it('switching assets suppresses obsolete measurements and late responses', async () => {
  let resolveOld!: (value: Response) => void;
  fixtureFetch(u => u.pathname === '/api/v1/transformers/HX-A/latest' ? new Promise(r => {resolveOld=r;}) : undefined);
  render(<App/>); await waitFor(() => expect(screen.getByRole('button',{name:'Monitor HX-A'})).toBeVisible());
  fireEvent.click(screen.getByRole('button',{name:'Monitor HX-A'}));
  fireEvent.change(screen.getByRole('combobox',{name:'Asset',exact:true}),{target:{value:'HX-B'}});
  await waitFor(() => expect(screen.getByRole('region',{name:'Selected transformer measurements'})).toHaveTextContent('HX-B'));
  await act(async () => resolveOld(new Response(JSON.stringify(makeLatest('HX-A')))));
  expect(screen.getByRole('combobox',{name:'Asset',exact:true})).toHaveValue('HX-B');
  expect(screen.getByRole('region',{name:'Selected transformer measurements'})).not.toHaveTextContent('HX-A');
});
it('loads every registry page without hardcoding an asset count', async () => {
  const assets=Array.from({length:75},(_,i)=>makeLatest(`REG-${i}`).transformer);
  const spy=vi.spyOn(api,'registry').mockImplementation(async (_s,offset=0)=>({items:assets.slice(offset,offset+50),offset,limit:50,total:75}));
  expect(await loadRegistry(new AbortController().signal)).toHaveLength(75);
  expect(spy).toHaveBeenCalledTimes(2);
});
it('caps portfolio concurrency at three and preserves failed asset last-success time', async () => {
  let concurrent=0, peak=0;
  vi.spyOn(api,'latest').mockImplementation(async id => {concurrent++;peak=Math.max(peak,concurrent);await new Promise(r=>setTimeout(r,2));concurrent--;if(id==='B')throw new Error('offline');return makeLatest(id);});
  const previous={B:{data:makeLatest('B'),error:null,lastSuccess:123}};
  const result=await loadPortfolio(['A','B','C','D','E'],new AbortController().signal,previous);
  expect(peak).toBe(3);expect(result.B.lastSuccess).toBe(123);expect(result.B.error).toBe('offline');expect(result.B.data?.transformer.id).toBe('B');expect(result.A.data?.transformer.id).toBe('A');
});
it('null oil/protection, zero readings and unknown units remain distinct', () => {
  const latest=makeLatest(); latest.telemetry!.oil_level=null;latest.telemetry!.oil_temp_trip=null;latest.telemetry!.acquisition!.field_units.oil_level='UNKNOWN';
  render(<FeaturePanels data={latest}/>);
  expect(screen.getByText('Trip: Unknown contact')).toBeVisible();expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
  latest.telemetry!.oil_temp_trip=0;expect(operatingState({...latest,analytics:null,analytics_availability:{status:'UNAVAILABLE',reasons:['ML_UNAVAILABLE'],state_coverage_loss:true}}).label).toBe('Assessment unavailable');
});
it('searches actual IDs and reports empty or failed registry without local samples', async () => {
  fixtureFetch();render(<App/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Monitor HX-A'})).toBeVisible());
  fireEvent.change(screen.getByRole('textbox',{name:'Search assets'}),{target:{value:'HX-B'}});
  expect(screen.queryByRole('button',{name:'Monitor HX-A'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Monitor HX-B'})).toBeVisible();
});
it('API outage shows errors instead of healthy cards', async () => {
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));render(<App/>);
  await waitFor(()=>expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
  expect(screen.queryByRole('button',{name:/Monitor HX/})).not.toBeInTheDocument();
});
it('chart gaps and unit changes are not joined or filled with zero', () => {
  const t=makeLatest().telemetry!;const records=[t,{...t,timestamp:'2026-10-09T00:00:30Z'},{...t,timestamp:'2026-10-09T00:00:35Z',oil_temperature:null}];
  const path=trendPath(records,'oil_temperature',t.acquisition!.field_units.oil_temperature,20,50,10);
  expect(path.match(/M/g)).toHaveLength(2);expect(path).not.toContain('L');expect(trendPath(records,'oil_temperature','UNKNOWN',20,50,10)).toBe('');
});
it('rejects cross-asset lifecycle data at the client boundary', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(page([{id:1,transformer_id:'WRONG',timestamp:'2026-10-09T00:00:00Z',priority:'WATCH',recommendation:'Other asset',reason_codes:[],status:'OPEN'}])))));
  await expect(api.maintenance('HX-A',new URLSearchParams())).rejects.toThrow('Asset identity mismatch');
});

it('paginates the authoritative ten-asset registry as two disjoint ordered five-card pages', async () => {
  const ids = fleet.assets.map(a => a.transformer_id);
  fixtureFetch(u => u.pathname === '/api/v1/transformers'
    ? Promise.resolve(new Response(JSON.stringify(page(ids.map(id => makeLatest(id).transformer), 50)))) : undefined);
  render(<App/>);
  await waitFor(() => expect(screen.getByRole('button',{name:`Monitor ${ids[0]}`})).toBeVisible());
  const cards = () => within(screen.getByRole('region',{name:'Asset portfolio'})).getAllByRole('button').map(b => b.getAttribute('aria-label')!.replace('Monitor ',''));
  expect(cards()).toEqual(ids.slice(0,5));
  expect(screen.getByText(/Page 1 of 2/)).toBeVisible();
  expect(screen.getByRole('button',{name:'Previous'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Next'})).toBeEnabled();
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  expect(cards()).toEqual(ids.slice(5));
  expect(screen.getByText(/Page 2 of 2/)).toBeVisible();
  expect(screen.getByRole('button',{name:'Next'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:`Monitor ${ids[9]}`}));
  await waitFor(() => expect(screen.getByRole('region',{name:'Selected transformer measurements'})).toHaveTextContent(ids[9]));
  fireEvent.click(screen.getByRole('button',{name:'Asset overview',exact:true}));
  expect(cards()).toEqual(ids.slice(5));
  fireEvent.click(screen.getByRole('button',{name:'Previous'}));
  expect(cards()).toEqual(ids.slice(0,5));
  expect(new Set(ids).size).toBe(10);
});

it('clamps the page after a registry refresh reduces the available inventory', async () => {
  const ids = fleet.assets.map(a => a.transformer_id);
  let inventory = ids;
  fixtureFetch(u => u.pathname === '/api/v1/transformers'
    ? Promise.resolve(new Response(JSON.stringify(page(inventory.map(id => makeLatest(id).transformer),50)))) : undefined);
  render(<App/>);
  await waitFor(() => expect(screen.getByRole('button',{name:`Monitor ${ids[0]}`})).toBeVisible());
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  inventory = ids.slice(0,5);
  fireEvent.click(screen.getByRole('button',{name:/Refresh/}));
  await waitFor(() => expect(screen.getByText(/Page 1 of 1/)).toBeVisible());
  expect(within(screen.getByRole('region',{name:'Asset portfolio'})).getAllByRole('button')).toHaveLength(5);
  expect(screen.getByRole('button',{name:'Next'})).toBeDisabled();
});

it('stops displaying a selected identity removed from the active registry', async () => {
  let inventory = ['HX-A','HX-B'];
  fixtureFetch(u => u.pathname === '/api/v1/transformers'
    ? Promise.resolve(new Response(JSON.stringify(page(inventory.map(id => makeLatest(id).transformer),50)))) : undefined);
  render(<App/>);
  await waitFor(() => expect(screen.getByRole('button',{name:'Monitor HX-A'})).toBeVisible());
  fireEvent.click(screen.getByRole('button',{name:'Monitor HX-A'}));
  await waitFor(() => expect(screen.getByRole('region',{name:'Selected transformer measurements'})).toHaveTextContent('HX-A'));
  inventory = ['HX-B'];
  fireEvent.click(screen.getByRole('button',{name:/Refresh/}));
  await waitFor(() => expect(screen.queryByRole('region',{name:'Selected transformer measurements'})).not.toBeInTheDocument());
  expect(screen.getByRole('combobox',{name:'Asset',exact:true})).toHaveValue('');
});
