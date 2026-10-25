import type {
  ConfirmedEvaluationReport, DiagnosisRecord, Incident, Metrics, RepairRecord,
} from '../api/client'
import { caseKind, relativeTime, shortRequestId } from '../lib/incident'

type Props = {
  incidents: Incident[]
  diagnoses: DiagnosisRecord[]
  repairs: RepairRecord[]
  evaluation: ConfirmedEvaluationReport | null
  metrics: Metrics | null
  onOpenCase: (id: string) => void
}

export function Loop({ incidents, diagnoses, repairs, evaluation, metrics, onOpenCase }: Props) {
  const viaMubit = diagnoses.filter((item) => item.provider_kind === 'mubit')
  const viaFixture = diagnoses.length - viaMubit.length
  const captured = incidents.filter((item) => caseKind(item.id) === 'captured').length
  const matched = repairs.filter((item) => item.matched).length
  const ordered = [...diagnoses].sort((a, b) => b.created_at.localeCompare(a.created_at))
  const byModel = groupByModel(repairs)
  const inspected = evaluation?.groups.filter((group) => group.total > 0) ?? []

  return (
    <div className="loop">
      <header className="loop-intro">
        <h1>Learning loop</h1>
        <p>
          This ledger separates saved Mubit inference results from offline fixture runs and local
          technician outcomes. Outcomes score saved diagnoses locally; they are not sent as adapter training feedback.
        </p>
      </header>

      <ol className="flow">
        <li>
          <span className="flow-count">{incidents.length}</span>
          <h2>Cases on the bench</h2>
          <p>{captured} captured from the simulator; the rest are bundled synthetic cases.</p>
        </li>
        <li className="flow-mubit">
          <span className="flow-count">{viaMubit.length}</span>
          <h2>Saved diagnoses through Mubit</h2>
          <p>
            {metrics?.provider_status === 'mubit'
              ? 'Mubit is configured, but this is not a live health check. A saved request ID confirms a routed inference response, not console review.'
              : `Mubit is not configured for new diagnoses here${viaFixture ? `; ${viaFixture} saved fixture runs are separate` : ''}.`}
          </p>
        </li>
        <li className="flow-mubit">
          <span className="flow-count flow-count-word">Not yet</span>
          <h2>Adapter status</h2>
          <p>
            No adapter was ready for this event. If training completes, we hope to test whether an adapter
            makes future triage more useful. No benefit has been measured yet.
          </p>
        </li>
        <li>
          <span className="flow-count">{repairs.length}</span>
          <h2>Local outcomes recorded</h2>
          <p>Recorded technician or simulator results; these have not been sent to Mubit as corrections.</p>
        </li>
        <li>
          <span className="flow-count flow-count-word">24 Oct</span>
          <h2>Documented Mubit task view</h2>
          <p>The 24 October console capture shows the intended task reviewing examples at 12 of 25 toward first training, with no adapter shown. This app does not read live console state.</p>
        </li>
        <li>
          <span className="flow-count">{repairs.length ? `${matched}/${repairs.length}` : '–'}</span>
          <h2>Local outcome agreement</h2>
          <p>{repairs.length ? `${matched} of ${repairs.length} saved predictions matched recorded outcomes. This is not adapter improvement.` : 'Record an outcome on the bench to start scoring.'}</p>
        </li>
      </ol>

      <section className="sheet ledger-sheet" aria-labelledby="ledger-heading">
        <h2 id="ledger-heading">Request ledger</h2>
        {ordered.length === 0 ? (
          <p className="quiet">No diagnoses yet. Run one from the bench and it appears here with its request ID.</p>
        ) : (
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Case</th>
                  <th scope="col">Request</th>
                  <th scope="col">Provider / ID</th>
                  <th scope="col">Predicted</th>
                  <th scope="col">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((record) => {
                  const repair = repairs.find((item) => item.diagnosis_id === record.id)
                  return (
                    <tr key={record.id}>
                      <td>{relativeTime(record.created_at)}</td>
                      <td><button className="link-btn" onClick={() => onOpenCase(record.incident_id)}>{record.incident_id}</button></td>
                      <td><code title={record.request_reference}>{shortRequestId(record.request_reference)}</code></td>
                      <td><code>{record.provider_kind === 'mubit' ? 'Mubit' : 'Fixture'} · {record.model_id}</code></td>
                      <td>{record.diagnosis.cause_label}<small>, {record.diagnosis.uncertainty}</small></td>
                      <td>
                        {!repair && <span className="quiet">Open</span>}
                        {repair && (
                          <span className={repair.matched ? 'tag-match' : 'tag-miss'}>
                            {repair.matched ? 'Matched' : `Was ${repair.actual_cause}`}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="sheet score-sheet" aria-labelledby="score-heading">
        <h2 id="score-heading">Score by provider and model</h2>
        {byModel.length === 0 ? (
          <p className="quiet">Scores appear once outcomes are recorded.</p>
        ) : (
          <ul className="scores">
            {byModel.map((group) => (
              <li key={group.key}>
                <div className="score-name">
                  <code>{group.model}</code>
                  <small>{group.provider === 'mubit' ? 'through Mubit' : 'offline fixture'}</small>
                </div>
                <div className="score-bar" aria-hidden="true">
                  <span style={{ transform: `scaleX(${group.matched / group.total})` }} />
                </div>
                <div className="score-figure">
                  {Math.round((group.matched / group.total) * 100)}%
                  <small>{group.matched} of {group.total}</small>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="footnote">
          {inspected.length
            ? `Physical inspections: ${inspected.map((g) => `${g.model_id} ${g.accuracy === null ? '–' : `${Math.round(g.accuracy * 100)}%`} on ${g.total}`).join('; ')}.`
            : 'All outcomes so far are simulated. This local sample is not an adapter or model performance estimate.'}
        </p>
      </section>
    </div>
  )
}

function groupByModel(repairs: RepairRecord[]) {
  const map = new Map<string, { key: string; model: string; provider: string; total: number; matched: number }>()
  repairs.forEach((repair) => {
    const key = `${repair.provider_kind}:${repair.model_id}`
    const group = map.get(key) ?? { key, model: repair.model_id, provider: repair.provider_kind, total: 0, matched: 0 }
    group.total += 1
    if (repair.matched) group.matched += 1
    map.set(key, group)
  })
  return Array.from(map.values()).sort((a, b) => b.total - a.total)
}
