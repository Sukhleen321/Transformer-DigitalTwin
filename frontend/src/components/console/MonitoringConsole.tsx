import { operatingState, timeLabel } from './presentation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, ArrowLeft, ArrowRight, Bell, ChevronLeft, ChevronRight, CircleHelp, LayoutGrid, Menu, Radio, RefreshCw, Search, ShieldCheck, Thermometer, Wrench, Zap } from 'lucide-react';
import { api } from '../../api/client';
import type { Asset } from '../../api/contracts';
import { registryLoader, useAssetData, usePortfolio } from '../../hooks/useConsoleData';
import { usePolling } from '../../hooks/usePolling';
import { usePhysics } from '../../hooks/usePhysics';
import { PhysicsPanel } from './PhysicsPanel';
import { PhysicsFeatureCards } from './PhysicsFeatureCards';
import { freshness, STALE_MS } from '../../monitoring';
import { HealthIndexDial } from '../HealthIndexDial';
import { PrescriptiveActionCard } from '../PrescriptiveActionCard';
import { EnergyCard, NameplateCard, RULCard } from '../ResourceCards';
import { ThermalResidualChart, thermalPoints } from '../ThermalResidualChart';
import { Badge, EventTime, FeaturePanels, Reading, SourceStrip, TransformerDrawing } from './TelemetryPanels';
import { TrendCharts } from './TrendCharts';
import './console.css';

const navigation = [
  { id: 'overview', label: 'Overview', icon: LayoutGrid },
  { id: 'monitoring', label: 'Transformer monitoring', icon: Zap },
  { id: 'alarms', label: 'Live alarms / events', icon: Bell },
  { id: 'thermal', label: 'Thermal & loading', icon: Thermometer },
  { id: 'maintenance', label: 'Predictive maintenance', icon: Wrench },
  { id: 'system', label: 'System / source health', icon: Radio },
];
export function RequestStatus({ state, label }: { state: { loading: boolean; error: string | null; retry: () => void }; label: string }) {
  return <>{state.loading && <p role="status" className="request-status">{label}: loading…</p>}{state.error && <div role="alert" className="request-error">{label}: {state.error}. Retained data may be stale. <button onClick={state.retry}>Retry</button></div>}</>;
}
export function MonitoringConsole() {
  const [area, setArea] = useState('overview'), [selected, setSelected] = useState(''), [sidebar, setSidebar] = useState(false);
  const [search, setSearch] = useState(''), [statusFilter, setStatusFilter] = useState('all'), [alarmFilter, setAlarmFilter] = useState('all'), [page, setPage] = useState(0);
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const registry = usePolling('active-registry', registryLoader, 60000);
  const assets = useMemo(() => registry.data ?? [], [registry.data]);
  const selectedAsset = assets.some(a => a.id === selected) ? selected : '';
  const matching = useMemo(() => assets.filter(a => `${a.id} ${a.name}`.toLowerCase().includes(search.toLowerCase())), [assets, search]);
  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(matching.length / pageSize)), currentPage = Math.min(page, pageCount - 1);
  const visible = matching.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const portfolio = usePortfolio(visible.map(a => a.id), area === 'overview');
  const detail = useAssetData(area === 'overview' || area === 'system' ? '' : selectedAsset, area);
  const livePhysicsDemo = import.meta.env.VITE_LIVE_PHYSICS_DEMO_ENABLED === 'true';
  const physics = usePhysics(selectedAsset, area === 'thermal' || (area === 'monitoring' && livePhysicsDemo));
  const latest = detail.latest;
  const mqttLoad = useCallback((s: AbortSignal) => api.mqtt(s), []);
  const mqtt = usePolling('mqtt', mqttLoad, 15000);
  const choose = (id: string) => { setSelected(id); setArea('monitoring'); setSidebar(false); };
  const asset = latest.data?.transformer ?? assets.find(a => a.id === selectedAsset);
  const t = latest.data?.telemetry, a = latest.data?.analytics;
  const state = operatingState(latest.data, latest.error);
  const matchingStatus = visible.filter(asset => {
    const snapshot = portfolio.data?.[asset.id], s = operatingState(snapshot?.data, snapshot?.error);
    const alarms = snapshot?.data?.open_alerts_count;
    return (statusFilter === 'all' || (statusFilter === 'warnings' ? ['danger','warning'].includes(s.tone) : !snapshot?.data?.analytics || !!snapshot.error)) && (alarmFilter === 'all' || (alarmFilter === 'open' ? alarms != null && alarms > 0 : alarms == null));
  });
  const title = navigation.find(n => n.id === area)?.label;
  return <div className="monitoring-console">
    <aside className={'console-sidebar ' + (sidebar ? 'expanded' : '')}><a className="console-brand" href="#" onClick={e => { e.preventDefault(); setArea('overview'); }}><span className="brand-mark"><Zap size={24}/></span><span>TRANSFORMER<span>DIGITAL TWIN</span></span></a><div className="sidebar-section-label">OPERATIONS CONSOLE</div><nav aria-label="Main navigation">{navigation.map(n => <button key={n.id} aria-current={area === n.id ? 'page' : undefined} className={area === n.id ? 'active' : ''} onClick={() => { setArea(n.id); setSidebar(false); }}><n.icon size={18}/><span>{n.label}</span>{area === n.id && <ChevronRight size={14}/>}</button>)}</nav><div className="sidebar-bottom"><ShieldCheck size={18}/><div>Read-only monitoring<small>Contract 1.1.0 · operator review</small></div><p>Simulated telemetry is not physical equipment data. No control writes.</p></div></aside>
    <div className="console-workspace"><header className="console-topbar"><button className="mobile-menu" aria-label="Toggle navigation" onClick={() => setSidebar(!sidebar)}><Menu size={20}/></button><div className="topbar-location"><span>Transformer Digital Twin</span><small>Monitoring workspace / {title}</small></div><div className="topbar-status"><Badge>{t?.acquisition?.source_kind ?? (area === 'overview' ? 'Source shown per asset' : 'UNKNOWN source')}</Badge><span className="topbar-update">Measurement <EventTime value={t?.timestamp}/></span><Badge tone={mqtt.error ? 'danger' : mqtt.data?.connected ? 'info' : 'neutral'}><span className="status-dot"/>{mqtt.error ? 'API connection error' : mqtt.data?.connected ? 'MQTT connected' : 'Transport unknown / disconnected'}</Badge><span className="topbar-update">API checked {timeLabel(mqtt.lastSuccess)}</span></div></header>
    <main className="console-main"><div className="page-heading"><div><div className="eyebrow">ASSET OPERATIONS / {area.toUpperCase()}</div><h1>{area === 'overview' ? 'Transformer overview' : title}</h1><p>{area === 'overview' ? 'Registered equipment · current telemetry and persisted condition assessments' : 'Measurements and model outputs from the selected asset’s backend records'}</p></div><div className="heading-actions"><Badge>Read only</Badge><button className="button-secondary" onClick={() => { registry.retry(); if (area === 'overview') portfolio.retry(); else if (area === 'system') mqtt.retry(); else { latest.retry(); if (area === 'thermal' || (area === 'monitoring' && livePhysicsDemo)) physics.retry(); } }}><RefreshCw size={14}/> Refresh</button></div></div>
    {area === 'overview' ? <>
      <RequestStatus state={registry} label="Asset registry"/>
      <div className="overview-summary"><div><LayoutGrid/><span>Active transformers<strong>{registry.data ? assets.length : '—'}</strong></span></div><div><Activity/><span>Monitoring scope<strong>{visible.length} cards / page</strong></span></div><div><Radio/><span>Delivery transport<strong>{mqtt.data?.connected ? 'MQTT connected' : 'Unconfirmed'}</strong></span></div><div><CircleHelp/><span>Condition evidence<strong>Per-asset assessment</strong></span></div></div>
      <div className="overview-toolbar"><label className="search-field"><Search size={17}/><input aria-label="Search assets" placeholder="Search asset ID or name…" value={search} onChange={e => { setSearch(e.target.value); setPage(0); }}/></label><label>Status on page<select aria-label="Status filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="all">All assessments</option><option value="warnings">Warnings / protection</option><option value="unavailable">Unavailable / errors</option></select></label><label>Alarms on page<select aria-label="Alarm filter" value={alarmFilter} onChange={e => setAlarmFilter(e.target.value)}><option value="all">All alarm states</option><option value="open">Open alerts</option><option value="unknown">Unknown</option></select></label></div>
      <div className="section-heading"><h2>Asset inventory <span>{matching.length} matching assets</span></h2><small>Visible cards: 15s refresh · ≤3 concurrent requests</small></div><RequestStatus state={portfolio} label="Visible asset readings"/>
      {registry.data && !assets.length && <div className="empty-state">No registered assets. No local samples are substituted.</div>}
      <section className="asset-grid" aria-label="Asset portfolio">{matchingStatus.map(asset => <TransformerCard key={asset.id} asset={asset} snapshot={portfolio.data?.[asset.id]} now={now} choose={choose}/> )}</section>
      {!!assets.length && !matchingStatus.length && <div className="empty-state">No matching assets on this page. Other pages may contain matching assessments.</div>}
      <div className="pagination"><span>Page {currentPage+1} of {pageCount} · {matchingStatus.length} displayed</span><button disabled={currentPage === 0} onClick={() => setPage(currentPage-1)}><ChevronLeft size={16}/>Previous</button><button disabled={currentPage+1 >= pageCount} onClick={() => setPage(currentPage+1)}>Next<ChevronRight size={16}/></button></div>
      <p className="disclosure">No alarm is not proof of a healthy asset. Freshness threshold {STALE_MS/1000}s is a configured demo policy, not an operational safety limit.</p>
    </> : area === 'system' ? <section className="console-panel" aria-label="System health"><div className="section-heading"><h2>Data-source & transport health</h2><Badge>{mqtt.data?.connected ? 'Broker connected' : 'Unconfirmed'}</Badge></div><RequestStatus state={mqtt} label="MQTT diagnostics"/><p>Gateway transport updates do not refresh measurement event time or establish a committed receipt.</p>{mqtt.data && <dl className="system-metrics">{Object.entries(mqtt.data).map(([key,value]) => <div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{value == null ? 'Unavailable' : String(value)}</dd></div>)}</dl>}<p>Actual model/configuration identity is shown per asset. Pressure, DGA and leak-detector resources are not supplied by this pipeline.</p></section> : <>
      <div className="detail-toolbar"><button className="button-secondary" onClick={() => setArea('overview')}><ArrowLeft size={15}/>Asset overview</button><label>Selected asset<select aria-label="Asset" value={selectedAsset} onChange={e => setSelected(e.target.value)}><option value="">Select registered asset</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.id} · {asset.name}</option>)}</select></label><Badge tone={state.tone}>{state.label}</Badge></div>
      {!selectedAsset ? <div className="empty-state">Select an asset from the overview or registry selector to monitor its data.</div> : <>
        <RequestStatus state={latest} label="Latest telemetry"/>
        <SourceStrip data={latest.data} lastSuccess={latest.lastSuccess} error={latest.error} now={now}/>
        {area === 'monitoring' && <>
          <section className="console-panel equipment-panel" aria-label="Selected transformer measurements"><div className="section-heading"><div><h2>{selectedAsset}</h2><p>{asset?.name ?? 'Registered asset'} · {asset?.measurement_side ?? 'UNKNOWN'} measurement side</p></div><Badge tone={state.tone}>{state.label}</Badge></div><div className="equipment-layout"><div className="equipment-readings"><Reading label="Oil temperature" field="oil_temperature" record={t}/><Reading label="Oil level" field="oil_level" record={t}/><Reading label="Ambient temperature" field="ambient_temperature" record={t}/></div><div className="equipment-center"><TransformerDrawing/><span className="equipment-caption">Illustrative schematic · {selectedAsset}</span><Badge>{t?.acquisition?.source_kind ?? 'UNKNOWN'} source</Badge></div><div className="equipment-readings"><Reading label="Phase L1 voltage" field="phase_voltage_l1" record={t}/><Reading label="Phase L1 current" field="current_l1" record={t}/><Reading label="Active power" field="active_power_total" record={t}/></div></div><div className="phase-readings">{(['current_l2','current_l3','phase_voltage_l2','phase_voltage_l3','apparent_power_total','reactive_power_total','neutral_current','winding_temperature','power_factor_l1'] as const).map(f => <Reading key={f} label={f === 'winding_temperature' ? 'WTI source indicator (not temperature)' : f.replaceAll('_',' ')} field={f} record={t}/>)}</div></section>
          <FeaturePanels data={latest.data} label="Transformer monitoring features"><PhysicsFeatureCards state={physics} enabled={livePhysicsDemo} now={now}/></FeaturePanels>
        </>}
        {(area === 'thermal' || area === 'monitoring') && <><RequestStatus state={detail.history} label="History"/><TrendCharts records={detail.history.data?.telemetry.items ?? []} total={detail.history.data?.telemetry.total ?? 0} gap={(t?.acquisition?.expected_interval_seconds ?? 5)*2}/>{area === 'thermal' && <><FeaturePanels data={latest.data}/><ThermalResidualChart data={thermalPoints(detail.history.data?.telemetry.items ?? [],detail.history.data?.analytics.items ?? [], t?.acquisition?.field_units.oil_temperature)} unit={t?.acquisition?.field_units.oil_temperature}/><PhysicsPanel state={physics} latestEvent={t?.timestamp}/>{asset && <NameplateCard asset={asset}/>}</>}</>}
        {(area === 'alarms' || area === 'monitoring') && <section className="console-panel" aria-label="Alerts"><div className="section-heading"><div><h2>Alarms & events</h2><p>{selected} · bounded 24-hour event-time window · latest open count {latest.data?.open_alerts_count ?? 'unknown'}</p></div><Bell size={18}/></div><RequestStatus state={detail.alerts} label="Events"/>{detail.alerts.data?.items.length === 0 && <div className="empty-state">No events returned in this window. This is not a healthy-state assertion.</div>}<div className="table-scroll"><table><thead><tr><th>Severity</th><th>Event / asset</th><th>Evidence</th><th>Event time</th><th>Lifecycle</th></tr></thead><tbody>{detail.alerts.data?.items.map(event => <tr key={event.id}><td><Badge tone={event.severity === 'CRITICAL' ? 'danger' : event.severity === 'WARNING' ? 'warning' : 'info'}>{event.severity}</Badge></td><td>{event.alert_type}<small>{event.transformer_id}</small></td><td>{event.trigger}<small>{event.threshold_or_reason}</small><details><summary>Backend evidence / recommendation</summary><pre>{JSON.stringify(event.evidence,null,2)}</pre><p>{event.recommended_action}</p></details></td><td><EventTime value={event.timestamp}/></td><td>{event.status}<small>Last seen <EventTime value={event.last_seen_at}/></small></td></tr>)}</tbody></table></div>{detail.alerts.data && <p className="disclosure">Showing {detail.alerts.data.items.length} of {detail.alerts.data.total}; older events outside the window are not included.</p>}</section>}
        {area === 'maintenance' && <><div className="analytics-grid"><HealthIndexDial analytics={a}/><PrescriptiveActionCard analytics={a}/></div><section className="console-panel"><h2>Persisted maintenance actions · {selectedAsset}</h2><RequestStatus state={detail.maintenance} label="Maintenance"/>{detail.maintenance.data?.total === 0 && <p>No recommendations returned in the bounded window.</p>}{detail.maintenance.data?.items.map(m => <article className="maintenance-row" key={m.id}><Badge>{m.priority}</Badge><strong>{m.recommendation}</strong><p>{m.reason_codes.join(', ')} · {m.status} · <EventTime value={m.timestamp}/></p></article>)}</section><div className="analytics-grid"><div><RequestStatus state={detail.rul} label="RUL"/><RequestStatus state={detail.projection} label="Scenario curve"/><RULCard result={detail.rul.data?.rul ?? a?.rul} projection={detail.projection.data} message="No persisted RUL result"/></div><div><RequestStatus state={detail.energy} label="Energy"/><EnergyCard result={detail.energy.data} message="No bounded-window energy result"/></div></div>{asset && <NameplateCard asset={asset}/>}</>}
      </>}
    </>}
    <footer className="console-footer"><span>POWERNext / Transformer Digital Twin</span><span>Source-aware monitoring · no local inference · contract 1.1.0</span></footer>
    </main></div>
  </div>;
}
function TransformerCard({ asset, snapshot, now, choose }: { asset: Asset; snapshot?: import('../../hooks/useConsoleData').AssetSnapshot; now: number; choose: (id: string) => void }) {
  const data = snapshot?.data, t = data?.telemetry, state = operatingState(data, snapshot?.error);
  return <button className="transformer-card" onClick={() => choose(asset.id)} aria-label={`Monitor ${asset.id}`}><div className="asset-card-heading"><Badge tone={state.tone}>{state.label}</Badge><ArrowRight size={16}/></div><div className="asset-card-identity"><TransformerDrawing small/><div><h3>{asset.id}</h3><p>{asset.name}</p><Badge>{t?.acquisition?.source_kind ?? 'UNKNOWN'} source</Badge></div></div><div className="asset-card-readings"><Reading label="Voltage L1" field="phase_voltage_l1" record={t}/><Reading label="Current L1" field="current_l1" record={t}/><Reading label="Oil temperature" field="oil_temperature" record={t}/><Reading label="Active power" field="active_power_total" record={t}/></div><div className="asset-card-footer"><span><EventTime value={t?.timestamp}/></span><small>{freshness(t,snapshot?.lastSuccess ?? null,now,snapshot?.error ?? null)}</small><small>Open alerts: {data?.open_alerts_count ?? 'Unknown'} · Configuration: {asset.configuration_metadata?.status ?? 'UNVERIFIED'}</small></div></button>;
}
