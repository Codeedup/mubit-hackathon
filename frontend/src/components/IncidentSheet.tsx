import { useMemo } from 'react'
import type { Incident } from '../api/client'
import { channels, clockTime, formatValue, metricLabel, readableAction, sampleTimes } from '../lib/incident'
import { Trace } from './Trace'

type Props = {
  incident: Incident
  /** Element targets the current diagnosis cites (see evidenceTarget). */
  cited: Set<string>
  /** Target of the evidence item the technician is pointing at. */
  focused: string | null
  /** Changes when a new diagnosis lands, so the highlight sweep replays once. */
  markKey: string
}

export function IncidentSheet({ incident, cited, focused, markKey }: Props) {
  const rows = useMemo(() => channels(incident.readings), [incident.readings])
  const times = useMemo(() => sampleTimes(incident.readings), [incident.readings])
  const groups = useMemo(() => Array.from(new Set(rows.map((row) => row.group))), [rows])
  const showTrace = times.length > 1

  const mark = (target: string) =>
    `${cited.has(target) ? 'cited' : ''} ${focused === target ? 'focused' : ''}`.trim() || undefined

  return (
    <section className="sheet incident-sheet" aria-labelledby="incident-heading" key={markKey}>
      <div className="sheet-meta">
        <span className="case-id">{incident.id}</span>
        <span className={`source source-${incident.source_type}`}>{incident.source_type}</span>
        <span data-target="robot_type" className={mark('robot_type')}>{incident.robot_type}</span>
      </div>

      <h1 id="incident-heading" className="incident-action">
        <span data-target="commanded_action" className={mark('commanded_action')} title={incident.commanded_action}>
          {readableAction(incident.commanded_action)}
        </span>
      </h1>
      <p className="time-window">
        <span data-target="time_window" className={mark('time_window')}>{incident.time_window}</span>
      </p>

      {incident.technician_note && (
        <blockquote className="symptom">
          <span data-target="technician_note" className={mark('technician_note')}>{incident.technician_note}</span>
        </blockquote>
      )}

      {incident.fault_codes.length > 0 && (
        <div className="fault-codes" aria-label="Fault codes">
          {incident.fault_codes.map((code, index) => (
            <span key={index} data-target={`fault-${index}`} className={`fault-code ${mark(`fault-${index}`) ?? ''}`}>
              {code}<small>fault_codes[{index}]</small>
            </span>
          ))}
        </div>
      )}

      <div className="channel-wrap">
        <table className="channels">
          <caption>
            {incident.readings.length} readings from {rows.length} {rows.length === 1 ? 'channel' : 'channels'}
            {times.length > 1 ? `, ${times.length} samples` : ''}
          </caption>
          <thead>
            <tr>
              <th scope="col">Channel</th>
              {times.map((time) => <th scope="col" key={time} className="num">{clockTime(time)}</th>)}
              {showTrace && <th scope="col" className="trace-col"><span className="visually-hidden">Trend</span></th>}
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group}>
              {groups.length > 1 && (
                <tr className="group-row"><th colSpan={times.length + (showTrace ? 2 : 1)} scope="rowgroup">{group}</th></tr>
              )}
              {rows.filter((row) => row.group === group).map((row) => (
                <tr key={row.sensor}>
                  <th scope="row">
                    {metricLabel(row.metric, row.unit)}
                    <small>{row.unit}</small>
                  </th>
                  {times.map((time) => {
                    const sample = row.samples.find((item) => item.reading.time === time)
                    if (!sample) return <td key={time} className="num empty">–</td>
                    const target = `reading-${sample.index}`
                    return (
                      <td key={time} className="num">
                        <span data-target={target} className={`reading ${mark(target) ?? ''}`}>
                          {formatValue(sample.reading.value)}
                          <small className="ref">[{sample.index}]</small>
                        </span>
                      </td>
                    )
                  })}
                  {showTrace && (
                    <td className="trace-col">
                      <Trace values={row.samples.map((item) => item.reading.value)} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </section>
  )
}
