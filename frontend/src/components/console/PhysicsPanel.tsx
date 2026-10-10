import type { PhysicsComponentName, PhysicsResult } from '../../api/physics';
import type { LivePhysicsDemoResult } from '../../api/livePhysicsDemo';
import { LivePhysicsDemoPanel } from './LivePhysicsDemoPanel';
import { Badge, EventTime } from './TelemetryPanels';
import { valueLabel } from './presentation';

const labels: Record<PhysicsComponentName, string> = {
  measured_oil_temperature: 'Measured oil sensor', top_oil_temperature: 'Oil node temperature estimate',
  hot_spot_temperature: 'Winding node temperature estimate', top_oil_rise: 'Oil node rise estimate',
  winding_hot_spot_gradient: 'Winding–oil node gradient estimate', total_loss: 'Current-squared loss estimate',
  ageing_acceleration_factor: 'Ageing acceleration factor', equivalent_ageing_hours: 'Equivalent ageing hours',
  fem_hot_spot_temperature: 'FEM hot-spot reference', hot_spot_difference: 'Estimator–FEM difference',
};
const statusLabels = { READY: 'Ready for this component', INITIALIZING: 'Initializing', INSUFFICIENT_DATA: 'Insufficient data', INVALID_CONFIGURATION: 'Invalid / missing configuration', MODEL_ERROR: 'Model error' };
interface State { data: PhysicsResult | LivePhysicsDemoResult | null; loading: boolean; error: string | null; retry: () => void; lastSuccess?: number | null }
export function PhysicsPanel({ state, latestEvent }: { state: State; latestEvent?: string | null }) {
  if (state.data && 'demo_contract_version' in state.data && !state.loading && !state.error) return <section className="console-panel" aria-label="Physics results"><LivePhysicsDemoPanel data={state.data} lastSuccess={state.lastSuccess}/></section>;
  const data = !state.loading && !state.error && state.data && 'physics_contract_version' in state.data ? state.data : null;
  const superseded = !!data?.timestamp && !!latestEvent && Date.parse(latestEvent) > Date.parse(data.timestamp);
  return <section className="console-panel" aria-label="Physics results">
    <div className="section-heading"><div><h2>Physics results</h2><p>Snapshot from the latest physics read · use Refresh to check newer observations.</p></div>{data && <Badge>{data.context === 'CONTROLLED_SIMULATION' ? 'CONTROLLED_SIMULATION' : 'Operational context · limited outputs'}</Badge>}</div>
    {state.loading && <p role="status" className="request-status">Physics: loading…</p>}
    {state.error && <div role="alert" className="request-error">Physics: {state.error}. Values are unavailable. <button onClick={state.retry}>Retry physics</button></div>}
    {!data && !state.loading && !state.error && <p>No physics result available.</p>}
    {superseded && <p role="status" className="request-status">Newer telemetry is available. Physics values are unavailable until refreshed.</p>}
    {data && <>
      {data.context === 'CONTROLLED_SIMULATION' && <p>Controlled-simulation estimates / simplified node proxies</p>}
      <p className="disclosure">Validated operational top-oil / hot-spot predictions, ageing, FEM comparison, RUL and failure probability are unavailable in this physics release.</p>
      <p className="disclosure">Source {data.lineage.source_kind} · origin {data.lineage.origin_kind} · inputs {data.lineage.input_verification}. Selected event <EventTime value={data.timestamp}/> · Evaluated <EventTime value={data.evaluated_at}/></p>
      <div className="table-scroll"><table><thead><tr><th>Quantity</th><th>Value / unit</th><th>Status / explanation</th></tr></thead><tbody>
        {(Object.keys(labels) as PhysicsComponentName[]).map(name => {
          const c = data.components[name];
          const kind = c.result_kind === 'MEASURED_TELEMETRY' ? 'Measured telemetry · sensor target per evidence' : c.result_kind === 'SIMULATED_REFERENCE' ? 'Simulated reference · numerical benchmark' : data.context === 'CONTROLLED_SIMULATION' ? 'Calculated estimate · controlled simulation' : 'Calculated estimate';
          return <tr key={name}><td>{labels[name]}<small title={c.result_kind}>{kind}</small></td><td>{!superseded && c.status === 'READY' && c.value !== null ? valueLabel(c.value, c.unit === 'DEG_C' ? '°C' : c.unit) : 'Unavailable'}{(superseded || c.status !== 'READY') && <small>Unit: {c.unit === 'DEG_C' ? '°C' : c.unit}</small>}</td><td>
            <Badge tone={superseded ? 'neutral' : c.status === 'MODEL_ERROR' ? 'danger' : c.status === 'READY' ? 'info' : 'neutral'}>{superseded ? 'Refresh required' : statusLabels[c.status]}</Badge>
            {c.reasons.map((r, i) => <small key={i} title={r.code}>{r.message}</small>)}
            <details><summary>{labels[name]} evidence and assumptions</summary>
              <p>Returned status: {c.status} · Kind: {c.result_kind} · Reasons: {c.reasons.map(r => `${r.code}: ${r.message}`).join('; ') || 'None reported'}</p>
              <p>Required inputs: {c.missing_inputs.join(', ') || 'None reported'}</p>
              <p>Warnings: {c.warnings.map(w => `${w.code}: ${w.message}`).join('; ') || 'None reported'}</p>
              <p>Assumptions: {c.assumptions.map(a => `${a.message} (${a.reference})`).join('; ') || 'None supplied'}</p>
              <p>Model: {c.provenance.model_id ?? 'Unavailable'} · Equations: {c.provenance.equation_ids.join(', ') || 'Unavailable'} · Case: {c.provenance.case_id ?? 'Unavailable'}</p>
              <p>Input paths: {c.provenance.input_paths.join(', ') || 'Unavailable'} · Evidence references: {c.provenance.evidence_references.join(', ') || 'Unavailable'}</p>
              <p>Coverage: <EventTime value={c.coverage.start}/> → <EventTime value={c.coverage.end}/> · {valueLabel(c.coverage.covered_seconds, 's')} covered / {valueLabel(c.coverage.expected_seconds, 's')} expected · fraction {valueLabel(c.coverage.fraction, '1')} · gaps {c.coverage.gap_count} · Missing: {c.coverage.missing_fields.join(', ') || 'None reported'}</p>
            </details>
          </td></tr>;
        })}
      </tbody></table></div>
      <details><summary>Physics identity and provenance</summary>
        <p>Contract {data.physics_contract_version} · Asset {data.transformer_id} · Acquisition {data.lineage.acquisition_reference ?? 'Unavailable'} · Origin asset {data.lineage.origin_transformer_id ?? 'Unavailable'} · Replay {data.lineage.replay_run_id ?? 'Unavailable'}</p>
        <p>{Object.entries(data.versions).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v ?? 'Unavailable'}`).join(' · ')}</p>
        <p>Evidence references: {data.lineage.evidence_references.join(', ') || 'Unavailable'}. References identify records; evidence bodies are not provided by this read API.</p>
      </details>
    </>}
  </section>;
}
