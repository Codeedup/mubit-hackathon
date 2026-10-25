import type { DiagnosisRecord, Incident, RepairRecord } from '../api/client'
import {
  CASE_KIND_LABEL, caseKind, caseStatus, caseTitle, type CaseKind,
} from '../lib/incident'

type Props = {
  incidents: Incident[]
  diagnoses: DiagnosisRecord[]
  repairs: RepairRecord[]
  selectedId: string | null
  fresh: Set<string>
  onSelect: (id: string) => void
}

const ORDER: CaseKind[] = ['captured', 'development', 'held_out', 'other']

export function Queue({ incidents, diagnoses, repairs, selectedId, fresh, onSelect }: Props) {
  const groups = ORDER
    .map((kind) => ({
      kind,
      items: incidents
        .filter((item) => caseKind(item.id) === kind)
        .sort((a, b) => (kind === 'captured' ? b.id.localeCompare(a.id) : a.id.localeCompare(b.id))),
    }))
    .filter((group) => group.items.length > 0)

  return (
    <nav className="queue" aria-label="Cases">
      {groups.map((group) => (
        <div className="queue-group" key={group.kind}>
          <h2>{CASE_KIND_LABEL[group.kind]}<span>{group.items.length}</span></h2>
          <ul>
            {group.items.map((incident) => {
              const status = caseStatus(incident.id, diagnoses, repairs)
              return (
                <li key={incident.id}>
                  <button
                    className={`queue-item ${selectedId === incident.id ? 'selected' : ''} ${fresh.has(incident.id) ? 'fresh' : ''}`}
                    aria-current={selectedId === incident.id ? 'true' : undefined}
                    onClick={() => onSelect(incident.id)}
                  >
                    <span className="queue-title">{caseTitle(incident)}</span>
                    <span className="queue-id">{incident.id}</span>
                    <span className={`queue-status status-${status.kind}${status.kind === 'confirmed' ? (status.repair.matched ? '-match' : '-miss') : ''}`}>
                      {status.kind === 'new' && (fresh.has(incident.id) ? 'New capture' : 'Not diagnosed')}
                      {status.kind === 'diagnosed' && (status.record.diagnosis.cause_label === 'unknown' ? 'Cause unknown' : status.record.diagnosis.cause_label)}
                      {status.kind === 'confirmed' && (status.repair.matched ? 'Confirmed' : 'Corrected')}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}
