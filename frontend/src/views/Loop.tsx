import type {
  ConfirmedEvaluationReport, DiagnosisRecord, Incident, Metrics, RepairRecord,
} from '../api/client'
import { FIRST_ADAPTER_EXAMPLES, caseKind, relativeTime, shortRequestId } from '../lib/incident'

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
  const progress = Math.min(viaMubit.length / FIRST_ADAPTER_EXAMPLES, 1)
  const ordered = [...diagnoses].sort((a, b) => b.created_at.localeCompare(a.created_at))
  const byModel = groupByModel(repairs)
  const inspected = evaluation?.groups.filter((group) => group.total > 0) ?? []

  return (
    <div className="loop">
      <header className="loop-intro">
        <h1>Learning loop</h1>
        <p>
          Each diagnosis is a Gemini call routed through Mubit. Mubit records it, groups it with every
          other diagnosis under one task, and can train a small adapter on that task. Technician outcomes
          are the ground truth used to score whichever model answered.
        </p>
      </header>

      <ol className="flow">
        <li>
          <span className="flow-count">{incidents.length}</span>
          <h2>Cases on the bench</h2>
          <p>{captured} captured live from the simulator, the rest from the synthetic case set.</p>
        </li>
        <li className="flow-mubit">
          <span className="flow-count">{viaMubit.length}</span>
          <h2>Calls through Mubit</h2>
          <p>
            {metrics?.provider_status === 'mubit'
              ? 'Each returns an mreq_ request ID, saved with the diagnosis it produced.'
              : `The backend is not on Mubit right now${viaFixture ? ` (${viaFixture} fixture runs)` : ''}. Set ROBO_MEDIC_PROVIDER=mubit.`}
          </p>
        </li>
        <li className="flow-mubit">
          <span className="flow-count">{viaMubit.length}<small>/{FIRST_ADAPTER_EXAMPLES}</small></span>
          <h2>One task, toward an adapter</h2>
          <div className="meter" role="img" aria-label={`${viaMubit.length} of ${FIRST_ADAPTER_EXAMPLES} calls`}>
            <span style={{ transform: `scaleX(${progress})` }} />
          </div>
          <p>
            Every call shares the same instructions, so Mubit files them under one task. A first adapter
            trains at {FIRST_ADAPTER_EXAMPLES} kept examples; the Mubit console shows the exact count.
          </p>
        </li>
        <li>
          <span className="flow-count">{repairs.length}</span>
          <h2>Outcomes recorded</h2>
          <p>What the technician or simulator showed the cause really was.</p>
        </li>
        <li>
          <span className="flow-count">{repairs.length ? `${Math.round((matched / repairs.length) * 100)}%` : '–'}</span>
          <h2>Diagnoses that held up</h2>
          <p>{repairs.length ? `${matched} of ${repairs.length} predictions matched the recorded cause.` : 'Record an outcome on the bench to start scoring.'}</p>
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
                  <th scope="col">Model</th>
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
                      <td><code>{record.model_id}</code></td>
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
        <h2 id="score-heading">Score by model</h2>
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
            : 'All outcomes so far are simulated. Scores from physical inspections are reported separately once there are any.'}
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

