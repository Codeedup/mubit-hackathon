import { useEffect, useState } from 'react'
import {
  Activity, ArrowRight, ChartNoAxesCombined, Check, ClipboardCheck,
  Database, FileJson, HeartPulse, LoaderCircle, RefreshCw, ShieldCheck,
  Stethoscope, TriangleAlert,
} from 'lucide-react'
import { api, type Incident, type Metrics } from './api/client'
import { Badge } from './components/ui/badge'
import { Button } from './components/ui/button'
import { Card, CardContent, CardHeader } from './components/ui/card'

type View = 'diagnostics' | 'feedback' | 'intelligence'
type LoadState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: T }

const navigation: { id: View; label: string; icon: typeof Activity; number: string }[] = [
  { id: 'diagnostics', label: 'Diagnostics', icon: Stethoscope, number: '01' },
  { id: 'feedback', label: 'Technician Feedback', icon: ClipboardCheck, number: '02' },
  { id: 'intelligence', label: 'Intelligence & Evaluation', icon: ChartNoAxesCombined, number: '03' },
]

function EmptyState({ icon: Icon, title, description }: {
  icon: typeof Activity; title: string; description: string
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={27} strokeWidth={1.7} /></div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <TriangleAlert size={20} />
      <div><strong>Could not load local data</strong><p>{message}</p></div>
      <Button variant="outline" size="sm" onClick={onRetry}><RefreshCw size={14} /> Retry</Button>
    </div>
  )
}

function LoadingState() {
  return <div className="loading-state" role="status"><LoaderCircle className="spin" size={18} /> Loading local data…</div>
}

function Diagnostics({ incidents, reload }: { incidents: LoadState<Incident[]>; reload: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = incidents.status === 'ready'
    ? incidents.data.find((item) => item.id === selectedId) ?? null
    : null

  return (
    <div className="view-grid">
      <Card className="incident-panel">
        <CardHeader>
          <div><div className="eyebrow">WORKSPACE / INCIDENTS</div><h2>Incident queue</h2></div>
          {incidents.status === 'ready' && <Badge>{incidents.data.length} records</Badge>}
        </CardHeader>
        <CardContent>
          {incidents.status === 'loading' && <LoadingState />}
          {incidents.status === 'error' && <ErrorState message={incidents.message} onRetry={reload} />}
          {incidents.status === 'ready' && incidents.data.length === 0 && (
            <EmptyState icon={FileJson} title="No incidents yet" description="Add team-authored JSON files to data/incidents to populate this queue." />
          )}
          {incidents.status === 'ready' && incidents.data.length > 0 && (
            <div className="incident-list">
              {incidents.data.map((item) => (
                <button
                  className={`incident-item ${selectedId === item.id ? 'selected' : ''}`}
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span><strong>{item.id}</strong><small>{item.robot_type}</small></span>
                  <span className="incident-source">{item.source_type}</span>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="detail-column">
        <Card className="detail-card">
          <CardHeader>
            <div><div className="eyebrow">DIAGNOSTIC WORKSPACE</div><h2>{selected ? selected.id : 'Incident details'}</h2></div>
            {selected && <Badge>{selected.source_type}</Badge>}
          </CardHeader>
          <CardContent>
            {selected ? (
              <div className="incident-detail">
                <dl>
                  <div><dt>Robot</dt><dd>{selected.robot_type}</dd></div>
                  <div><dt>Time window</dt><dd>{selected.time_window}</dd></div>
                  <div><dt>Commanded action</dt><dd>{selected.commanded_action}</dd></div>
                  <div><dt>Fault codes</dt><dd>{selected.fault_codes.length ? selected.fault_codes.join(', ') : 'None supplied'}</dd></div>
                  <div><dt>Readings</dt><dd>{selected.readings.length} supplied · display pending team reading contract</dd></div>
                  <div><dt>Technician note</dt><dd>{selected.technician_note || 'None supplied'}</dd></div>
                </dl>
              </div>
            ) : (
              <EmptyState icon={Activity} title="Select an incident" description="Its readings, fault codes, and notes will appear here once the team adds a case." />
            )}
            <div className="action-bar">
              <span><span className="status-dot muted" /> Diagnosis service not configured</span>
              <Button disabled>Run diagnosis <ArrowRight size={16} /></Button>
            </div>
          </CardContent>
        </Card>
        <div className="hint-card"><ShieldCheck size={18} /><span>Incident provenance is shown from each case file. Diagnosis results will appear here after the provider integration is built.</span></div>
      </div>
    </div>
  )
}

function Feedback() {
  return (
    <Card className="full-card">
      <CardHeader><div><div className="eyebrow">VERIFIED OUTCOMES</div><h2>Technician Feedback</h2></div><Badge>Awaiting diagnosis</Badge></CardHeader>
      <CardContent>
        <EmptyState icon={ClipboardCheck} title="No diagnosis to verify" description="A diagnosis must be recorded before a technician can confirm the cause and fix. The original prediction will remain linked to that confirmation." />
        <div className="step-row"><span>01 <Check size={15} /> Select incident</span><span>02 <Check size={15} /> Record diagnosis</span><span>03 <Check size={15} /> Confirm outcome</span></div>
      </CardContent>
    </Card>
  )
}

function Intelligence({ metrics, reload }: { metrics: LoadState<Metrics>; reload: () => void }) {
  return (
    <div className="intelligence-view">
      <div className="metric-grid">
        {([
          ['Incidents', 'incident_count', FileJson],
          ['Diagnoses', 'diagnosis_count', Stethoscope],
          ['Confirmations', 'confirmation_count', ClipboardCheck],
        ] as const).map(([label, key, Icon]) => (
          <Card className="metric-card" key={key}>
            <div className="metric-top"><span>{label}</span><Icon size={18} /></div>
            <strong>{metrics.status === 'ready' ? metrics.data[key] : '—'}</strong>
            <small>Local records</small>
          </Card>
        ))}
      </div>
      {metrics.status === 'loading' && <LoadingState />}
      {metrics.status === 'error' && <ErrorState message={metrics.message} onRetry={reload} />}
      <Card className="full-card">
        <CardHeader><div><div className="eyebrow">INTEGRATION STATUS</div><h2>Evidence & evaluation</h2></div><Badge>Local baseline</Badge></CardHeader>
        <CardContent>
          <div className="status-list">
            <div><Database size={19} /><span><strong>Local records</strong><small>SQLite is ready to store verified results.</small></span><Badge>{metrics.status === 'ready' ? 'Ready' : 'Pending'}</Badge></div>
            <div><Activity size={19} /><span><strong>Provider requests</strong><small>No provider is configured or called by this baseline.</small></span><Badge>Not configured</Badge></div>
            <div><ChartNoAxesCombined size={19} /><span><strong>Evaluation</strong><small>Results will require real diagnoses and held-out cases.</small></span><Badge>Unavailable</Badge></div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState<View>('diagnostics')
  const [incidents, setIncidents] = useState<LoadState<Incident[]>>({ status: 'loading' })
  const [metrics, setMetrics] = useState<LoadState<Metrics>>({ status: 'loading' })

  function loadIncidents() {
    setIncidents({ status: 'loading' })
    api.incidents().then((data) => setIncidents({ status: 'ready', data }))
      .catch((error: unknown) => setIncidents({ status: 'error', message: String(error) }))
  }

  function loadMetrics() {
    setMetrics({ status: 'loading' })
    api.metrics().then((data) => setMetrics({ status: 'ready', data }))
      .catch((error: unknown) => setMetrics({ status: 'error', message: String(error) }))
  }

  useEffect(() => { loadIncidents(); loadMetrics() }, [])

  const current = navigation.find((item) => item.id === view)!
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><HeartPulse size={23} /></div><div><strong>ROBO<span>MEDIC</span></strong><small>FAULT DIAGNOSTICS</small></div></div>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Primary navigation">
          {navigation.map((item) => <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => setView(item.id)}><item.icon size={18} /><span>{item.label}</span><small>{item.number}</small></button>)}
        </nav>
        <div className="sidebar-footer"><div className="environment"><span className="status-dot" /><span>LOCAL ENVIRONMENT</span></div><p>Project baseline · v0.1</p></div>
      </aside>
      <div className="main-shell">
        <header className="topbar"><span>ROBO MEDIC <span className="topbar-slash">/</span> {current.label.toUpperCase()}</span><Badge>LOCAL BASELINE</Badge></header>
        <main>
          <div className="page-heading"><div><div className="eyebrow">{current.number} / 03 · TECHNICIAN WORKSPACE</div><h1>{current.label}</h1><p>{view === 'diagnostics' ? 'Review incident evidence and prepare a structured diagnosis.' : view === 'feedback' ? 'Record a technician-confirmed cause and fix.' : 'Track recorded evidence and evaluation readiness.'}</p></div><div className="heading-symbol"><current.icon size={30} strokeWidth={1.4} /></div></div>
          {view === 'diagnostics' && <Diagnostics incidents={incidents} reload={loadIncidents} />}
          {view === 'feedback' && <Feedback />}
          {view === 'intelligence' && <Intelligence metrics={metrics} reload={loadMetrics} />}
        </main>
        <footer className="footer"><span>ROBO MEDIC / NIGHT SHIFT</span><span>Local-first diagnostic workspace</span></footer>
      </div>
    </div>
  )
}

