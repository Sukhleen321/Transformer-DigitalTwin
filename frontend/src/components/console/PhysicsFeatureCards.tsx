import { Activity, Clock, Droplets, Flame, GitCompareArrows, Thermometer, Zap } from 'lucide-react';
import { physicsComponentNames } from '../../api/livePhysicsDemo';
import type { PhysicsComponentName } from '../../api/physics';
import type { usePhysics } from '../../hooks/usePhysics';
import { Badge, EventTime } from './TelemetryPanels';
import { valueLabel } from './presentation';

const features: Record<PhysicsComponentName, { title: string; unit: string; icon: typeof Thermometer; explanation: string; provenance: string }> = {
  measured_oil_temperature: { title: 'Simulated oil sensor temperature', unit: '°C', icon: Droplets, explanation: 'Synthetic sensor input; response model is documented for the selected demo.', provenance: 'SIMULATED SENSOR' },
  top_oil_temperature: { title: 'Top-oil temperature estimate', unit: '°C', icon: Thermometer, explanation: 'Simplified oil-node proxy in the synthetic thermal case.', provenance: 'SIMULATED ESTIMATE' },
  hot_spot_temperature: { title: 'Winding hot-spot temperature estimate', unit: '°C', icon: Thermometer, explanation: 'Winding mean-node proxy; not an equipment hot-spot measurement.', provenance: 'SIMULATED ESTIMATE' },
  top_oil_rise: { title: 'Oil-node temperature rise', unit: 'K', icon: Thermometer, explanation: 'Oil-node temperature above the declared demo ambient.', provenance: 'SIMULATED ESTIMATE' },
  winding_hot_spot_gradient: { title: 'Winding-to-oil temperature gradient', unit: 'K', icon: Activity, explanation: 'Temperature difference between winding and oil nodes.', provenance: 'SIMULATED ESTIMATE' },
  total_loss: { title: 'Total transformer losses', unit: 'W', icon: Zap, explanation: 'Current-squared loss calculation using fictional reference inputs.', provenance: 'SIMULATED ESTIMATE' },
  ageing_acceleration_factor: { title: 'Ageing acceleration factor', unit: '1', icon: Flame, explanation: 'Illustrative temperature index; not standards-based insulation ageing.', provenance: 'ILLUSTRATIVE DEMO' },
  equivalent_ageing_hours: { title: 'Equivalent ageing hours', unit: 'h', icon: Clock, explanation: 'Integrated illustrative index over this contiguous demo history.', provenance: 'ILLUSTRATIVE DEMO' },
  fem_hot_spot_temperature: { title: 'FEM reference temperature', unit: '°C', icon: Thermometer, explanation: 'Synthetic sheet winding mean; not a spatial hot-spot maximum.', provenance: 'SIMULATED REFERENCE' },
  hot_spot_difference: { title: 'Estimator-versus-FEM temperature difference', unit: 'K', icon: GitCompareArrows, explanation: 'Estimator minus FEM, using the same synthetic winding mean target.', provenance: 'SIMULATED COMPARISON' },
};

type State = Pick<ReturnType<typeof usePhysics>, 'data' | 'loading' | 'error' | 'retry' | 'lastSuccess'>;

/** Ten siblings appended to the existing feature grid; no fetching or calculations here. */
export function PhysicsFeatureCards({ state, enabled, now }: { state: State; enabled: boolean; now: number }) {
  const data = enabled && !state.loading && !state.error && state.data && 'demo_contract_version' in state.data ? state.data : null;
  const expired = !!data && now - Date.parse(data.timestamp) > data.maximum_age_seconds * 1000;
  return <>{physicsComponentNames.map(name => {
    const definition = features[name], component = data?.components[name];
    const status = !enabled ? 'DISABLED' : state.loading ? 'LOADING' : state.error ? 'API ERROR' : expired ? 'STALE' : component?.status ?? 'UNAVAILABLE';
    const available = status === 'READY' && component?.value != null;
    const reason = !enabled ? 'Local frontend demo flag is disabled. Start backend/scripts/Start-TenTransformerDemo.ps1 for the MQTT fleet, open its printed frontend URL and select one of its registered synthetic assets.' : state.loading ? 'Loading the selected asset’s simulation result.' : state.error ?? (expired ? 'Simulation event expired; waiting for a new event.' : component?.status === 'INITIALIZING' ? 'Waiting for supported temperature history.' : component?.status === 'UNAVAILABLE' ? data?.reason ?? 'This component is unavailable.' : !data ? 'No eligible simulation result is available.' : null);
    return <article className="feature-panel physics-feature" key={name} aria-label={definition.title} data-physics-component={name} data-asset={data?.transformer_id} data-sequence={data?.sequence}>
      <div className="feature-heading"><definition.icon size={18}/><h3>{definition.title}</h3></div>
      <div className="physics-card-badges"><Badge tone={available ? 'info' : state.error ? 'danger' : 'neutral'}>{status}</Badge>{enabled && <Badge>LIVE SIMULATION</Badge>}</div>
      <strong className="feature-value">{available ? valueLabel(component.value, definition.unit) : 'Unavailable'}</strong>
      {!available && <small>Unit: {definition.unit}</small>}
      <small className="physics-card-provenance">{definition.provenance} · SYNTHETIC</small>
      <p>{definition.explanation}</p>
      {reason && <p className="physics-card-reason">{reason}</p>}
      {state.error && enabled && name === 'measured_oil_temperature' && <button className="button-secondary" onClick={state.retry}>Retry physics</button>}
      <details><summary>Model and assumptions</summary><p>Model {component?.model_id ?? 'Unavailable'} · Target {component?.target ?? 'Unavailable'} · Reference {component?.reference ?? 'docs/live_physics_demo_model.md'}</p><p>Case {data?.case_id ?? 'Unavailable'} · Run {data?.run_id ?? 'Unavailable'}. Demo-only simplified models; operational physics eligibility is unchanged.</p></details>
      <footer><div>Event <EventTime value={data?.timestamp}/></div><div>Evaluated <EventTime value={data?.evaluated_at}/></div><div>Last update <EventTime value={state.lastSuccess == null ? null : new Date(state.lastSuccess).toISOString()}/></div><div>{data?.transformer_id ?? 'No current result'} · sequence {data?.sequence ?? 'Unavailable'}</div></footer>
    </article>;
  })}</>;
}
