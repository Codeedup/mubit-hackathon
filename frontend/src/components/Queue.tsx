import type { DiagnosisRecord, Incident, RepairRecord } from '../api/client'
import { useState } from 'react'
import { Search } from 'lucide-react'
import {
  CASE_KIND_LABEL,
  caseKind,
  caseStatus,
  caseTitle,
  type CaseKind,
} from '../lib/incident'

type Props = {
  incidents: Incident[]
  diagnoses: DiagnosisRecord[]
  repairs: RepairRecord[]
  selectedId: string | null
  fresh: Set<string>
  onSelect: (id: string) => void
}

const ORDER: CaseKind[] = [
  'demo',
  'captured',
  'development',
  'held_out',
  'other',
]

export function Queue({
  incidents,
  diagnoses,
  repairs,
  selectedId,
  fresh,
  onSelect,
}: Props) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const filtered = incidents.filter((item) => {
    const status = caseStatus(item.id, diagnoses, repairs).kind
    return (
      `${item.id} ${caseTitle(item)} ${item.technician_note}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (filter === 'all' || status === filter)
    )
  })
  const groups = ORDER.map((kind) => ({
    kind,
    items: filtered
      .filter((item) => caseKind(item.id) === kind)
      .sort((a, b) =>
        kind === 'captured' || kind === 'demo'
          ? b.id.localeCompare(a.id)
          : a.id.localeCompare(b.id),
      ),
  })).filter((group) => group.items.length > 0)

  return (
    <nav className="queue" aria-label="Cases">
      <div className="queue-controls">
        <h2>
          Case queue <span>{filtered.length}</span>
        </h2>
        <label className="queue-search">
          <Search size={15} />
          <input
            aria-label="Search cases"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search cases…"
          />
        </label>
        <select
          className="field"
          aria-label="Filter cases by status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All cases</option>
          <option value="new">Needs diagnosis</option>
          <option value="diagnosed">Awaiting outcome</option>
          <option value="confirmed">Outcome recorded</option>
        </select>
      </div>
      <div className="queue-list">
        {groups.length === 0 && <p className="quiet">No matching cases.</p>}
        {groups.map((group) => (
          <div className="queue-group" key={group.kind}>
            <h2>
              {CASE_KIND_LABEL[group.kind]}
              <span>{group.items.length}</span>
            </h2>
            <ul>
              {group.items.map((incident) => {
                const status = caseStatus(incident.id, diagnoses, repairs)
                return (
                  <li key={incident.id}>
                    <button
                      className={`queue-item ${selectedId === incident.id ? 'selected' : ''} ${fresh.has(incident.id) ? 'fresh' : ''}`}
                      aria-current={
                        selectedId === incident.id ? 'true' : undefined
                      }
                      onClick={() => onSelect(incident.id)}
                    >
                      <span className="queue-title">{caseTitle(incident)}</span>
                      <span className="queue-id">{incident.id}</span>
                      <span
                        className={`queue-status status-${status.kind}${status.kind === 'confirmed' ? (status.repair.matched ? '-match' : '-miss') : ''}`}
                      >
                        {status.kind === 'new' &&
                          (fresh.has(incident.id)
                            ? 'New capture'
                            : 'Not diagnosed')}
                        {status.kind === 'diagnosed' &&
                          (status.record.diagnosis.cause_label === 'unknown'
                            ? 'Cause unknown'
                            : status.record.diagnosis.cause_label)}
                        {status.kind === 'confirmed' &&
                          (status.repair.matched ? 'Confirmed' : 'Corrected')}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  )
}
