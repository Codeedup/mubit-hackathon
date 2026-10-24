export type Reading = {
  sensor: string
  value: number | string | boolean
  unit: string
  origin: 'synthetic' | 'measured' | 'operator-observed'
  time: string
}
export type Incident = {
  schema_version: '1.0'
  id: string
  robot_type: string
  time_window: string
  commanded_action: string
  readings: Reading[]
  fault_codes: string[]
  technician_note: string
  source_type: Reading['origin']
}
export type EvidenceReference = { field: string; explanation: string }
export type Diagnosis = {
  cause_label: 'wheel obstruction' | 'motor power/driver path' | 'encoder/reporting fault' | 'unknown'
  supporting_evidence: EvidenceReference[]
  alternative: string
  next_check: string
  uncertainty: 'low' | 'medium' | 'high'
}
export type DiagnosisRecord = {
  id: string
  incident_id: string
  incident: Incident
  diagnosis: Diagnosis
  created_at: string
  request_reference: string
  model_id: string
  provider_kind: 'local_fixture' | 'mubit'
  raw_response: string
}
export type ConfirmRequest = {
  diagnosis_id: string
  incident_id: string
  actual_cause: string
  fix_performed: string
  inspection_note: string
  verifier: string
  timestamp: string
}
export type ConfirmationRecord = ConfirmRequest & {
  id: string
  verification_kind: 'inspection' | 'synthetic_simulation'
}
export type RepairRecord = ConfirmationRecord & {
  predicted_cause: Diagnosis['cause_label']
  diagnosis_created_at: string
  provider_kind: DiagnosisRecord['provider_kind']
  model_id: string
  matched: boolean
}
export type ConfirmedEvaluationReport = {
  source: 'technician_confirmed'
  groups: {
    provider_kind: DiagnosisRecord['provider_kind']
    model_id: string
    total: number
    confirmed_diagnosis_count: number
    matched: number
    accuracy: number | null
    cases: {
      diagnosis_id: string
      incident_id: string
      predicted_cause: Diagnosis['cause_label']
      actual_cause: string
      matched: boolean
    }[]
  }[]
}
export type Metrics = {
  incident_count: number
  diagnosis_count: number
  confirmation_count: number
  provider_status: 'not_configured' | 'missing_credentials' | 'local_fixture' | 'mubit'
  simulator_online: boolean
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let detail = `API returned ${response.status} for ${path}`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* Keep the HTTP status when no JSON body is returned. */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  incidents: () => requestJson<Incident[]>('/api/incidents'),
  diagnoses: () => requestJson<DiagnosisRecord[]>('/api/diagnoses'),
  repairs: () => requestJson<RepairRecord[]>('/api/repairs'),
  confirmedEvaluation: () => requestJson<ConfirmedEvaluationReport>('/api/evaluation/confirmed'),
  metrics: () => requestJson<Metrics>('/api/metrics'),
  diagnose: (incident_id: string) => requestJson<DiagnosisRecord>('/api/diagnose', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ incident_id }),
  }),
  confirm: (payload: ConfirmRequest) => requestJson<ConfirmationRecord>('/api/confirm', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
}
