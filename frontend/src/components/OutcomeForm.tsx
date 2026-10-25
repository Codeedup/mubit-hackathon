import { useEffect, useState } from 'react'
import { api, type DiagnosisRecord } from '../api/client'
import { CAUSES } from '../lib/incident'

const VERIFIER_KEY = 'robo-medic.verifier'

function storedVerifier(): string {
  try { return window.localStorage.getItem(VERIFIER_KEY) ?? '' } catch { return '' }
}

export function OutcomeForm({ record, onRecorded }: { record: DiagnosisRecord; onRecorded: () => void }) {
  const predicted = record.diagnosis.cause_label
  const synthetic = record.incident.source_type === 'synthetic'
  const [cause, setCause] = useState<string>(predicted === 'unknown' ? '' : predicted)
  const [other, setOther] = useState('')
  const [fix, setFix] = useState('')
  const [note, setNote] = useState('')
  const [verifier, setVerifier] = useState(storedVerifier)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setCause(predicted === 'unknown' ? '' : predicted)
    setOther(''); setFix(''); setNote(''); setError(null)
  }, [record.id, predicted])

  const actual = cause === 'other' ? other.trim() : cause
  const ready = actual && fix.trim() && note.trim() && verifier.trim()

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!ready) return
    setSaving(true)
    setError(null)
    try {
      await api.confirm({
        diagnosis_id: record.id,
        incident_id: record.incident_id,
        actual_cause: actual,
        fix_performed: fix.trim(),
        inspection_note: note.trim(),
        verifier: verifier.trim(),
        timestamp: new Date().toISOString(),
      })
      try { window.localStorage.setItem(VERIFIER_KEY, verifier.trim()) } catch { /* Optional convenience. */ }
      onRecorded()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="outcome-form" onSubmit={submit}>
      <h3>{synthetic ? 'Record the simulated outcome' : 'Record what the inspection found'}</h3>
      <p className="form-hint">
        This becomes local ground truth for scoring the saved diagnosis. The prediction above is never changed or sent as training feedback.
      </p>

      <fieldset>
        <legend>Actual cause</legend>
        <div className="cause-choices">
          {[...CAUSES, 'other'].map((option) => (
            <label key={option} className={cause === option ? 'chosen' : undefined}>
              <input type="radio" name="actual-cause" value={option} checked={cause === option}
                onChange={() => setCause(option)} />
              {option === 'other' ? 'Something else' : option}
              {option === predicted && <small>predicted</small>}
            </label>
          ))}
        </div>
        {cause === 'other' && (
          <input className="field" aria-label="Describe the actual cause" placeholder="For example: loose connector on the encoder harness"
            value={other} onChange={(e) => setOther(e.target.value)} />
        )}
      </fieldset>

      <label className="field-label">
        Fix performed
        <input className="field" value={fix} onChange={(e) => setFix(e.target.value)}
          placeholder={synthetic ? 'Cleared the injected fault in the simulator' : 'Removed debris from the left gearbox'} />
      </label>
      <label className="field-label">
        What you found
        <textarea className="field" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder={synthetic ? 'Simulator state showed the wheel jammed, then turned freely once cleared' : 'Wheel turned freely by hand after cleaning'} />
      </label>
      <label className="field-label">
        Your name
        <input className="field" value={verifier} onChange={(e) => setVerifier(e.target.value)} autoComplete="name" />
      </label>

      {error && <div className="notice notice-error" role="alert"><p>{error}</p></div>}
      <button className="btn btn-primary" type="submit" disabled={!ready || saving}>
        {saving ? 'Recording…' : 'Record outcome'}
      </button>
    </form>
  )
}
