import { useRef, useState } from 'react'
import { Plus, Upload, X } from 'lucide-react'
import { api, type Incident } from '../api/client'

const SCENARIOS = [
  ['stalled-wheel', 'Stopped wheel', 'Zero speed with high motor current.'],
  [
    'low-voltage',
    'Low supply voltage',
    'Neither motor responds to the command.',
  ],
  [
    'encoder-mismatch',
    'Conflicting readings',
    'Wheel motion and encoder reporting disagree.',
  ],
  [
    'incomplete-evidence',
    'Missing evidence',
    'An ambiguous case that needs another measurement.',
  ],
]

export function CaseTools({
  onCreated,
}: {
  onCreated: (incident: Incident) => void
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  async function create(scenario: string) {
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.createDemo(scenario))
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return
    setError(null)
    setBusy(true)
    try {
      if (file.size > 2 * 1024 * 1024)
        throw new Error('Choose a case JSON smaller than 2 MB.')
      const result = await api.importIncident(JSON.parse(await file.text()))
      onCreated(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="case-tools">
      <div className="toolbar-actions">
        <button
          className="btn btn-quiet"
          onClick={() => input.current?.click()}
          disabled={busy}
        >
          <Upload size={16} /> Import case
        </button>
        <input
          ref={input}
          className="visually-hidden"
          type="file"
          accept="application/json,.json"
          aria-label="Import incident JSON"
          onChange={(e) => void upload(e.target.files?.[0])}
        />
        <button
          className="btn btn-primary"
          aria-expanded={open}
          aria-controls="demo-scenarios"
          onClick={() => setOpen(!open)}
          disabled={busy}
        >
          <Plus size={17} /> New demo case
        </button>
      </div>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      {open && (
        <section
          className="scenario-panel"
          id="demo-scenarios"
          aria-labelledby="scenario-heading"
        >
          <div className="section-top">
            <div>
              <p className="eyebrow">Synthetic case generator</p>
              <h2 id="scenario-heading">Choose an observation</h2>
            </div>
            <button
              className="icon-btn"
              aria-label="Close demo cases"
              onClick={() => setOpen(false)}
            >
              <X size={20} />
            </button>
          </div>
          <p>
            Create fresh readings, review the diagnosis, then record a simulated
            outcome. Creating a case makes no model call.
          </p>
          <div className="scenario-grid">
            {SCENARIOS.map(([id, name, description]) => (
              <button key={id} onClick={() => void create(id)} disabled={busy}>
                <strong>{name}</strong>
                <span>{description}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
