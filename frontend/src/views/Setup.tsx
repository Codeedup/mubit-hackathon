import { useEffect, useState } from 'react'
import { CheckCircle2, Cable, FlaskConical, RefreshCw } from 'lucide-react'
import { api, type MubitStatus, type SetupInfo } from '../api/client'

export function Setup() {
  const [info, setInfo] = useState<SetupInfo | null>(null)
  const [status, setStatus] = useState<MubitStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api
      .setup()
      .then(setInfo)
      .catch((err: Error) => setError(err.message))
  }, [])
  async function refresh() {
    setBusy(true)
    setError(null)
    try {
      setStatus(await api.mubitStatus())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="setup-grid">
      <header className="loop-intro">
        <p className="eyebrow">Your workspace</p>
        <h1>Ready for the next fault.</h1>
        <p>
          Run the complete demo locally. Connect Mubit when you’re ready to use
          live classification and reviewed feedback.
        </p>
      </header>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      <section className="sheet setup-card">
        <FlaskConical className="card-icon" />
        <h2>Offline demo</h2>
        <p>
          Deterministic rules exercise the complete diagnosis and outcome
          workflow. No credentials or network are needed after installation.
        </p>
        <p className="setup-state">
          <CheckCircle2 size={18} />{' '}
          {info?.provider === 'local_fixture'
            ? 'Active in this workspace'
            : 'Available with the local_fixture provider'}
        </p>
        <code className="code-block">
          python run.py --provider local_fixture --open
        </code>
        <p>
          Use <strong>New demo case</strong> on the bench, or explore the
          bundled development and held-out cases.
        </p>
      </section>
      <section className="sheet setup-card">
        <Cable className="card-icon" />
        <h2>Connect Mubit</h2>
        <p>
          In your Mubit project, add a Gemini provider key, then create an
          inference key. Keep both keys out of browser code.
        </p>
        <p>
          <a
            href="https://app.mubit.ai/console/"
            target="_blank"
            rel="noreferrer"
          >
            Open Mubit console
          </a>{' '}
          ·{' '}
          <a
            href="https://docs.mubit.ai/guides/connect-gemini"
            target="_blank"
            rel="noreferrer"
          >
            Connection guide
          </a>
        </p>
        <p>
          Copy <code>.env.example</code> to <code>.env</code>, set these values,
          then restart the app:
        </p>
        <pre className="code-block">
          {
            'ROBO_MEDIC_PROVIDER=mubit\nMUBIT_API_KEY=<your inference key>\nMUBIT_MODEL=gemini-3.8-flash'
          }
        </pre>
        <p className="setup-state">
          Inference key:{' '}
          {info?.inference_key_configured ? 'configured' : 'not configured'} ·
          Model: {info?.model ?? 'checking…'}
        </p>
      </section>
      <section className="sheet setup-card wide">
        <div className="section-top">
          <div>
            <p className="eyebrow">Optional integration</p>
            <h2>Task status & reviewed feedback</h2>
          </div>
          <button
            className="btn btn-quiet"
            onClick={() => void refresh()}
            disabled={busy}
          >
            <RefreshCw size={16} />
            {busy ? 'Checking…' : 'Check Mubit status'}
          </button>
        </div>
        <p>
          A project-scoped management key enables task status. A{' '}
          <strong>member</strong> key also enables explicit ratings and
          corrections after you record an outcome. This does not automatically
          train or promote an adapter.
        </p>
        <pre className="code-block">
          {
            'MUBIT_MANAGEMENT_KEY=<project-scoped key>\nMUBIT_PROJECT_ID=<management API project ID>\nMUBIT_TASK_ID=<classification task ID>'
          }
        </pre>
        <p>
          Management key:{' '}
          {info?.management_key_configured ? 'configured' : 'not configured'}.
          Project and task:{' '}
          {info?.project_id && info?.task_id ? 'configured' : 'not configured'}.
        </p>
        {status && (
          <div className="integration-result" role="status">
            {status.task ? (
              <>
                <h3>{status.task.name}</h3>
                <p>
                  Stage: <strong>{status.task.stage}</strong> ·{' '}
                  {status.task.rows_count} dataset rows · Active version:{' '}
                  <strong>{status.task.active_version ?? 'none'}</strong>
                </p>
                <p>
                  {status.versions?.length
                    ? status.versions
                        .map((v) => `Version ${v.version_number}: ${v.status}`)
                        .join(' · ')
                    : 'No adapter versions returned.'}
                </p>
              </>
            ) : (
              <p>{status.message}</p>
            )}
            <small>
              Checked {new Date(status.checked_at).toLocaleString()}. Refresh to
              check again.
            </small>
          </div>
        )}
      </section>
      <section className="sheet setup-card wide">
        <h2>Local data, clear provenance</h2>
        <p>
          Cases are saved as versioned JSON and diagnoses and outcomes in
          SQLite. Predictions remain unchanged when an outcome is recorded.
          Export your workspace from the header to keep a portable evidence
          record.
        </p>
        <p>
          Imported incidents must follow the version 1.0 schema.{' '}
          <a href="/docs" target="_blank" rel="noreferrer">
            Open the API reference
          </a>{' '}
          for the contract. This app is designed for one local operator.
        </p>
        <p className="footnote">
          Robo Medic {info?.version ?? '1.0.0'} · The assistant recommends
          checks; a technician performs them.
        </p>
      </section>
    </div>
  )
}
