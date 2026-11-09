import type { AssessResponse, CorridorResponse, Place, PlanResponse, TripInput } from "./types"

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "")

async function read<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => ({}))) as { error?: string }
  if (!response.ok) {
    throw new Error(body.error || `Request failed (${response.status}).`)
  }
  return body as T
}

export async function getHealth(): Promise<{ status: string; backend: string }> {
  const response = await fetch(`${API_BASE}/api/health`)
  return read(response)
}

export async function suggestPlaces(query: string): Promise<Place[]> {
  const response = await fetch(`${API_BASE}/api/suggest?q=${encodeURIComponent(query)}`)
  const body = await read<{ results: Place[] }>(response)
  return body.results
}

function placePayload(text: string, point: Place | null) {
  if (point) {
    return { query: text, label: point.label, lat: point.lat, lon: point.lon }
  }
  return text.trim()
}

export async function planTrip(input: TripInput): Promise<PlanResponse> {
  const response = await fetch(`${API_BASE}/api/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin: placePayload(input.origin, input.originPoint),
      destination: placePayload(input.destination, input.destinationPoint),
      departure: input.departure,
      timezone: input.timezone,
      load_lb: Number(input.loadLb),
      spacing_miles: input.spacing,
    }),
  })
  return read(response)
}

export async function assessTrip(plan: PlanResponse): Promise<AssessResponse> {
  const response = await fetch(`${API_BASE}/api/assess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      load_lb: plan.load_lb,
      timezone: plan.timezone,
      departure: plan.departure.slice(0, 16),
      routes: plan.routes.map((route) => ({
        id: route.id,
        duration_seconds: route.duration_seconds,
        checkpoints: route.checkpoints.map((point) => ({
          index: point.index,
          mile: point.mile,
          lat: point.lat,
          lon: point.lon,
          elapsed_seconds: point.elapsed_seconds,
          is_origin: point.is_origin,
          is_destination: point.is_destination,
        })),
      })),
    }),
  })
  return read(response)
}

export async function loadCorridor(plan: PlanResponse): Promise<CorridorResponse> {
  const response = await fetch(`${API_BASE}/api/corridor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      load_lb: plan.load_lb,
      timezone: plan.timezone,
      departure: plan.departure.slice(0, 16),
      points: plan.corridor.points,
    }),
  })
  return read(response)
}
