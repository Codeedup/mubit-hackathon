import { useEffect, useState } from 'react'
import { api, type DiagnosisRecord, type FeedbackStatus } from '../api/client'

export function MubitFeedback({ record }: { record: DiagnosisRecord }) {
  const [state, setState] = useState<FeedbackStatus | null>(null)
  const [callId, setCallId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    setState(null)
    setCallId('')
    setError(null)
    api
      .feedbackStatus(record.id)
      .then((result) => {
        if (active) setState(result)
      })
      .catch((err: Error) => {
        if (active) setError(err.message)
      })
    return () => {
      active = false
    }
  }, [record.id])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const submission = await api.submitFeedback(record.id, callId.trim())
      setState((value) => ({
        configured: value?.configured ?? true,
        submission,
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="feedback-panel">
      <h3>Share the reviewed outcome</h3>
      {state?.submission ? (
        <p role="status">
          Feedback accepted by Mubit:{' '}
          <strong>
            {state.submission.rating === 'up' ? 'Good' : 'Needs correction'}
          </strong>
          . Reference <code>{state.submission.feedback_id}</code>. Adapter
          training and evaluation are separate steps.
        </p>
      ) : (
        <>
          <p>
            Your outcome is saved locally. You can explicitly send a rating and
            corrected label to Mubit after linking the console call.
          </p>
          {!state?.configured && (
            <p className="quiet">
              Configure a project-scoped management key and project ID in Setup
              to enable submission.
            </p>
          )}
          {state?.configured && (
            <form onSubmit={submit}>
              <label className="field-label">
                Mubit console call ID
                <input
                  className="field"
                  value={callId}
                  onChange={(e) => setCallId(e.target.value)}
                  placeholder="Copy the call ID from Mubit Requests"
                  required
                />
              </label>
              <p className="form-hint">
                The backend verifies the project, original input, and reply
                before sending. A gateway request reference may differ from the
                console call ID.
              </p>
              <button
                className="btn btn-quiet"
                disabled={busy || !callId.trim()}
              >
                {busy ? 'Submitting…' : 'Send outcome to Mubit'}
              </button>
            </form>
          )}
        </>
      )}
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
