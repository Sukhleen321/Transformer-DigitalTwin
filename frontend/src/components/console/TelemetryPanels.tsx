import type { Latest, Telemetry } from '../../api/contracts';
import type { ReactNode } from 'react';
import { contactLabel, freshness, thermalReady } from '../../monitoring';
import { timeLabel, valueLabel as displayNumber } from './presentation';
import { Activity, Droplets, Gauge, Thermometer, Zap, Wrench } from 'lucide-react';

export function EventTime({ value }: { value?: string | null }) {
  return <time dateTime={value ?? undefined} title={value ?? undefined}>{timeLabel(value)}</time>;
}
export function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: string }) {
  return <span className={'console-badge ' + tone}>{children}</span>;
}
export function Reading({ label, field, record }: { label: string; field: keyof Telemetry; record?: Telemetry | null }) {
  const value = record?.[field];
  return <div className="reading"><span>{label}</span><strong>{displayNumber(typeof value === 'number' ? value : null, record?.acquisition?.field_units[field])}</strong><small>{record?.acquisition?.field_verification[field] ?? 'UNVERIFIED'} · {record?.acquisition?.measurement_side ?? 'UNKNOWN'} side</small></div>;
}
export function TransformerDrawing({ small = false }: { small?: boolean }) {
  return <svg className={small ? 'transformer-mini' : 'transformer-drawing'} viewBox="0 0 320 260" role="img" aria-label="Transformer schematic, illustrative equipment only">
    <defs><linearGradient id={small ? 'tank-mini' : 'tank-detail'} x1="0" x2="1"><stop stopColor="#395b7a"/><stop offset=".5" stopColor="#6586a0"/><stop offset="1" stopColor="#35536e"/></linearGradient></defs>
    <path d="M40 226h240" stroke="#ccd7e1" strokeWidth="2"/>
    <path d="M105 57v-28m54 28v-38m55 38v-28" stroke="#203f5d" strokeWidth="10"/>
    {[105,159,214].map(x => <g key={x}>{[26,33,40,47].map(y => <rect key={y} x={x-11} y={y} width="22" height="5" rx="2" fill="#7492ab"/>)}</g>)}
    <rect x="88" y="65" width="143" height="140" rx="5" fill={`url(#${small ? 'tank-mini' : 'tank-detail'})`} stroke="#274760" strokeWidth="2"/>
    <path d="M88 65l22-12h121l-1 13M230 65l15-10v139l-15 11" fill="#90a6b8" stroke="#385770"/>
    {[63,72,81,235,244,253].map(x => <rect key={x} x={x} y="92" width="7" height="97" rx="2" fill="#53718a" stroke="#2e4c64"/>)}
    <rect x="99" y="78" width="120" height="8" fill="#abc0cd"/>
    <rect x="108" y="99" width="105" height="57" rx="5" fill="#223f55" stroke="#aac0d0"/>
    {[131,163,195].map(x => <g key={x}><rect x={x-10} y="107" width="19" height="40" fill="#b98451"/>{[108,114,120,126,132,138,144].map(y=><ellipse key={y} cx={x} cy={y} rx="10" ry="3" fill="#d7a773" stroke="#9e663d" strokeWidth="1"/>)}</g>)}
    <rect x="121" y="168" width="75" height="17" rx="2" fill="#c6d4df"/><path d="M112 205v15m98-15v15" stroke="#2c4c65" strokeWidth="10"/>
    <rect x="50" y="209" width="220" height="8" rx="2" fill="#526d82"/>
  </svg>;
}
export function SourceStrip({ data, lastSuccess, error, now }: { data?: Latest | null; lastSuccess: number | null; error: string | null; now: number }) {
  const t = data?.telemetry, a = data?.analytics;
  return <section className="source-strip" aria-label="Source and freshness">
    <div><span>Source</span><strong>{t?.acquisition?.source_kind ?? 'UNKNOWN'} · {t?.acquisition?.source_name ?? 'Unknown provenance'}</strong><small>{t?.acquisition?.source_kind === 'SIMULATED' ? 'Generated telemetry · no physical transformer connection' : t?.acquisition?.source_kind === 'REPLAYED' ? `Historical replay · origin ${t.acquisition.origin_kind} / ${t.acquisition.origin_transformer_id} · run ${t.acquisition.replay_run_id}` : 'A source label does not establish verified units'}</small></div>
    <div><span>Measurement event</span><strong><EventTime value={t?.timestamp}/></strong><small>{freshness(t, lastSuccess, now, error)}</small></div>
    <div><span>Analytics event</span><strong><EventTime value={a?.timestamp}/></strong><small>{a && t && Date.parse(a.timestamp) < Date.parse(t.timestamp) ? 'Analysis predates telemetry' : data?.analytics_availability?.status ?? 'Unavailable'} · {data?.analytics_availability?.reasons.join(', ')}</small></div>
    <div><span>Last successful API poll</span><strong>{timeLabel(lastSuccess)}</strong><small>Map {t?.acquisition?.map_version ?? 'unknown'} · sequence {t?.acquisition?.sequence ?? 'unknown'}</small></div>
    <details><summary>Identity and quality</summary><p>Snapshot: {t?.acquisition?.snapshot_id ?? 'Unknown'} · Received: {timeLabel(t?.received_at)} · Timezone evidence: {t?.acquisition?.timezone_status ?? 'UNKNOWN'} · Expected cadence: {displayNumber(t?.acquisition?.expected_interval_seconds, 's')}</p><p>Bundle: {a?.metadata?.versions?.bundle_id ?? 'Unknown'} · Configuration: {a?.metadata?.versions?.configuration_version ?? 'Unknown'} · Inference: {a?.inference_status ?? 'Unavailable'}</p></details>
  </section>;
}
export function FeaturePanels({ data, children, label = 'Six monitoring features' }: { data?: Latest | null; children?: ReactNode; label?: string }) {
  const t = data?.telemetry, a = data?.analytics;
  const thermalUnit = a?.metadata?.thermal_temperature_unit ?? a?.metadata?.units?.thermal_model_temperature;
  const compatible = thermalReady(a) && thermalUnit === t?.acquisition?.field_units.oil_temperature;
  const features = [
    { title: 'Oil-leak detection', icon: Droplets, state: 'Detector unavailable', value: displayNumber(t?.oil_level, t?.acquisition?.field_units.oil_level), evidence: `Oil gauge contact: ${contactLabel(t?.magnetic_oil_gauge_alarm)}. No leak/depletion result is supplied by the API. An oil-level change alone does not confirm leakage.` },
    { title: 'Pressure monitoring', icon: Gauge, state: 'Input unavailable', value: 'Unavailable', evidence: 'No pressure measurement, unit, limits or trend exists in the canonical pipeline. DGA measurements are also unavailable.' },
    { title: 'Electrical-fault monitoring', icon: Zap, state: t?.oil_temp_trip === 1 ? 'Protection contact active' : a?.anomaly_flag ? 'Model anomaly' : 'No confirmed fault result', value: `Trip: ${contactLabel(t?.oil_temp_trip)}`, evidence: `Oil temperature alarm: ${contactLabel(t?.oil_temp_alarm)}. Maintenance trip latch: ${a?.metadata?.maintenance_trip_latched == null ? 'Unknown' : a.metadata.maintenance_trip_latched ? 'Latched' : 'Not latched'}. These are temperature/protection contacts, not a short-circuit relay diagnosis. A generic anomaly is not a confirmed short circuit.` },
    { title: 'Thermal capacity', icon: Thermometer, state: a?.metadata?.components?.thermal?.status ?? a?.metadata?.thermal_readiness ?? 'Assessment unavailable', value: compatible ? displayNumber(a?.thermal_residual, thermalUnit) + ' residual' : 'Residual unavailable', evidence: `Model: ${thermalReady(a) ? displayNumber(a?.thermal_model_temperature, thermalUnit) : 'Unavailable — component not ready'}. ${a?.thermal_state ?? 'No thermal-state result'}. ${a?.metadata?.components?.thermal?.reasons.join(', ') ?? 'No readiness reasons supplied'}. Headroom requires verified equipment limits. WTI status is not temperature.` },
    { title: 'Overload capacity', icon: Activity, state: a?.loading_percent == null ? 'Assessment unavailable' : 'Backend loading assessment', value: displayNumber(a?.loading_percent, '%'), evidence: `Only the supplied backend loading result is shown. ${a?.reason_codes?.filter(r => r.includes('OVERLOAD')).join(', ') || 'No overload reason supplied'}. No duration/headroom estimate is supplied.` },
    { title: 'Predictive maintenance', icon: Wrench, state: a?.maintenance_priority ?? 'Recommendation unavailable', value: displayNumber(a?.health_index, '/ 100 HI'), evidence: a?.maintenance_recommendation ?? 'No recommendation supplied. Operational risk and RUL remain unavailable without required evidence.' },
  ];
  return <section className="feature-grid" aria-label={label}>{features.map(f => <article className="feature-panel" key={f.title}><div className="feature-heading"><f.icon size={18}/><h3>{f.title}</h3></div><Badge>{f.state}</Badge><strong className="feature-value">{f.value}</strong><p>{f.evidence}</p><footer><EventTime value={f.title === 'Pressure monitoring' ? null : f.title === 'Oil-leak detection' || f.title === 'Electrical-fault monitoring' ? t?.timestamp : a?.timestamp}/> · {t?.acquisition?.source_kind ?? 'UNKNOWN'}</footer></article>)}{children}</section>;
}
