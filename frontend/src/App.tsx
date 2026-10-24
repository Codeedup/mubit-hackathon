import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  type ConfirmedEvaluationReport,
  type DiagnosisRecord,
  type Incident,
  type Metrics,
  type RepairRecord,
} from './api/client'
import { DiagnosisSheet, type DiagnoseState } from './components/DiagnosisSheet'
import { IncidentSheet } from './components/IncidentSheet'
import { Queue } from './components/Queue'
import { caseKind, caseTitle, citedTargets, latestFor } from './lib/incident'
import { Loop } from './views/Loop'

type View = 'bench' | 'loop'
const POLL_MS = 1500

export default function App() {
  const [view, setView] = useState<View>('bench')
  const [incidents, setIncidents] = useState<Incident[] | null>(null)
  const [diagnoses, setDiagnoses] = useState<DiagnosisRecord[]>([])
  const [repairs, setRepairs] = useState<RepairRecord[]>([])
  const [evaluation, setEvaluation] = useState<ConfirmedEvaluationReport | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [backendError, setBackendError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runs, setRuns] = useState<Record<string, DiagnoseState>>({})
  const [roundTrip, setRoundTrip] = useState<Record<string, number>>({})
  const [focused, setFocused] = useState<string | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  const known = useRef<Set<string> | null>(null)

  const reload = useCallback(async () => {
    const [inc, diag, rep, evalReport, met] = await Promise.allSettled([
      api.incidents(), api.diagnoses(), api.repairs(), api.confirmedEvaluation(), api.metrics(),
    ])
    if (inc.status === 'rejected') {
      setBackendError(inc.reason instanceof Error ? inc.reason.message : String(inc.reason))
      return
    }
    setBackendError(null)
    const list = inc.value
    // Anything that appears after the first load is a live capture worth pointing out.
    if (known.current) {
      const added = list.filter((item) => !known.current!.has(item.id)).map((item) => item.id)
      if (added.length) setFresh((current) => new Set([...current, ...added]))
    }
    // Pin the opening case so a live capture never swaps the bench out from under someone.
    if (!known.current && list.length) setSelectedId((current) => current ?? defaultCase(list).id)
    known.current = new Set(list.map((item) => item.id))
    setIncidents(list)
    if (diag.status === 'fulfilled') setDiagnoses(diag.value)
    if (rep.status === 'fulfilled') setRepairs(rep.value)
    if (evalReport.status === 'fulfilled') setEvaluation(evalReport.value)
    if (met.status === 'fulfilled') setMetrics(met.value)
  }, [])

  useEffect(() => {
    void reload()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void reload()
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [reload])

  const selected = useMemo(() => {
    if (!incidents?.length) return null
    return incidents.find((item) => item.id === selectedId) ?? defaultCase(incidents)
  }, [incidents, selectedId])

  const record = selected ? latestFor(selected.id, diagnoses) : null
  const earlier = useMemo(
    () => (selected && record
      ? diagnoses.filter((item) => item.incident_id === selected.id && item.id !== record.id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
      : []),
    [diagnoses, selected, record],
  )
  const repair = record ? repairs.find((item) => item.diagnosis_id === record.id) ?? null : null
  const cited = useMemo(() => citedTargets(record?.diagnosis.supporting_evidence), [record])
  const newestFresh = useMemo(
    () => incidents?.filter((item) => fresh.has(item.id) && !latestFor(item.id, diagnoses))
      .sort((a, b) => b.id.localeCompare(a.id))[0] ?? null,
    [incidents, fresh, diagnoses],
  )

  function select(id: string) {
    setSelectedId(id)
    setFocused(null)
    setView('bench')
  }

  async function diagnose() {
    if (!selected) return
    const id = selected.id
    const startedAt = performance.now()
    setRuns((current) => ({ ...current, [id]: { status: 'pending', startedAt: Date.now() } }))
    try {
      const result = await api.diagnose(id)
      setRoundTrip((current) => ({ ...current, [result.id]: performance.now() - startedAt }))
      setDiagnoses((current) => [result, ...current.filter((item) => item.id !== result.id)])
      setRuns((current) => ({ ...current, [id]: { status: 'idle' } }))
      void reload()
    } catch (err) {
      setRuns((current) => ({
        ...current,
        [id]: { status: 'error', message: err instanceof Error ? err.message : String(err) },
      }))
    }
  }

  const providerModel = diagnoses.find((item) => item.provider_kind === 'mubit')?.model_id

  return (
    <div className="app">
      <header className="masthead">
        <div className="brand">
          <BrandMark />
          <span>Robo Medic</span>
        </div>
        <nav className="views" aria-label="Views">
          <button className={view === 'bench' ? 'on' : undefined} aria-current={view === 'bench' ? 'page' : undefined} onClick={() => setView('bench')}>Bench</button>
          <button className={view === 'loop' ? 'on' : undefined} aria-current={view === 'loop' ? 'page' : undefined} onClick={() => setView('loop')}>Learning loop</button>
        </nav>
        <div className="signals" aria-label="System status">
          <span className={`signal provider-${metrics?.provider_status ?? 'unknown'}`}>
            {providerText(metrics?.provider_status, providerModel)}
          </span>
          <span className={`signal ${metrics?.simulator_online ? 'sim-on' : 'sim-off'}`}>
            {metrics?.simulator_online ? 'Simulator live' : 'Simulator offline'}
          </span>
        </div>
      </header>

      {backendError && (
        <div className="notice notice-error page-notice" role="alert">
          <strong>Can’t reach the backend.</strong>
          <p>{backendError}. Start it with <code>uvicorn backend.app.main:app --port 8000</code>; this page retries every few seconds.</p>
        </div>
      )}

      {newestFresh && view === 'bench' && newestFresh.id !== selected?.id && (
        <div className="capture-strip" role="status">
          <span>New capture from the simulator: <strong>{caseTitle(newestFresh)}</strong></span>
          <button className="btn btn-small" onClick={() => select(newestFresh.id)}>Open it</button>
        </div>
      )}

      {view === 'bench' && (
        <main className="bench">
          {incidents === null && !backendError && <p className="quiet loading">Loading cases…</p>}
          {incidents && incidents.length === 0 && (
            <div className="bench-empty">
              <h1>No cases yet</h1>
              <p>Inject a fault from the simulator dashboard at localhost:8001. The capture appears here within a second.</p>
            </div>
          )}
          {incidents && incidents.length > 0 && selected && (
            <>
              <Queue incidents={incidents} diagnoses={diagnoses} repairs={repairs}
                selectedId={selected.id} fresh={fresh} onSelect={select} />
              <IncidentSheet incident={record?.incident ?? selected} cited={cited} focused={focused}
                markKey={`${selected.id}:${record?.id ?? 'none'}`} />
              <DiagnosisSheet
                incidentId={selected.id}
                record={record}
                earlier={earlier}
                repair={repair}
                state={runs[selected.id] ?? { status: 'idle' }}
                roundTrip={roundTrip}
                provider={metrics?.provider_status ?? null}
                onDiagnose={diagnose}
                onFocusEvidence={setFocused}
                onRecorded={() => void reload()}
              />
            </>
          )}
        </main>
      )}

      {view === 'loop' && incidents && (
        <main className="loop-main">
          <Loop incidents={incidents} diagnoses={diagnoses} repairs={repairs}
            evaluation={evaluation} metrics={metrics} onOpenCase={select} />
        </main>
      )}
    </div>
  )
}

function defaultCase(incidents: Incident[]): Incident {
  const captured = incidents.filter((item) => caseKind(item.id) === 'captured')
    .sort((a, b) => b.id.localeCompare(a.id))
  return captured[0] ?? [...incidents].sort((a, b) => a.id.localeCompare(b.id))[0]
}

function providerText(status: Metrics['provider_status'] | undefined, model?: string): string {
  switch (status) {
    case 'mubit': return model ? `${model} via Mubit` : 'Mubit gateway'
    case 'local_fixture': return 'Offline fixture, not Mubit'
    case 'missing_credentials': return 'Mubit key missing'
    case 'not_configured': return 'No provider set'
    default: return 'Connecting…'
  }
}

/** A heartbeat drawn as a scope trace. */
function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 28 28" width="28" height="28" aria-hidden="true">
      <rect x="0.5" y="0.5" width="27" height="27" rx="6" className="brand-mark-bg" />
      <path d="M3 15h6l2-5 3 10 3-12 2 7h6" className="brand-mark-trace" />
    </svg>
  )
}
