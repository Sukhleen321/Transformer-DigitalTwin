import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { PhysicsFeatureCards } from '../src/components/console/PhysicsFeatureCards';
import { FeaturePanels } from '../src/components/console/TelemetryPanels';
import { livePhysicsDemoSchema, physicsComponentNames } from '../src/api/livePhysicsDemo';
import computed from './live-physics-computed.json';

afterEach(cleanup);
const now = Date.now();
function data() {
  const r = structuredClone(computed);
  r.timestamp = new Date(now - 500).toISOString(); r.published_at = r.timestamp;
  r.evaluated_at = new Date(now - 100).toISOString();
  return livePhysicsDemoSchema.parse(r);
}
const state = () => ({ data: data(), loading: false, error: null as string | null, retry: vi.fn(), lastSuccess: now });

it('appends all ten numeric cards to the same six-card grid with provenance and exact timestamps', () => {
  const s = state();
  render(<FeaturePanels label="Transformer monitoring features"><PhysicsFeatureCards state={s} enabled now={now}/></FeaturePanels>);
  const region = screen.getByRole('region', { name: 'Transformer monitoring features' });
  const cards = within(region).getAllByRole('article');
  expect(cards).toHaveLength(16);
  expect(cards.slice(0,6).map(c => c.querySelector('h3')?.textContent)).toEqual(['Oil-leak detection','Pressure monitoring','Electrical-fault monitoring','Thermal capacity','Overload capacity','Predictive maintenance']);
  const units = ['°C','°C','°C','K','K','W','1','h','°C','K'];
  cards.slice(6).forEach((card,i) => {
    expect(card.parentElement).toBe(region);
    expect(card.querySelector('.feature-value')?.textContent).toMatch(new RegExp(` ${units[i]}$`));
    expect(card).toHaveTextContent('READY'); expect(card).toHaveTextContent('LIVE SIMULATION'); expect(card).toHaveTextContent('SYNTHETIC');
    const times = card.querySelectorAll('time');
    expect(times[0].dateTime).toBe(s.data.timestamp); expect(times[1].dateTime).toBe(s.data.evaluated_at); expect(times[2].dateTime).toBe(new Date(now).toISOString());
    expect(card.dataset.physicsComponent).toBe(physicsComponentNames[i]);
    fireEvent.click(card.querySelector('summary')!); expect(card.querySelector('details')?.open).toBe(true);
  });
  expect(cards[6]).toHaveTextContent('SIMULATED SENSOR'); expect(cards[6]).not.toHaveTextContent('MEASURED');
});

it('keeps component readiness independent when the event is initializing', () => {
  const s = state(); s.data.status = 'INITIALIZING';
  s.data.components.hot_spot_temperature.status = 'INITIALIZING';
  s.data.components.hot_spot_temperature.value = null;
  render(<PhysicsFeatureCards state={s} enabled now={now}/>);
  expect(screen.getByRole('article',{name:'Winding hot-spot temperature estimate'})).toHaveTextContent('INITIALIZING');
  expect(screen.getByRole('article',{name:'Total transformer losses'})).toHaveTextContent('READY');
  expect(screen.getByRole('article',{name:'Total transformer losses'}).querySelector('.feature-value')).not.toHaveTextContent('Unavailable');
});

it.each(['disabled','loading','error','missing','stale'])('withholds every old reading for %s', mode => {
  const s: Omit<ReturnType<typeof state>, 'data'> & {data: ReturnType<typeof data> | null} = state();
  if (mode === 'loading') s.loading = true;
  if (mode === 'error') s.error = 'API disconnected';
  if (mode === 'missing') s.data = null;
  render(<PhysicsFeatureCards state={s} enabled={mode !== 'disabled'} now={mode === 'stale' ? now + 16000 : now}/>);
  screen.getAllByRole('article').forEach(c => expect(c.querySelector('.feature-value')).toHaveTextContent('Unavailable'));
  if (mode === 'error') { fireEvent.click(screen.getByRole('button',{name:'Retry physics'})); expect(s.retry).toHaveBeenCalledOnce(); }
});
