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
  cause_label:
    | 'wheel obstruction'
    | 'motor power/driver path'
    | 'encoder/reporting fault'
    | 'unknown'
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
  provider_kind: 'local_fixture' | 'mubit' | 'openrouter'
  raw_response: string
  model_label: Diagnosis['cause_label'] | null
  advisory_source: 'application_rules' | 'local_fixture' | 'legacy_provider'
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
  provider_status:
    | 'not_configured'
    | 'missing_credentials'
    | 'local_fixture'
    | 'mubit'
    | 'openrouter'
  simulator_online: boolean
}

export type SetupInfo = {
  version: string
  provider: string
  model: string
  inference_key_configured: boolean
  mubit_key_configured: boolean
  openrouter_key_configured: boolean
  mubit_api_format: 'gemini' | 'openai'
  management_key_configured: boolean
  project_id: string
  task_id: string
  simulator_url: string
  frontend_built: boolean
}
export type MubitStatus = {
  status: 'not_configured' | 'connected'
  checked_at: string
  message?: string
  task?: {
    id: string
    name: string
    stage: string
    rows_count: number
    active_version: number | null
    recommendation: string | null
  }
  versions?: {
    id: string
    version_number: number
    status: string
    score: number | null
  }[]
}
export type FeedbackStatus = {
  configured: boolean
  submission: {
    call_id: string
    rating: string
    feedback_id: string
    submitted_at: string
  } | null
}
export type SyntheticEvaluation = {
  split: string
  evaluated: number
  matched: number
  accuracy: number | null
  key_count: number
  missing_incident_ids: string[]
  excluded_leaky_incident_ids: string[]
  cases: {
    incident_id: string
    predicted_cause: string
    actual_cause: string
    matched: boolean
  }[]
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(75_000),
  })
  if (!response.ok) {
    let detail = `API returned ${response.status} for ${path}`
    try {
      const body = await response.json()
      if (body?.detail)
        detail =
          typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail)
    } catch {
      /* Keep the HTTP status when no JSON body is returned. */
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  incidents: () => requestJson<Incident[]>('/api/incidents'),
  diagnoses: () => requestJson<DiagnosisRecord[]>('/api/diagnoses'),
  repairs: () => requestJson<RepairRecord[]>('/api/repairs'),
  confirmedEvaluation: () =>
    requestJson<ConfirmedEvaluationReport>('/api/evaluation/confirmed'),
  metrics: () => requestJson<Metrics>('/api/metrics'),
  diagnose: (incident_id: string) =>
    requestJson<DiagnosisRecord>('/api/diagnose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ incident_id, request_id: crypto.randomUUID() }),
    }),
  confirm: (payload: ConfirmRequest) =>
    requestJson<ConfirmationRecord>('/api/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  setup: () => requestJson<SetupInfo>('/api/setup'),
  syntheticEvaluation: (split: string, provider: string) =>
    requestJson<SyntheticEvaluation>(
      `/api/evaluation/synthetic?split=${split}&provider_kind=${provider}`,
    ),
  mubitStatus: () => requestJson<MubitStatus>('/api/mubit/status'),
  feedbackStatus: (id: string) =>
    requestJson<FeedbackStatus>(
      `/api/diagnoses/${encodeURIComponent(id)}/feedback`,
    ),
  submitFeedback: (id: string, call_id: string) =>
    requestJson<FeedbackStatus['submission']>(
      `/api/diagnoses/${encodeURIComponent(id)}/feedback`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ call_id }),
      },
    ),
  createDemo: (scenario: string) =>
    requestJson<Incident>(`/api/demo/${scenario}`, { method: 'POST' }),
  importIncident: (incident: unknown) =>
    requestJson<Incident>('/api/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(incident),
    }),
}
