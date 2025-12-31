const API_BASE = '/api/v1'

export interface AnalyzeResponse {
  status: 'success' | 'error'
  facts: Facts | null
  error: string | null
}

export interface Facts {
  schema: string
  repo: {
    url: string
    commit: string
    detected_at: string
  }
  languages: Language[]
  frameworks: Framework[]
  architecture: Architecture
  modules: Module[]
  api: {
    endpoints: APIEndpoint[]
    total_count: number
  }
  frontend_routes: FrontendRoute[]
  models: ORMModel[]
  runtime: {
    dependencies: Dependency[]
    build_files: string[]
    entrypoints: string[]
  }
}

export interface Language {
  name: string
  ratio: number
  lines_of_code: number
  evidence: Evidence[]
}

export interface Framework {
  name: string
  type: string
  evidence: Evidence[]
}

export interface Architecture {
  type: string
  layers: string[]
  details: Record<string, unknown>
  evidence: Evidence[]
}

export interface Module {
  name: string
  role: string
  path: string
  submodules: string[]
  evidence: Evidence[]
}

export interface APIEndpoint {
  method: string
  path: string
  full_path: string
  handler: string
  router: string
  file: string
  tags: string[]
  auth_required: boolean
  description: string
}

export interface FrontendRoute {
  path: string
  name: string
  component: string
  file: string
  auth_required: boolean
}

export interface ORMModel {
  name: string
  table: string
  fields: { name: string; type: string; foreign_key?: string }[]
  relationships: { name: string; target: string }[]
  file: string
}

export interface Dependency {
  name: string
  version: string
  evidence: Evidence[]
}

export interface Evidence {
  path: string
  lines?: number[]
}

export async function analyzeRepository(repoUrl: string): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/analyzer/analyze/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ repo_url: repoUrl }),
  })

  return response.json()
}
