import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowRight, Bot, ChartNoAxesCombined, Check, CheckCircle2, ClipboardCheck,
  Database, HeartPulse, LoaderCircle, Radio, RefreshCw, ShieldCheck,
  Sparkles, Stethoscope, TriangleAlert, Wrench, Zap,
} from 'lucide-react'
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  api,
  type DiagnosisRecord,
  type ConfirmedEvaluationReport,
  type Incident,
  type Metrics,
  type Reading,
  type RepairRecord,
} from './api/client'
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

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <TriangleAlert size={20} />
      <div><strong>Action or data error</strong><p>{message}</p></div>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><RefreshCw size={14} /> Retry</Button>}
    </div>
  )
}

function LoadingState({ label = 'Loading local data…' }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle className="spin" size={18} /> {label}</div>
}

function TelemetryChart({ readings }: { readings: Reading[] }) {
  const sensors = useMemo(() => {
    const set = new Set<string>()
    readings.forEach((r) => { if (r.sensor) set.add(r.sensor.split('.')[0]) })
    return Array.from(set)
  }, [readings])

  const defaultSensor = useMemo(() => {
    return sensors.find((s) => s.startsWith('n20_')) ?? sensors[0] ?? 'power'
  }, [sensors])

  const [activeSensor, setActiveSensor] = useState<string>(defaultSensor)
  useEffect(() => { setActiveSensor(defaultSensor) }, [defaultSensor])

  const { chartData, metricKeys } = useMemo(() => {
    const byTs = new Map<string, Record<string, number | string>>()
    const keys = new Set<string>()
    readings
      .filter((r) => r.sensor.startsWith(activeSensor + '.'))
      .forEach((r) => {
        const shortTs = r.time.includes('T') ? r.time.split('T')[1].replace('Z', '') : r.time
        const row = byTs.get(shortTs) ?? { time: shortTs }
        const metric = r.sensor.startsWith(activeSensor + '.') ? r.sensor.slice(activeSensor.length + 1) : r.sensor
        const label = r.unit ? `${metric} (${r.unit})` : metric
        if (typeof r.value !== 'number') return
        row[label] = r.value
        keys.add(label)
        byTs.set(shortTs, row)
      })
    return { chartData: Array.from(byTs.values()), metricKeys: Array.from(keys) }
  }, [readings, activeSensor])

  const colors = ['#0d9488', '#2563eb', '#d97706', '#dc2626', '#7c3aed']

  if (readings.length === 0) return null

  return (
    <div style={{ marginTop: 18, borderTop: '1px solid #edf1f4', paddingTop: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <span className="eyebrow">LIVE TELEMETRY WAVEFORMS ({readings.length} SAMPLES)</span>
        <div style={{ display: 'flex', gap: 6 }}>
          {sensors.map((s) => (
            <Button
              key={s}
              size="sm"
              variant={activeSensor === s ? 'default' : 'outline'}
              onClick={() => setActiveSensor(s)}
            >
              {s}
            </Button>
          ))}
        </div>
      </div>
      {chartData.length > 1 ? (
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 5, right: 16, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#edf1f4" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#7a8a9a' }} />
              <YAxis tick={{ fontSize: 10, fill: '#7a8a9a' }} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e3eaf0' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {metricKeys.map((k, idx) => (
                <Line
                  key={k}
                  type="monotone"
                  dataKey={k}
                  stroke={colors[idx % colors.length]}
                  strokeWidth={2}
                  dot={{ r: 2 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
          {readings.filter((r) => r.sensor.startsWith(activeSensor + '.')).map((r, i) => (
            <div key={i} style={{ padding: '10px 12px', background: '#f8fafb', borderRadius: 8, border: '1px solid #e5ecef' }}>
              <small style={{ display: 'block', fontSize: 10, color: '#7a8a9a' }}>{r.sensor}</small>
              <strong style={{ fontSize: 15, color: '#182338' }}>{r.value} {r.unit}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Diagnostics({
  incidents,
  diagnoses,
  confirmations,
  simulatorOnline,
  selectedId,
  setSelectedId,
  liveBanner,
  dismissBanner,
  reloadAll,
  onSelectForFeedback,
}: {
  incidents: LoadState<Incident[]>
  diagnoses: DiagnosisRecord[]
  confirmations: RepairRecord[]
  simulatorOnline: boolean
  selectedId: string | null
  setSelectedId: (id: string | null) => void
  liveBanner: Incident | null
  dismissBanner: () => void
  reloadAll: () => void
  onSelectForFeedback: (diagId: string) => void
}) {
  const [diagnosing, setDiagnosing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const selected = incidents.status === 'ready'
    ? incidents.data.find((item) => item.id === selectedId) ?? incidents.data[0] ?? null
    : null

  const latestDiagnosis = useMemo(() => {
    if (!selected) return null
    return diagnoses.find((d) => d.incident_id === selected.id) ?? null
  }, [diagnoses, selected])

  const linkedConfirmation = useMemo(() => {
    if (!latestDiagnosis) return null
    return confirmations.find((c) => c.diagnosis_id === latestDiagnosis.id) ?? null
  }, [confirmations, latestDiagnosis])

  async function handleRunDiagnosis() {
    if (!selected) return
    setDiagnosing(true)
    setActionError(null)
    try {
      await api.diagnose(selected.id)
      reloadAll()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setDiagnosing(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {liveBanner && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '12px 18px',
            background: '#fffbeb',
            border: '1px solid #fde68a',
            borderRadius: 10,
            color: '#92400e',
            fontSize: 13,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Zap size={18} style={{ color: '#d97706', flexShrink: 0 }} />
            <span>
              <strong>New Live Simulator Incident Detected:</strong> <code>{liveBanner.id}</code> —{' '}
              {liveBanner.fault_codes.join(', ')}
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={dismissBanner}>Dismiss</Button>
        </div>
      )}

      <div className="view-grid">
        <Card className="incident-panel">
          <CardHeader>
            <div>
              <div className="eyebrow">REAL-TIME STREAM / INCIDENTS</div>
              <h2>Live Incident Queue</h2>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {incidents.status === 'ready' && <Badge>{incidents.data.length} records</Badge>}
            </div>
          </CardHeader>
          <CardContent>
            {incidents.status === 'loading' && <LoadingState />}
            {incidents.status === 'error' && <ErrorState message={incidents.message} onRetry={reloadAll} />}
            {incidents.status === 'ready' && incidents.data.length === 0 && (
              <EmptyState
                icon={Radio}
                title="Listening to Live Simulator (:8001)"
                description="No incidents have occurred yet. Open the Robot Simulator at http://localhost:8001 and inject any fault or overload — it will automatically pop up here in real time!"
              />
            )}
            {incidents.status === 'ready' && incidents.data.length > 0 && (
              <div className="incident-list">
                {incidents.data.map((item) => {
                  const hasDiag = diagnoses.some((d) => d.incident_id === item.id)
                  const isSel = (selected?.id ?? null) === item.id
                  return (
                    <button
                      className={`incident-item ${isSel ? 'selected' : ''}`}
                      key={item.id}
                      onClick={() => { setSelectedId(item.id); setActionError(null) }}
                    >
                      <span>
                        <strong>{item.id}</strong>
                        <small>{item.fault_codes.join(', ') || item.commanded_action}</small>
                      </span>
                      {hasDiag && <Badge>Diagnosed</Badge>}
                      <span className="incident-source">{item.source_type}</span>
                      <ArrowRight size={16} />
                    </button>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="detail-column">
          {actionError && <ErrorState message={actionError} />}
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
                    <div><dt>Commanded action</dt><dd><code>{selected.commanded_action}</code></dd></div>
                    <div><dt>Fault codes</dt><dd>{selected.fault_codes.length ? selected.fault_codes.join(', ') : 'None supplied'}</dd></div>
                    <div><dt>Live symptom log</dt><dd>{selected.technician_note || 'None supplied'}</dd></div>
                  </dl>
                  <TelemetryChart readings={selected.readings} />
                </div>
              ) : (
                <EmptyState
                  icon={Activity}
                  title="Waiting for live incident"
                  description="Trigger a fault in the simulator at http://localhost:8001. Its live waveforms, fault codes, and telemetry symptoms will appear here automatically."
                />
              )}
              <div className="action-bar">
                <span>
                  <span className="status-dot" /> {simulatorOnline ? 'Simulator intake active (:8001)' : 'Waiting for simulator (:8001)'}
                </span>
                <Button disabled={!selected || diagnosing} onClick={handleRunDiagnosis}>
                  {diagnosing ? <><LoaderCircle className="spin" size={15} /> Analyzing…</> : <>Run diagnosis <Sparkles size={15} /></>}
                </Button>
              </div>
            </CardContent>
          </Card>

          {latestDiagnosis && (
            <Card>
              <CardHeader>
                <div>
                  <div className="eyebrow">STRUCTURED DIAGNOSIS · {latestDiagnosis.model_id}</div>
                  <h2>{latestDiagnosis.diagnosis.cause_label}</h2>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Badge>Uncertainty: {latestDiagnosis.diagnosis.uncertainty}</Badge>
                  {linkedConfirmation && <Badge>{linkedConfirmation.verification_kind === 'inspection' ? 'Inspected' : 'Simulation recorded'} by {linkedConfirmation.verifier}</Badge>}
                </div>
              </CardHeader>
              <CardContent>
                <div className="incident-detail" style={{ padding: 0 }}>
                  <dl>
                    <div>
                      <dt>Supporting evidence</dt>
                      <dd>
                        <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 4 }}>
                          {latestDiagnosis.diagnosis.supporting_evidence.map((ev, i) => <li key={i}><code>{ev.field}</code>: {ev.explanation}</li>)}
                        </ul>
                      </dd>
                    </div>
                    <div><dt>Alternative hypothesis</dt><dd>{latestDiagnosis.diagnosis.alternative}</dd></div>
                    <div><dt>Recommended check / fix</dt><dd><strong>{latestDiagnosis.diagnosis.next_check}</strong></dd></div>
                  </dl>
                </div>
                <div className="action-bar" style={{ padding: '14px 0 0', marginTop: 16 }}>
                  <span>Ref: {latestDiagnosis.request_reference}</span>
                  {linkedConfirmation ? (
                    <span style={{ color: '#0d9488', fontWeight: 700 }}>
                      <Check size={14} style={{ display: 'inline' }} /> Outcome recorded ({linkedConfirmation.fix_performed})
                    </span>
                  ) : (
                    <Button variant="outline" size="sm" onClick={() => onSelectForFeedback(latestDiagnosis.id)}>
                      Verify / Confirm in Feedback <ArrowRight size={14} />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="hint-card">
            <ShieldCheck size={18} />
            <span>
              Robo Medic polls the local simulator for telemetry and faults. Captured incidents are labelled synthetic and remain separate from inspected outcomes.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

function Feedback({
  diagnoses,
  confirmations,
  selectedDiagId,
  onSelectDiagId,
  reloadAll,
}: {
  diagnoses: DiagnosisRecord[]
  confirmations: RepairRecord[]
  selectedDiagId: string | null
  onSelectDiagId: (id: string) => void
  reloadAll: () => void
}) {
  const unconfirmed = useMemo(
    () => diagnoses.filter((d) => !confirmations.some((c) => c.diagnosis_id === d.id)),
    [diagnoses, confirmations]
  )

  const currentDiag = useMemo(() => {
    if (selectedDiagId) {
      const found = diagnoses.find((d) => d.id === selectedDiagId)
      if (found) return found
    }
    return unconfirmed[0] ?? diagnoses[0] ?? null
  }, [diagnoses, unconfirmed, selectedDiagId])

  const [actualCause, setActualCause] = useState('')
  const [fixPerformed, setFixPerformed] = useState('')
  const [inspectionNote, setInspectionNote] = useState('')
  const [verifier, setVerifier] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  useEffect(() => {
    if (currentDiag) {
      setActualCause('')
      setFixPerformed('')
      setInspectionNote('')
      setError(null)
    }
  }, [currentDiag?.id])

  const alreadyConfirmed = useMemo(
    () => (currentDiag ? confirmations.find((c) => c.diagnosis_id === currentDiag.id) : null),
    [confirmations, currentDiag]
  )

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!currentDiag) return
    setSubmitting(true)
    setError(null)
    setSuccessMsg(null)
    try {
      await api.confirm({
        diagnosis_id: currentDiag.id,
        incident_id: currentDiag.incident_id,
        actual_cause: actualCause.trim(),
        fix_performed: fixPerformed.trim(),
        inspection_note: inspectionNote.trim(),
        verifier: verifier.trim(),
        timestamp: new Date().toISOString(),
      })
      setSuccessMsg(`Outcome recorded for ${currentDiag.incident_id}.`)
      reloadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (diagnoses.length === 0) {
    return (
      <Card className="full-card">
        <CardHeader><div><div className="eyebrow">VERIFIED OUTCOMES</div><h2>Technician Feedback</h2></div><Badge>Awaiting diagnosis</Badge></CardHeader>
        <CardContent>
          <EmptyState icon={ClipboardCheck} title="No diagnosis to verify" description="Run a diagnosis on a live incident in the Diagnostics tab first. Then confirm the actual cause and fix here." />
          <div className="step-row"><span>01 <Check size={15} /> Trigger incident in simulator</span><span>02 <Check size={15} /> Record diagnosis</span><span>03 <Check size={15} /> Confirm outcome</span></div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="view-grid">
      <Card className="incident-panel">
        <CardHeader>
          <div><div className="eyebrow">RECORDED DIAGNOSES</div><h2>Select prediction</h2></div>
          <Badge>{unconfirmed.length} pending</Badge>
        </CardHeader>
        <CardContent>
          <div className="incident-list">
            {diagnoses.map((d) => {
              const isConfirmed = confirmations.some((c) => c.diagnosis_id === d.id)
              return (
                <button
                  key={d.id}
                  className={`incident-item ${currentDiag?.id === d.id ? 'selected' : ''}`}
                  onClick={() => { onSelectDiagId(d.id); setSuccessMsg(null) }}
                >
                  <span>
                    <strong>{d.incident_id}</strong>
                    <small>{d.diagnosis.cause_label}</small>
                  </span>
                  <Badge>{isConfirmed ? (d.incident.source_type === 'synthetic' ? 'Simulation recorded' : 'Inspected') : 'Pending'}</Badge>
                  <ArrowRight size={16} />
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      <div className="detail-column">
        {error && <ErrorState message={error} />}
        {successMsg && (
          <div style={{ padding: '12px 16px', background: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: 8, fontSize: 13, color: '#065f46' }}>
            <CheckCircle2 size={16} style={{ display: 'inline', marginRight: 8, verticalAlign: 'text-bottom' }} />
            {successMsg}
          </div>
        )}
        {currentDiag && (
          <Card>
            <CardHeader>
              <div>
                <div className="eyebrow">TECHNICIAN OUTCOME LOG · {currentDiag.incident_id}</div>
                <h2>Verify or override prediction</h2>
              </div>
              <Badge>{alreadyConfirmed ? 'Confirmed' : 'Open for review'}</Badge>
            </CardHeader>
            <CardContent>
              <div style={{ marginBottom: 18, padding: 14, background: '#f8fafb', borderRadius: 8, border: '1px solid #e5ecef', fontSize: 12 }}>
                <div style={{ color: '#627286', marginBottom: 4 }}>Original prediction ({currentDiag.model_id}):</div>
                <strong>{currentDiag.diagnosis.cause_label}</strong>
                <div style={{ marginTop: 6, color: '#547678' }}>Suggested action: {currentDiag.diagnosis.next_check}</div>
              </div>

              {alreadyConfirmed ? (
                <div className="incident-detail" style={{ padding: 0 }}>
                  <dl>
                    <div><dt>Verified actual cause</dt><dd><strong>{alreadyConfirmed.actual_cause}</strong></dd></div>
                    <div><dt>Fix performed</dt><dd>{alreadyConfirmed.fix_performed}</dd></div>
                    <div><dt>Inspection note</dt><dd>{alreadyConfirmed.inspection_note}</dd></div>
                    <div><dt>Evidence kind</dt><dd>{alreadyConfirmed.verification_kind}</dd></div>
                    <div><dt>Verifier ID</dt><dd>{alreadyConfirmed.verifier}</dd></div>
                    <div><dt>Timestamp</dt><dd>{alreadyConfirmed.timestamp}</dd></div>
                  </dl>
                </div>
              ) : (
                <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }}>
                  <label style={{ display: 'grid', gap: 5, fontSize: 12, fontWeight: 600 }}>
                    <span>Actual Root Cause (confirm or correct the label)</span>
                    <input
                      type="text"
                      required
                      value={actualCause}
                      onChange={(e) => setActualCause(e.target.value)}
                      style={{ padding: '9px 12px', borderRadius: 7, border: '1px solid #d6e2e7', fontSize: 13 }}
                    />
                  </label>
                  <label style={{ display: 'grid', gap: 5, fontSize: 12, fontWeight: 600 }}>
                    <span>Physical / Software Fix Performed</span>
                    <textarea
                      required
                      rows={3}
                      value={fixPerformed}
                      onChange={(e) => setFixPerformed(e.target.value)}
                      style={{ padding: '9px 12px', borderRadius: 7, border: '1px solid #d6e2e7', fontSize: 13, fontFamily: 'inherit' }}
                    />
                  </label>
                  <label style={{ display: 'grid', gap: 5, fontSize: 12, fontWeight: 600 }}>
                    <span>{currentDiag.incident.source_type === 'synthetic' ? 'Simulation observation' : 'Physical inspection note'}</span>
                    <textarea required rows={3} value={inspectionNote}
                      onChange={(e) => setInspectionNote(e.target.value)}
                      style={{ padding: '9px 12px', borderRadius: 7, border: '1px solid #d6e2e7', fontSize: 13, fontFamily: 'inherit' }} />
                  </label>
                  <label style={{ display: 'grid', gap: 5, fontSize: 12, fontWeight: 600 }}>
                    <span>Verifier Callsign / Technician ID</span>
                    <input
                      type="text"
                      required
                      value={verifier}
                      onChange={(e) => setVerifier(e.target.value)}
                      style={{ padding: '9px 12px', borderRadius: 7, border: '1px solid #d6e2e7', fontSize: 13 }}
                    />
                  </label>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                    <Button type="submit" disabled={submitting}>
                      <Wrench size={15} /> {submitting ? 'Saving confirmation…' : 'Record Confirmed Outcome'}
                    </Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

function Intelligence({
  metrics, evaluations, confirmations, reloadAll,
}: {
  metrics: LoadState<Metrics>
  evaluations: ConfirmedEvaluationReport
  confirmations: RepairRecord[]
  reloadAll: () => void
}) {
  const groups = evaluations.groups
  const evaluated = groups.reduce((sum, group) => sum + group.total, 0)
  const matched = groups.reduce((sum, group) => sum + group.matched, 0)
  const simulated = confirmations.filter((item) => item.verification_kind === 'synthetic_simulation').length

  return (
    <div className="intelligence-view">
      <div className="metric-grid">
        {([
          ['Incidents', 'incident_count', Radio],
          ['Diagnoses', 'diagnosis_count', Stethoscope],
          ['Outcomes', 'confirmation_count', ClipboardCheck],
        ] as const).map(([label, key, Icon]) => (
          <Card className="metric-card" key={key}>
            <div className="metric-top"><span>{label}</span><Icon size={18} /></div>
            <strong>{metrics.status === 'ready' ? metrics.data[key] : '?'}</strong>
            <small>Persisted local records</small>
          </Card>
        ))}
      </div>
      {metrics.status === 'loading' && <LoadingState />}
      {metrics.status === 'error' && <ErrorState message={metrics.message} onRetry={reloadAll} />}

      <Card className="full-card">
        <CardHeader>
          <div><div className="eyebrow">INSPECTED OUTCOMES</div><h2>Confirmed Evaluation</h2></div>
          {evaluated > 0 && <Badge>Accuracy: {Math.round(matched / evaluated * 100)}% ({matched}/{evaluated})</Badge>}
        </CardHeader>
        <CardContent>
          {evaluated > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead><tr style={{ textAlign: 'left', borderBottom: '1px solid #e3eaf0' }}>
                  <th>Incident</th><th>Inspected cause</th><th>Prediction</th><th>Provider</th><th>Result</th>
                </tr></thead>
                <tbody>
                  {groups.flatMap((group) => group.cases.map((item) => (
                    <tr key={item.diagnosis_id} style={{ borderBottom: '1px solid #f0f3f5' }}>
                      <td>{item.incident_id}</td><td>{item.actual_cause}</td>
                      <td>{item.predicted_cause}</td><td>{group.provider_kind} / {group.model_id}</td>
                      <td>{item.matched ? 'MATCH' : 'MISMATCH'}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon={ChartNoAxesCombined} title="No inspected outcomes yet"
              description="A technician must record a physical inspection before an outcome contributes to confirmed accuracy." />
          )}
          <p style={{ marginTop: 16, fontSize: 12, color: '#627286' }}>
            {simulated} simulator outcome(s) recorded separately from inspected accuracy.
          </p>
        </CardContent>
      </Card>

      <Card className="full-card">
        <CardHeader><div><div className="eyebrow">INTEGRATION STATUS</div><h2>System status</h2></div></CardHeader>
        <CardContent>
          <div className="status-list">
            <div><Database size={19} /><span><strong>Local SQLite store</strong><small>Diagnosis and outcome records persist across restarts.</small></span><Badge>{metrics.status === 'ready' ? 'Ready' : 'Pending'}</Badge></div>
            <div><Activity size={19} /><span><strong>Diagnosis provider</strong><small>Configured provider and evidence validation.</small></span><Badge>{metrics.status === 'ready' ? metrics.data.provider_status : 'Pending'}</Badge></div>
            <div><Bot size={19} /><span><strong>Simulator intake</strong><small>Local synthetic telemetry from port 8001.</small></span><Badge>{metrics.status === 'ready' && metrics.data.simulator_online ? 'Online' : 'Offline'}</Badge></div>
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
  const [diagnoses, setDiagnoses] = useState<DiagnosisRecord[]>([])
  const [confirmations, setConfirmations] = useState<RepairRecord[]>([])
  const [evaluations, setEvaluations] = useState<ConfirmedEvaluationReport>({ source: 'technician_confirmed', groups: [] })
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null)
  const [selectedFeedbackDiagId, setSelectedFeedbackDiagId] = useState<string | null>(null)
  const [liveBanner, setLiveBanner] = useState<Incident | null>(null)
  const knownIncidentIdsRef = useRef<Set<string>>(new Set())
  const initializedRef = useRef<boolean>(false)

  function reloadAll() {
    api.incidents()
      .then((data) => {
        setIncidents({ status: 'ready', data })
        if (!initializedRef.current) {
          knownIncidentIdsRef.current = new Set(data.map((i) => i.id))
          initializedRef.current = true
          if (data.length > 0 && !selectedIncidentId) {
            setSelectedIncidentId(data[0].id)
          }
        } else {
          const newOnes = data.filter((i) => !knownIncidentIdsRef.current.has(i.id))
          if (newOnes.length > 0) {
            newOnes.forEach((i) => knownIncidentIdsRef.current.add(i.id))
            const newest = newOnes[0]
            setSelectedIncidentId(newest.id)
            setLiveBanner(newest)
          }
          if (data.length === 0) {
            knownIncidentIdsRef.current.clear()
          }
        }
      })
      .catch((error: unknown) => setIncidents({ status: 'error', message: String(error) }))

    api.metrics()
      .then((data) => setMetrics({ status: 'ready', data }))
      .catch((error: unknown) => setMetrics({ status: 'error', message: String(error) }))

    api.diagnoses().then(setDiagnoses).catch(() => {})
    api.repairs().then(setConfirmations).catch(() => {})
    api.confirmedEvaluation().then(setEvaluations).catch(() => {})
  }

  useEffect(() => {
    reloadAll()
    const timer = window.setInterval(reloadAll, 1200)
    return () => window.clearInterval(timer)
  }, [])

  const current = navigation.find((item) => item.id === view)!
  const simOnline = metrics.status === 'ready' && metrics.data.simulator_online

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><HeartPulse size={23} /></div><div><strong>ROBO<span>MEDIC</span></strong><small>FAULT DIAGNOSTICS</small></div></div>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Primary navigation">
          {navigation.map((item) => (
            <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => setView(item.id)}>
              <item.icon size={18} /><span>{item.label}</span><small>{item.number}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="environment">
            <span className="status-dot" />
            <span>{simOnline ? 'LIVE SIMULATOR (:8001)' : 'WAITING FOR SIM (:8001)'}</span>
          </div>
          <p>Simulator fault stream · v0.3</p>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>ROBO MEDIC <span className="topbar-slash">/</span> {current.label.toUpperCase()}</span>
          <div style={{ display: 'flex', gap: 8 }}>
            {simOnline && <Badge>LIVE STREAM (:8001)</Badge>}
            <Badge>BACKEND PROVIDER</Badge>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">{current.number} / 03 · REAL-TIME TELEMETRY WORKSPACE</div>
              <h1>{current.label}</h1>
              <p>
                {view === 'diagnostics'
                  ? 'Faults injected or triggered in the simulator (:8001) automatically pop up here with live waveforms.'
                  : view === 'feedback'
                  ? 'Record a cause, performed fix, and inspection or simulation observation.'
                  : 'Review inspected outcome accuracy and separate simulator records.'}
              </p>
            </div>
            <div className="heading-symbol"><current.icon size={30} strokeWidth={1.4} /></div>
          </div>
          {view === 'diagnostics' && (
            <Diagnostics
              incidents={incidents}
              diagnoses={diagnoses}
              confirmations={confirmations}
              simulatorOnline={simOnline}
              selectedId={selectedIncidentId}
              setSelectedId={setSelectedIncidentId}
              liveBanner={liveBanner}
              dismissBanner={() => setLiveBanner(null)}
              reloadAll={reloadAll}
              onSelectForFeedback={(diagId) => {
                setSelectedFeedbackDiagId(diagId)
                setView('feedback')
              }}
            />
          )}
          {view === 'feedback' && (
            <Feedback
              diagnoses={diagnoses}
              confirmations={confirmations}
              selectedDiagId={selectedFeedbackDiagId}
              onSelectDiagId={setSelectedFeedbackDiagId}
              reloadAll={reloadAll}
            />
          )}
          {view === 'intelligence' && (
            <Intelligence
              metrics={metrics}
              evaluations={evaluations}
              confirmations={confirmations}
              reloadAll={reloadAll}
            />
          )}
        </main>
        <footer className="footer"><span>ROBO MEDIC / NIGHT SHIFT</span><span>Simulator intake and verified outcomes</span></footer>
      </div>
    </div>
  )
}
