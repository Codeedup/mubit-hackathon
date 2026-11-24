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
import { Setup } from './views/Setup'
import { CaseTools } from './components/CaseTools'
import { Download, Moon, Sun, Activity, ExternalLink } from 'lucide-react'

type View = 'bench' | 'loop' | 'setup'
const POLL_MS = 3000

function currentView(): View {
  const hash = window.location.hash.slice(1)
  return hash === 'loop' || hash === 'setup' ? hash : 'bench'
}

export default function App() {
  const [view, setView] = useState<View>(currentView)
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('robo-medic.theme') ?? 'light'
    } catch {
      return 'light'
    }
  })
  const [simulatorUrl, setSimulatorUrl] = useState('http://127.0.0.1:8001')
  const [incidents, setIncidents] = useState<Incident[] | null>(null)
  const [diagnoses, setDiagnoses] = useState<DiagnosisRecord[]>([])
  const [repairs, setRepairs] = useState<RepairRecord[]>([])
  const [evaluation, setEvaluation] =
    useState<ConfirmedEvaluationReport | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [backendError, setBackendError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [runs, setRuns] = useState<Record<string, DiagnoseState>>({})
  const [roundTrip, setRoundTrip] = useState<Record<string, number>>({})
  const [focused, setFocused] = useState<string | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  const known = useRef<Set<string> | null>(null)
  const reloading = useRef(false)
  const inFlight = useRef(new Set<string>())

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('robo-medic.theme', theme)
    } catch {
      /* Theme still works for this session. */
    }
  }, [theme])
  useEffect(() => {
    void api
      .setup()
      .then((info) => setSimulatorUrl(info.simulator_url))
      .catch(() => {})
    const onHash = () => setView(currentView())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  function navigate(next: View) {
    setView(next)
    window.location.hash = next
  }

  const reload = useCallback(async () => {
    if (reloading.current) return
    reloading.current = true
    try {
      const [inc, diag, rep, evalReport, met] = await Promise.allSettled([
        api.incidents(),
        api.diagnoses(),
        api.repairs(),
        api.confirmedEvaluation(),
        api.metrics(),
      ])
      if (inc.status === 'rejected') {
        setBackendError(
          inc.reason instanceof Error ? inc.reason.message : String(inc.reason),
        )
        return
      }
      const failed = [diag, rep, evalReport, met].filter(
        (result) => result.status === 'rejected',
      )
      setBackendError(
        failed.length
          ? 'Some workspace records could not be refreshed. Your last loaded records remain visible.'
          : null,
      )
      const list = inc.value
      // Anything that appears after the first load is a live capture worth pointing out.
      if (known.current) {
        const added = list
          .filter(
            (item) =>
              caseKind(item.id) === 'captured' && !known.current!.has(item.id),
          )
          .map((item) => item.id)
        if (added.length) setFresh((current) => new Set([...current, ...added]))
      }
      // Pin the opening case so a live capture never swaps the bench out from under someone.
      if (!known.current && list.length)
        setSelectedId((current) => current ?? defaultCase(list).id)
      known.current = new Set(list.map((item) => item.id))
      setIncidents(list)
      if (diag.status === 'fulfilled') setDiagnoses(diag.value)
      if (rep.status === 'fulfilled') setRepairs(rep.value)
      if (evalReport.status === 'fulfilled') setEvaluation(evalReport.value)
      if (met.status === 'fulfilled') setMetrics(met.value)
    } finally {
      reloading.current = false
    }
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
    return (
      incidents.find((item) => item.id === selectedId) ?? defaultCase(incidents)
    )
  }, [incidents, selectedId])

  const record = selected
    ? (diagnoses.find(
        (item) => item.id === selectedRunId && item.incident_id === selected.id,
      ) ?? latestFor(selected.id, diagnoses))
    : null
  const earlier = useMemo(
    () =>
      selected && record
        ? diagnoses
            .filter(
              (item) =>
                item.incident_id === selected.id && item.id !== record.id,
            )
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
        : [],
    [diagnoses, selected, record],
  )
  const repair = record
    ? (repairs.find((item) => item.diagnosis_id === record.id) ?? null)
    : null
  const cited = useMemo(
    () => citedTargets(record?.diagnosis.supporting_evidence),
    [record],
  )
  const newestFresh = useMemo(
    () =>
      incidents
        ?.filter((item) => fresh.has(item.id) && !latestFor(item.id, diagnoses))
        .sort((a, b) => b.id.localeCompare(a.id))[0] ?? null,
    [incidents, fresh, diagnoses],
  )

  function select(id: string) {
    setSelectedId(id)
    setSelectedRunId(null)
    setFocused(null)
    setFresh((current) => new Set([...current].filter((value) => value !== id)))
    navigate('bench')
  }
  function openRun(id: string) {
    const run = diagnoses.find((item) => item.id === id)
    if (run) {
      select(run.incident_id)
      setSelectedRunId(id)
    }
  }

  async function diagnose() {
    if (!selected) return
    const id = selected.id
    if (inFlight.current.has(id)) return
    inFlight.current.add(id)
    const startedAt = performance.now()
    setRuns((current) => ({
      ...current,
      [id]: { status: 'pending', startedAt: Date.now() },
    }))
    try {
      const result = await api.diagnose(id)
      setRoundTrip((current) => ({
        ...current,
        [result.id]: performance.now() - startedAt,
      }))
      setDiagnoses((current) => [
        result,
        ...current.filter((item) => item.id !== result.id),
      ])
      setSelectedRunId(result.id)
      setRuns((current) => ({ ...current, [id]: { status: 'idle' } }))
      void reload()
    } catch (err) {
      setRuns((current) => ({
        ...current,
        [id]: {
          status: 'error',
          message: err instanceof Error ? err.message : String(err),
        },
      }))
    } finally {
      inFlight.current.delete(id)
    }
  }

  const providerModel = diagnoses.find(
    (item) => item.provider_kind === 'mubit',
  )?.model_id

  return (
    <div className="app">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <header className="masthead">
        <div className="brand">
          <BrandMark />
          <span>Robo Medic</span>
        </div>
        <nav className="views" aria-label="Views">
          <button
            className={view === 'bench' ? 'on' : undefined}
            aria-current={view === 'bench' ? 'page' : undefined}
            onClick={() => navigate('bench')}
          >
            Diagnostics
          </button>
          <button
            className={view === 'loop' ? 'on' : undefined}
            aria-current={view === 'loop' ? 'page' : undefined}
            onClick={() => navigate('loop')}
          >
            History & evaluation
          </button>
          <button
            className={view === 'setup' ? 'on' : undefined}
            aria-current={view === 'setup' ? 'page' : undefined}
            onClick={() => navigate('setup')}
          >
            Setup
          </button>
        </nav>
        <div className="signals" aria-label="System status">
          <span
            className={`signal provider-${metrics?.provider_status ?? 'unknown'}`}
          >
            {providerText(metrics?.provider_status, providerModel)}
          </span>
          <span
            className={`signal ${metrics?.simulator_online ? 'sim-on' : 'sim-off'}`}
          >
            {metrics?.simulator_online ? 'Simulator live' : 'Simulator offline'}
          </span>
        </div>
        <div className="header-actions">
          <a
            className="icon-btn"
            href="/api/export"
            download
            aria-label="Export workspace"
            title="Export workspace"
          >
            <Download size={18} />
          </a>
          <button
            className="icon-btn"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={
              theme === 'dark'
                ? 'Switch to light theme'
                : 'Switch to dark theme'
            }
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      {view === 'bench' && (
        <>
          <section
            className="workspace-intro"
            aria-labelledby="workspace-title"
          >
            <div>
              <p className="eyebrow">
                <Activity size={14} /> Robot maintenance workspace
              </p>
              <h1 id="workspace-title">Turn a fault into a next step.</h1>
              <p>
                Inspect the readings. Review a diagnosis. Record what fixed it.
              </p>
            </div>
            <CaseTools
              onCreated={(incident) => {
                setIncidents((current) => [
                  incident,
                  ...(current ?? []).filter((item) => item.id !== incident.id),
                ])
                select(incident.id)
                void reload()
              }}
            />
          </section>
          <div className="workspace-bar">
            <div className="workspace-counts">
              <span>
                <strong>{incidents?.length ?? '–'}</strong> cases
              </span>
              <span>
                <strong>{diagnoses.length}</strong> diagnoses
              </span>
              <span>
                <strong>{repairs.length}</strong> outcomes
              </span>
            </div>
            <span className="mode-note">
              {metrics?.provider_status === 'local_fixture'
                ? 'Offline demo · deterministic rules'
                : metrics?.provider_status === 'mubit'
                  ? 'Live classification through Mubit'
                  : 'Choose a provider in Setup'}
            </span>
            {metrics?.simulator_online && (
              <a href={simulatorUrl} target="_blank" rel="noreferrer">
                Open simulator <ExternalLink size={14} />
              </a>
            )}
          </div>
        </>
      )}

      {backendError && (
        <div className="notice notice-error page-notice" role="alert">
          <strong>Workspace needs attention.</strong>
          <p>
            {backendError}. Check that the app is running; this page reconnects
            automatically.
          </p>
        </div>
      )}

      {newestFresh && view === 'bench' && newestFresh.id !== selected?.id && (
        <div className="capture-strip" role="status">
          <span>
            New capture from the simulator:{' '}
            <strong>{caseTitle(newestFresh)}</strong>
          </span>
          <button
            className="btn btn-small"
            onClick={() => select(newestFresh.id)}
          >
            Open it
          </button>
        </div>
      )}

      {view === 'bench' && (
        <main className="bench" id="workspace" tabIndex={-1}>
          {incidents === null && !backendError && (
            <p className="quiet loading">Loading cases…</p>
          )}
          {incidents && incidents.length === 0 && (
            <div className="bench-empty">
              <h1>No cases yet</h1>
              <p>
                Create a demo case above or import an incident to get started.
              </p>
            </div>
          )}
          {incidents && incidents.length > 0 && selected && (
            <>
              <Queue
                incidents={incidents}
                diagnoses={diagnoses}
                repairs={repairs}
                selectedId={selected.id}
                fresh={fresh}
                onSelect={select}
              />
              <IncidentSheet
                incident={record?.incident ?? selected}
                cited={cited}
                focused={focused}
                markKey={`${selected.id}:${record?.id ?? 'none'}`}
              />
              <DiagnosisSheet
                key={selected.id}
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
                onOpenRecord={openRun}
              />
            </>
          )}
        </main>
      )}

      {view === 'loop' && incidents && (
        <main className="loop-main" id="workspace" tabIndex={-1}>
          <Loop
            incidents={incidents}
            diagnoses={diagnoses}
            repairs={repairs}
            evaluation={evaluation}
            metrics={metrics}
            onOpenCase={select}
            onOpenRecord={openRun}
          />
        </main>
      )}
      {view === 'setup' && (
        <main className="loop-main" id="workspace" tabIndex={-1}>
          <Setup />
        </main>
      )}
      <footer className="app-footer">
        <span>
          Robo Medic <small>v1.0</small>
        </span>
        <span>Evidence first. Technician verified.</span>
        <a
          href="https://github.com/Codeedup/mubit-hackathon"
          target="_blank"
          rel="noreferrer"
        >
          View source
        </a>
      </footer>
    </div>
  )
}

function defaultCase(incidents: Incident[]): Incident {
  const captured = incidents
    .filter((item) => caseKind(item.id) === 'captured')
    .sort((a, b) => b.id.localeCompare(a.id))
  return (
    incidents.find((item) => item.id === 'DEV-001') ??
    captured[0] ??
    [...incidents].sort((a, b) => a.id.localeCompare(b.id))[0]
  )
}

function providerText(
  status: Metrics['provider_status'] | undefined,
  model?: string,
): string {
  switch (status) {
    case 'mubit':
      return model ? `Mubit · ${model}` : 'Mubit configured'
    case 'local_fixture':
      return 'Offline demo'
    case 'missing_credentials':
      return 'Mubit key missing'
    case 'not_configured':
      return 'No provider set'
    default:
      return 'Connecting…'
  }
}

/** A heartbeat drawn as a scope trace. */
function BrandMark() {
  return (
    <svg
      className="brand-mark"
      viewBox="0 0 28 28"
      width="28"
      height="28"
      aria-hidden="true"
    >
      <rect
        x="0.5"
        y="0.5"
        width="27"
        height="27"
        rx="6"
        className="brand-mark-bg"
      />
      <path d="M3 15h6l2-5 3 10 3-12 2 7h6" className="brand-mark-trace" />
    </svg>
  )
}
