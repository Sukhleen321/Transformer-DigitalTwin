import { physicsComponentNames, type LivePhysicsDemoResult } from '../../api/livePhysicsDemo';
import { Badge, EventTime } from './TelemetryPanels';
import { valueLabel } from './presentation';
import { useEffect, useState } from 'react';

const labels = ['Oil temperature channel · simulated sensor input', 'Top-oil estimate · oil node proxy',
  'Winding hot-spot estimate · winding mean proxy', 'Oil-node temperature rise', 'Winding-to-oil temperature gradient',
  'Total synthetic losses', 'Illustrative ageing acceleration factor', 'Illustrative equivalent ageing hours',
  'FEM hot-spot reference · winding mean proxy', 'Estimator–FEM winding mean difference'];
export function LivePhysicsDemoPanel({ data, lastSuccess }: { data: LivePhysicsDemoResult; lastSuccess?: number | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const expired = now - Date.parse(data.timestamp) > data.maximum_age_seconds * 1000;
  return <>
    <div className="section-heading"><div><h2>Physics results</h2><p>Live demo · refreshes at the configured simulation interval while this view is active.</p></div><Badge>LIVE SIMULATION</Badge></div>
    <p className="disclosure">Every value is SYNTHETIC / SIMULATED. Fictional sheets and simplified node proxies; no measured equipment readings, operational hot-spot accuracy, IEEE/IEC compliance, RUL or failure probability.</p>
    <p>Asset {data.transformer_id} · Event <EventTime value={data.timestamp}/> · Published <EventTime value={data.published_at}/> · Latest update <EventTime value={lastSuccess ? new Date(lastSuccess).toISOString() : data.evaluated_at}/> · Sequence {data.sequence}</p>
    <p className="disclosure">FEM and estimator share the area-average winding target, not a spatial maximum. Illustrative ageing is a fictional temperature index, not insulation life. Current input {valueLabel(data.inputs.current_a, 'A')} · ambient {valueLabel(data.inputs.ambient_k, 'K')}.</p>
    {data.reason && <p role="status">{data.reason}. All values unavailable.</p>}
    {expired && !data.reason && <p role="status">Simulation event is stale. All values unavailable until a new event arrives.</p>}
    <div className="table-scroll"><table><thead><tr><th>Quantity</th><th>Value / unit</th><th>Status / provenance</th></tr></thead><tbody>{physicsComponentNames.map((name, i) => {
      const c = data.components[name];
      const unit = c.unit === 'DEG_C' ? '°C' : c.unit;
      return <tr key={name}><td>{labels[i]}<small>SYNTHETIC_SIMULATED</small></td><td>{!expired && c.status === 'READY' ? valueLabel(c.value, unit) : 'Unavailable'}{(expired || c.status !== 'READY') && <small>Unit: {unit}</small>}</td><td><Badge>{expired ? 'UNAVAILABLE' : c.status}</Badge><details><summary>{labels[i]} demo evidence</summary><p>Provenance {c.provenance} · Model {c.model_id} · Target {c.target} · Definition {c.reference} · Case {data.case_id} · Run {data.run_id}</p></details></td></tr>;
    })}</tbody></table></div>
  </>;
}
