import { useEffect, useState } from 'react'
import type { DiagnosisRecord, Metrics, RepairRecord } from '../api/client'
import { evidenceTarget, relativeTime, shortRequestId } from '../lib/incident'
import { OutcomeForm } from './OutcomeForm'

export type DiagnoseState =
  | { status: 'idle' }
  | { status: 'pending'; startedAt: number }
  | { status: 'error'; message: string }

type Props = {
  incidentId: string
  record: DiagnosisRecord | null
  earlier: DiagnosisRecord[]
  repair: RepairRecord | null
  state: DiagnoseState
  /** Round-trip time measured by this browser for the most recent run, by diagnosis ID. */
  roundTrip: Record<string, number>
  provider: Metrics['provider_status'] | null
  onDiagnose: () => void
  onFocusEvidence: (target: string | null) => void
  onRecorded: () => void
}

const UNCERTAINTY = ['low', 'medium', 'high'] as const

export function providerLine(record: DiagnosisRecord): string {
  return record.provider_kind === 'mubit'
    ? `${record.model_id} through Mubit`
    : 'the offline rule fixture (not a model)'
}

export function DiagnosisSheet(props: Props) {
  const { record, state, provider, onDiagnose } = props
  const canDiagnose = provider === 'mubit' || provider === 'local_fixture'
  const pending = state.status === 'pending'

  return (
    <section className="sheet diagnosis-sheet" aria-labelledby="diagnosis-heading" aria-busy={pending}>
      {pending && <Pending startedAt={state.startedAt} provider={provider} />}
      {!pending && state.status === 'error' && (
        <div className="notice notice-error" role="alert">
          <strong>The diagnosis was not saved.</strong>
          <p>{state.message}</p>
        </div>
      )}
      {!pending && !record && (
        <div className="diagnosis-empty">
          <h2 id="diagnosis-heading">No diagnosis yet</h2>
          <p>
            {provider === 'mubit' && 'Send this case to Gemini through Mubit. The answer must cite fields from the incident or it is rejected.'}
            {provider === 'local_fixture' && 'The backend is using the offline rule fixture. Set ROBO_MEDIC_PROVIDER=mubit to diagnose through Mubit.'}
            {provider === 'missing_credentials' && 'Mubit is selected but the backend has no MUBIT_API_KEY. Add it to .env and restart the backend.'}
            {provider === 'not_configured' && 'No diagnosis provider is set. Set ROBO_MEDIC_PROVIDER=mubit in .env and restart the backend.'}
            {provider === null && 'Checking the backend…'}
          </p>
          <button className="btn btn-primary" onClick={onDiagnose} disabled={!canDiagnose}>
            {provider === 'local_fixture' ? 'Diagnose with fixture' : 'Diagnose through Mubit'}
          </button>
        </div>
      )}
      {!pending && record && <Result {...props} record={record} canDiagnose={canDiagnose} />}
    </section>
  )
}

function Pending({ startedAt, provider }: { startedAt: number; provider: Metrics['provider_status'] | null }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 100)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="pending" role="status">
      <div className="pending-pen" aria-hidden="true" />
      <h2 id="diagnosis-heading">
        {provider === 'mubit' ? 'Waiting for Gemini through Mubit' : 'Running the fixture'}
      </h2>
      <p className="pending-time">{((now - startedAt) / 1000).toFixed(1)} s</p>
      <p>The backend checks every cited field against the incident before saving.</p>
    </div>
  )
}

function Result({
  record, earlier, repair, roundTrip, onDiagnose, onFocusEvidence, onRecorded, canDiagnose,
}: Props & { record: DiagnosisRecord; canDiagnose: boolean }) {
  const diagnosis = record.diagnosis
  const [copied, setCopied] = useState(false)
  const trip = roundTrip[record.id]

  async function copyReference() {
    try {
      await navigator.clipboard.writeText(record.request_reference)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch { /* Clipboard can be blocked; the ID stays visible to select by hand. */ }
  }

  function jumpTo(target: string | null) {
    if (!target) return
    document.querySelector(`[data-target="${target}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  return (
    <>
      <p className="by-line">Diagnosis from {providerLine(record)}, {relativeTime(record.created_at)}</p>
      <h2 id="diagnosis-heading" className={`cause cause-${diagnosis.cause_label.split(/[ /]/)[0]}`}>
        {diagnosis.cause_label === 'unknown' ? 'Cause unknown' : capitalise(diagnosis.cause_label)}
      </h2>

      <div className="uncertainty" aria-label={`Uncertainty ${diagnosis.uncertainty}`}>
        <span className="uncertainty-label">Uncertainty</span>
        <span className="uncertainty-scale" aria-hidden="true">
          {UNCERTAINTY.map((level) => (
            <span key={level} className={level === diagnosis.uncertainty ? 'on' : undefined}>{level}</span>
          ))}
        </span>
      </div>

      <h3 className="part-heading">Evidence it cited</h3>
      <ol className="evidence">
        {diagnosis.supporting_evidence.map((item, index) => {
          const target = evidenceTarget(item.field)
          return (
            <li key={index}>
              <button
                className="evidence-field"
                onMouseEnter={() => onFocusEvidence(target)}
                onMouseLeave={() => onFocusEvidence(null)}
                onFocus={() => onFocusEvidence(target)}
                onBlur={() => onFocusEvidence(null)}
                onClick={() => jumpTo(target)}
                aria-label={`Show ${item.field} in the incident`}
              >
                {item.field}
              </button>
              <p>{item.explanation}</p>
            </li>
          )
        })}
      </ol>

      <div className="two-up">
        <div>
          <h3 className="part-heading">If it is not that</h3>
          <p>{diagnosis.alternative}</p>
        </div>
        <div>
          <h3 className="part-heading">Check next</h3>
          <p>{diagnosis.next_check}</p>
          <p className="advisory">Advice only. A technician does any physical check.</p>
        </div>
      </div>

      <dl className="provenance">
        <div>
          <dt>{record.provider_kind === 'mubit' ? 'Mubit request' : 'Fixture run'}</dt>
          <dd>
            <code title={record.request_reference}>{shortRequestId(record.request_reference)}</code>
            <button className="link-btn" onClick={copyReference}>{copied ? 'Copied' : 'Copy'}</button>
          </dd>
        </div>
        <div><dt>Model</dt><dd><code>{record.model_id}</code></dd></div>
        {trip !== undefined && <div><dt>Round trip</dt><dd>{(trip / 1000).toFixed(2)} s</dd></div>}
        <div><dt>Saved as</dt><dd><code title={record.id}>{record.id.slice(0, 8)}</code></dd></div>
      </dl>
      <details className="raw">
        <summary>Raw model response</summary>
        <pre>{pretty(record.raw_response)}</pre>
      </details>

      {earlier.length > 0 && (
        <details className="earlier">
          <summary>{earlier.length} earlier {earlier.length === 1 ? 'run' : 'runs'} on this case</summary>
          <ul>
            {earlier.map((item) => (
              <li key={item.id}>
                <span>{capitalise(item.diagnosis.cause_label)}</span>
                <small>{item.diagnosis.uncertainty} uncertainty, {item.model_id}, {relativeTime(item.created_at)}</small>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="sheet-actions">
        <button className="btn btn-quiet" onClick={onDiagnose} disabled={!canDiagnose}>Diagnose again</button>
      </div>

      {repair ? <Outcome repair={repair} /> : <OutcomeForm record={record} onRecorded={onRecorded} />}
    </>
  )
}

function Outcome({ repair }: { repair: RepairRecord }) {
  return (
    <section className={`outcome outcome-${repair.matched ? 'match' : 'miss'}`} aria-label="Recorded outcome">
      <h3>{repair.matched ? 'Confirmed: the diagnosis was right' : 'Corrected: the cause was different'}</h3>
      <dl>
        <div><dt>Actual cause</dt><dd>{capitalise(repair.actual_cause)}</dd></div>
        <div><dt>Fix</dt><dd>{repair.fix_performed}</dd></div>
        <div><dt>Found</dt><dd>{repair.inspection_note}</dd></div>
        <div>
          <dt>{repair.verification_kind === 'synthetic_simulation' ? 'Simulated by' : 'Inspected by'}</dt>
          <dd>{repair.verifier}, {relativeTime(repair.timestamp)}</dd>
        </div>
      </dl>
    </section>
  )
}

export function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function pretty(raw: string): string {
  try { return JSON.stringify(JSON.parse(raw), null, 2) } catch { return raw }
}
