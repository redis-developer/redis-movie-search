/**
 * API client for the Video Clip Searcher backend.
 */

// VITE_API_URL overrides; otherwise the relative /api path works with both
// the Vite dev proxy and the nginx proxy in Docker.
const API_BASE = import.meta.env.VITE_API_URL || '/api';

export type Fusion = 'RRF' | 'LINEAR';

export interface ClipResult {
  rank: number;
  id: string;
  title: string;
  movie: string;
  year?: number | null;
  genre: string;
  director?: string;
  duration_seconds?: number | null;
  description: string;
  video_url?: string | null;
  thumbnail_url?: string | null;
  hybrid_score?: number | null;
  text_score?: number | null;
  vector_similarity?: number | null;
}

export interface SearchResponse {
  query: string;
  results: ClipResult[];
  count: number;
  backend: string;
  fusion: string;
  took_ms: number;
}

export interface SearchParams {
  query: string;
  num_results?: number;
  genre?: string;
  year_from?: number;
  year_to?: number;
  fusion?: Fusion;
  vector_weight?: number;
}

export interface HealthResponse {
  status: string;
  redis_connected: boolean;
  index_exists: boolean;
  index_info: Record<string, unknown>;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body.detail === 'string') return body.detail;
  } catch {
    /* ignore */
  }
  return `API error: ${response.status}`;
}

async function post<T>(endpoint: string, body?: object): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

async function get<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export function searchClips(params: SearchParams): Promise<SearchResponse> {
  return post('/search', params);
}

export function checkHealth(): Promise<HealthResponse> {
  return get('/health');
}

export function fetchGenres(): Promise<{ genres: string[] }> {
  return get('/genres');
}

export function ingestClips(): Promise<{ status: string; clips_loaded: number }> {
  return post('/ingest');
}
