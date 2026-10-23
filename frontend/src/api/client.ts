export type Reading = {
  ts: string
  sensor: string
  metric: string
  value: number
  unit: string
  origin: string
}

export type Incident = {
  id: string
  robot_type: string
  time_window: string
  commanded_action: string
  readings: Reading[]
  fault_codes: string[]
  technician_note: string
  source_type: 'synthetic' | 'measured' | 'operator-observed'
}

export type RecommendedCommand = {
  target: string
  action: string
  value: number | string | null
  reason?: string
}

export type Diagnosis = {
  cause_label: string
  supporting_evidence: string[]
  alternative: string
  next_check: string
  uncertainty: 'low' | 'medium' | 'high'
  recommended_command?: RecommendedCommand | null
}

export type DiagnosisRecord = {
  id: string
  incident_id: string
  diagnosis: Diagnosis
  created_at: string
  request_reference: string | null
  model_id: string | null
}

export type ConfirmRequest = {
  diagnosis_id: string
  incident_id: string
  actual_cause: string
  fix_performed: string
  verifier: string
  timestamp: string
}

export type ConfirmationRecord = ConfirmRequest & {
  id: string
}

export type EvaluationCaseResult = {
  incident_id: string
  expected_cause_label: string
  predicted_cause_label: string
  matched: boolean
  uncertainty: 'low' | 'medium' | 'high'
}

export type EvaluationSummary = {
  id: string
  total_cases: number
  matched_cases: number
  accuracy_pct: number
  results: EvaluationCaseResult[]
  created_at: string
}

export type Metrics = {
  incident_count: number
  diagnosis_count: number
  confirmation_count: number
  evaluation_count: number
  latest_accuracy_pct: number | null
  provider_status: 'not_configured' | 'ready'
  task_status: 'unavailable' | 'ready'
  adapter_status: 'unavailable' | 'ready' | 'learning'
  simulator_online: boolean
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let detail = `API returned ${response.status} for ${path}`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // ignore json parse failure
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  incidents: () => requestJson<Incident[]>('/api/incidents'),
  diagnoses: () => requestJson<DiagnosisRecord[]>('/api/diagnoses'),
  confirmations: () => requestJson<ConfirmationRecord[]>('/api/confirmations'),
  evaluations: () => requestJson<EvaluationSummary[]>('/api/evaluations'),
  metrics: () => requestJson<Metrics>('/api/metrics'),
  diagnose: (incident_id: string) =>
    requestJson<DiagnosisRecord>('/api/diagnose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ incident_id }),
    }),
  confirm: (payload: ConfirmRequest) =>
    requestJson<ConfirmationRecord>('/api/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  evaluate: () =>
    requestJson<EvaluationSummary>('/api/evaluate', {
      method: 'POST',
    }),
  clearIncidents: () =>
    requestJson<{ status: string }>('/api/incidents/clear', {
      method: 'POST',
    }),
  sendSimulatorCommand: (cmd: Record<string, unknown>) =>
    requestJson<{ ok: boolean; message: string }>('/api/simulator/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cmd),
    }),
}
