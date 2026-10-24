import type {
  DiagnosisRecord, EvidenceReference, Incident, Reading, RepairRecord,
} from '../api/client'

export const CAUSES = [
  'wheel obstruction',
  'motor power/driver path',
  'encoder/reporting fault',
] as const

/** Mubit trains a task's first adapter at 25 kept examples by default (docs.mubit.ai/guides/first-adapter). */
export const FIRST_ADAPTER_EXAMPLES = 25

/** Evidence fields the backend accepts, mapped to the element they point at in the incident sheet. */
export function evidenceTarget(field: string): string | null {
  const reading = /^readings\[(\d+)\]\.\w+$/.exec(field)
  if (reading) return `reading-${reading[1]}`
  const code = /^fault_codes\[(\d+)\]$/.exec(field)
  if (code) return `fault-${code[1]}`
  if (['robot_type', 'time_window', 'commanded_action', 'technician_note', 'source_type'].includes(field)) {
    return field
  }
  return null
}

export function citedTargets(evidence: EvidenceReference[] | undefined): Set<string> {
  const set = new Set<string>()
  evidence?.forEach((item) => {
    const target = evidenceTarget(item.field)
    if (target) set.add(target)
  })
  return set
}

export type Channel = {
  sensor: string
  group: string
  metric: string
  unit: string
  samples: { index: number; reading: Reading }[]
}

/** Group readings by sensor while keeping each reading's original index, which evidence refers to. */
export function channels(readings: Reading[]): Channel[] {
  const map = new Map<string, Channel>()
  readings.forEach((reading, index) => {
    const dot = reading.sensor.indexOf('.')
    const group = dot > 0 ? reading.sensor.slice(0, dot) : 'observed'
    const metric = dot > 0 ? reading.sensor.slice(dot + 1) : reading.sensor
    const channel = map.get(reading.sensor) ?? {
      sensor: reading.sensor, group, metric, unit: reading.unit, samples: [],
    }
    channel.samples.push({ index, reading })
    map.set(reading.sensor, channel)
  })
  return Array.from(map.values())
}

export function sampleTimes(readings: Reading[]): string[] {
  return Array.from(new Set(readings.map((r) => r.time))).sort()
}

/** Simulator metrics carry their unit in the name (battery_v, temp_c); the unit column already says it. */
export function metricLabel(metric: string, unit: string): string {
  const suffix = /_(v|a|c|w|pct|s)$/i.exec(metric)
  const bare = suffix && unit ? metric.slice(0, suffix.index) : metric
  return bare.replace(/_/g, ' ')
}

/** Simulator captures describe the command as "n20_fl target_rpm=150.0"; say it the way a technician would. */
export function readableAction(action: string): string {
  const match = /^(\S+) target_(rpm|deg)=([\d.-]+)$/.exec(action)
  if (!match) return action
  const [, component, unit, value] = match
  const amount = Number(value)
  const shown = Number.isFinite(amount) ? String(Math.round(amount * 10) / 10) : value
  return unit === 'rpm' ? `${component} commanded to ${shown} RPM` : `${component} commanded to ${shown}°`
}

export function formatValue(value: Reading['value']): string {
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return String(value)
    return Math.abs(value) >= 100 ? value.toFixed(1) : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return value
}

export function clockTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 1, hour12: false,
  } as Intl.DateTimeFormatOptions)
}

export function relativeTime(iso: string, now = Date.now()): string {
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000)
  if (Number.isNaN(seconds)) return iso
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return new Date(iso).toLocaleDateString()
}

export type CaseKind = 'captured' | 'development' | 'held_out' | 'other'

export function caseKind(id: string): CaseKind {
  if (id.startsWith('SIM-')) return 'captured'
  if (id.startsWith('DEV-')) return 'development'
  if (id.startsWith('HOLD-')) return 'held_out'
  return 'other'
}

export const CASE_KIND_LABEL: Record<CaseKind, string> = {
  captured: 'Captured from the simulator',
  development: 'Development cases',
  held_out: 'Held-out cases',
  other: 'Other cases',
}

/** A short human title for a case. Simulator captures name the component in commanded_action. */
export function caseTitle(incident: Incident): string {
  if (caseKind(incident.id) === 'captured') {
    const component = incident.commanded_action.split(' ')[0]
    return `${component} capture`
  }
  return incident.commanded_action
}

export type CaseStatus =
  | { kind: 'new' }
  | { kind: 'diagnosed'; record: DiagnosisRecord }
  | { kind: 'confirmed'; record: DiagnosisRecord; repair: RepairRecord }

/** Diagnoses arrive newest first from the API; the newest one per incident is the one on the bench. */
export function caseStatus(id: string, diagnoses: DiagnosisRecord[], repairs: RepairRecord[]): CaseStatus {
  const record = latestFor(id, diagnoses)
  if (!record) return { kind: 'new' }
  const repair = repairs.find((item) => item.diagnosis_id === record.id)
  return repair ? { kind: 'confirmed', record, repair } : { kind: 'diagnosed', record }
}

export function latestFor(id: string, diagnoses: DiagnosisRecord[]): DiagnosisRecord | null {
  let latest: DiagnosisRecord | null = null
  for (const record of diagnoses) {
    if (record.incident_id !== id) continue
    if (!latest || record.created_at > latest.created_at) latest = record
  }
  return latest
}

export function shortRequestId(reference: string): string {
  if (reference.startsWith('local-fixture:')) return `fixture ${reference.slice(14, 22)}`
  if (reference.startsWith('mreq_')) return `${reference.slice(0, 13)}…`
  return reference.length > 16 ? `${reference.slice(0, 16)}…` : reference
}
