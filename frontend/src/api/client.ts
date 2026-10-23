export type Incident = {
  id: string
  robot_type: string
  time_window: string
  commanded_action: string
  // Owners A and B will define the nested reading contract.
  readings: Record<string, unknown>[]
  fault_codes: string[]
  technician_note: string
  source_type: 'synthetic' | 'measured' | 'operator-observed'
}

export type Metrics = {
  incident_count: number
  diagnosis_count: number
  confirmation_count: number
  provider_status: 'not_configured'
  task_status: 'unavailable'
  adapter_status: 'unavailable'
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`API returned ${response.status} for ${path}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  incidents: () => getJson<Incident[]>('/api/incidents'),
  metrics: () => getJson<Metrics>('/api/metrics'),
}

