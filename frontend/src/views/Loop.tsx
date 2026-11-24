import type {
  ConfirmedEvaluationReport,
  DiagnosisRecord,
  Incident,
  Metrics,
  RepairRecord,
} from '../api/client'
import { useState } from 'react'
import { api, type SyntheticEvaluation } from '../api/client'
import { caseKind, relativeTime, shortRequestId } from '../lib/incident'

type Props = {
  incidents: Incident[]
  diagnoses: DiagnosisRecord[]
  repairs: RepairRecord[]
  evaluation: ConfirmedEvaluationReport | null
  metrics: Metrics | null
  onOpenCase: (id: string) => void
  onOpenRecord: (id: string) => void
}

export function Loop({
  incidents,
  diagnoses,
  repairs,
  evaluation,
  metrics,
  onOpenCase,
  onOpenRecord,
}: Props) {
  const [split, setSplit] = useState('held_out')
  const [provider, setProvider] = useState('local_fixture')
  const [score, setScore] = useState<SyntheticEvaluation | null>(null)
  const [scoring, setScoring] = useState(false)
  const [scoreError, setScoreError] = useState<string | null>(null)
  async function scorePredictions() {
    setScoring(true)
    setScoreError(null)
    try {
      setScore(await api.syntheticEvaluation(split, provider))
    } catch (err) {
      setScoreError(err instanceof Error ? err.message : String(err))
    } finally {
      setScoring(false)
    }
  }
  const viaMubit = diagnoses.filter((item) => item.provider_kind === 'mubit')
  const viaFixture = diagnoses.filter(
    (item) => item.provider_kind === 'local_fixture',
  ).length
  const viaOpenRouter = diagnoses.filter(
    (item) => item.provider_kind === 'openrouter',
  ).length
  const captured = incidents.filter(
    (item) => caseKind(item.id) === 'captured',
  ).length
  const matched = repairs.filter((item) => item.matched).length
  const ordered = [...diagnoses].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )
  const byModel = groupByModel(repairs)
  const inspected = evaluation?.groups.filter((group) => group.total > 0) ?? []

  return (
    <div className="loop">
      <header className="loop-intro">
        <p className="eyebrow">A traceable record</p>
        <h1>History & evaluation</h1>
        <p>
          This ledger separates saved Mubit inference results from offline
          fixture runs and local technician outcomes. Review what happened,
          compare predictions with outcomes, and keep model results separate
          from the offline demo.
        </p>
      </header>

      <ol className="flow">
        <li>
          <span className="flow-count">{incidents.length}</span>
          <h2>Cases on the bench</h2>
          <p>
            {captured} captured from the simulator.{' '}
            {
              incidents.filter((item) => item.source_type === 'synthetic')
                .length
            }{' '}
            synthetic cases;{' '}
            {
              incidents.filter((item) => item.source_type !== 'synthetic')
                .length
            }{' '}
            measured or operator-observed.
          </p>
        </li>
        <li className="flow-mubit">
          <span className="flow-count">{viaMubit.length}</span>
          <h2>Saved diagnoses through Mubit</h2>
          <p>
            {metrics?.provider_status === 'mubit'
              ? 'Mubit is configured, but this is not a live health check. A saved request ID confirms a routed inference response, not console review.'
              : `Mubit is not configured for new diagnoses here. ${viaFixture} offline runs and ${viaOpenRouter} direct OpenRouter runs are separate.`}
          </p>
        </li>
        <li className="flow-mubit">
          <span className="flow-count flow-count-word">Check live</span>
          <h2>Adapter status</h2>
          <p>
            Open Setup to check the configured task and its adapter versions.
            Adapter gains require a separate comparison on held-out cases.
          </p>
        </li>
        <li>
          <span className="flow-count">{repairs.length}</span>
          <h2>Local outcomes recorded</h2>
          <p>
            Recorded technician or simulator results. Sending an outcome to
            Mubit is an explicit action on its diagnosis.
          </p>
        </li>
        <li>
          <span className="flow-count flow-count-word">Reviewed</span>
          <h2>Feedback before learning</h2>
          <p>
            Only link a console call after recording an outcome. Its project,
            input, and reply are checked before a rating and corrected label are
            submitted.
          </p>
        </li>
        <li>
          <span className="flow-count">
            {repairs.length ? `${matched}/${repairs.length}` : '–'}
          </span>
          <h2>Local outcome agreement</h2>
          <p>
            {repairs.length
              ? `${matched} of ${repairs.length} saved predictions matched recorded outcomes. This is not adapter improvement.`
              : 'Record an outcome on the bench to start scoring.'}
          </p>
        </li>
      </ol>

      <section className="sheet ledger-sheet" aria-labelledby="ledger-heading">
        <h2 id="ledger-heading">Request ledger</h2>
        {ordered.length === 0 ? (
          <p className="quiet">
            No diagnoses yet. Run one from the bench and it appears here with
            its request ID.
          </p>
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
                  const repair = repairs.find(
                    (item) => item.diagnosis_id === record.id,
                  )
                  return (
                    <tr key={record.id}>
                      <td>{relativeTime(record.created_at)}</td>
                      <td>
                        <button
                          className="link-btn"
                          onClick={() => onOpenRecord(record.id)}
                        >
                          {record.incident_id}
                        </button>
                      </td>
                      <td>
                        <code title={record.request_reference}>
                          {shortRequestId(record.request_reference)}
                        </code>
                      </td>
                      <td>
                        <code>
                          {record.provider_kind === 'mubit'
                            ? 'Mubit'
                            : record.provider_kind === 'openrouter'
                              ? 'OpenRouter'
                              : 'Fixture'}{' '}
                          · {record.model_id}
                        </code>
                      </td>
                      <td>
                        {record.diagnosis.cause_label}
                        <small>, {record.diagnosis.uncertainty}</small>
                      </td>
                      <td>
                        {!repair && <span className="quiet">Open</span>}
                        {repair && (
                          <span
                            className={
                              repair.matched ? 'tag-match' : 'tag-miss'
                            }
                          >
                            {repair.matched
                              ? 'Matched'
                              : `Was ${repair.actual_cause}`}
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

      <section
        className="sheet score-sheet"
        aria-labelledby="synthetic-score-heading"
      >
        <div className="section-top">
          <div>
            <p className="eyebrow">Separate answer keys</p>
            <h2 id="synthetic-score-heading">Synthetic case evaluation</h2>
          </div>
        </div>
        <p>
          Score stored first predictions against the bundled answer keys.
          Missing cases stay visible. This check makes no new inference calls.
        </p>
        <div className="evaluation-controls">
          <label className="field-label">
            Case set
            <select
              className="field"
              value={split}
              onChange={(e) => {
                setSplit(e.target.value)
                setScore(null)
              }}
            >
              <option value="held_out">Held-out cases</option>
              <option value="development">Development cases</option>
            </select>
          </label>
          <label className="field-label">
            Provider
            <select
              className="field"
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value)
                setScore(null)
              }}
            >
              <option value="local_fixture">Offline rules</option>
              <option value="mubit">Mubit</option>
              <option value="openrouter">OpenRouter directly</option>
            </select>
          </label>
          <button
            className="btn btn-primary"
            onClick={() => void scorePredictions()}
            disabled={scoring}
          >
            {scoring ? 'Scoring…' : 'Score saved predictions'}
          </button>
        </div>
        {scoreError && (
          <p className="notice notice-error" role="alert">
            {scoreError}
          </p>
        )}
        {score && (
          <div className="integration-result" role="status">
            <h3>
              {score.evaluated
                ? `${score.matched} of ${score.evaluated} matched`
                : 'No eligible predictions yet'}
            </h3>
            <p>
              {score.evaluated} of {score.key_count} cases evaluated.{' '}
              {score.missing_incident_ids.length} missing.{' '}
              {score.excluded_leaky_incident_ids.length} excluded for source or
              label leakage.
            </p>
            {score.cases.map((item) => (
              <p key={item.incident_id}>
                <button
                  className="link-btn"
                  onClick={() => onOpenCase(item.incident_id)}
                >
                  {item.incident_id}
                </button>{' '}
                · {item.predicted_cause} ·{' '}
                {item.matched ? 'Matched' : `Expected ${item.actual_cause}`}
              </p>
            ))}
            {score.missing_incident_ids.length > 0 && (
              <details>
                <summary>Cases needing a first diagnosis</summary>
                <p>{score.missing_incident_ids.join(', ')}</p>
              </details>
            )}
            <p className="footnote">
              Offline scores check the workflow. They do not measure AI quality
              or adapter improvement. Each case uses its first prediction across
              providers, before corrections.
            </p>
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
                  <small>
                    {group.provider === 'mubit'
                      ? 'through Mubit'
                      : group.provider === 'openrouter'
                        ? 'OpenRouter directly'
                        : 'offline fixture'}
                  </small>
                </div>
                <div className="score-bar" aria-hidden="true">
                  <span
                    style={{
                      transform: `scaleX(${group.matched / group.total})`,
                    }}
                  />
                </div>
                <div className="score-figure">
                  {Math.round((group.matched / group.total) * 100)}%
                  <small>
                    {group.matched} of {group.total}
                  </small>
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
  const map = new Map<
    string,
    {
      key: string
      model: string
      provider: string
      total: number
      matched: number
    }
  >()
  repairs.forEach((repair) => {
    const key = `${repair.provider_kind}:${repair.model_id}`
    const group = map.get(key) ?? {
      key,
      model: repair.model_id,
      provider: repair.provider_kind,
      total: 0,
      matched: 0,
    }
    group.total += 1
    if (repair.matched) group.matched += 1
    map.set(key, group)
  })
  return Array.from(map.values()).sort((a, b) => b.total - a.total)
}
