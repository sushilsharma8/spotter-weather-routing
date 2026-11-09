export type Place = {
  label: string
  lat: number
  lon: number
  query?: string
}

export type Checkpoint = {
  index: number
  mile: number
  lat: number
  lon: number
  elapsed_seconds: number
  is_origin: boolean
  is_destination: boolean
  eta?: string
  wind_mph?: number | null
  rain_in_hr?: number | null
  snow_in_hr?: number | null
  wind_risk?: string | null
  rain_risk?: string | null
  snow_risk?: string | null
  load_adjusted_wind_risk?: string | null
  risk?: string
  missing?: string[]
  detail?: string
  forecast_error?: string | null
}

export type Segment = {
  from_index: number
  to_index: number
  miles: number
  risk: string
}

export type Summary = {
  total_miles: number
  low_miles: number
  moderate_miles: number
  high_miles: number
  severe_miles: number
  no_travel_miles: number
  unknown_miles: number
  average_risk: number | null
  eligible: boolean
  blockers: string[]
}

export type PlanRoute = {
  id: string
  provider: string
  kind: string
  profile: string
  road_name: string | null
  timing: string
  truck_restrictions: boolean
  has_toll: boolean | null
  has_highway: boolean | null
  via: { lat: number; lon: number; fraction: number; side: string } | null
  distance_miles: number
  engine_distance_miles: number
  duration_seconds: number
  geometry: { coordinates: number[][]; miles: number[] }
  checkpoints: Checkpoint[]
}

export type PlanResponse = {
  plan_id: string
  origin: Place
  destination: Place
  origin_alternatives: Place[]
  destination_alternatives: Place[]
  departure: string
  timezone: string
  load_lb: number
  spacing_miles: number
  routes: PlanRoute[]
  route_count: number
  notes: string[]
  provider_errors: string[]
  assumptions: string[]
  corridor: { sample_spacing_miles: number; points: { lat: number; lon: number }[] }
}

export type AssessedRoute = {
  id: string
  checkpoints: Checkpoint[]
  segments: Segment[]
  summary: Summary
}

export type Criterion = {
  id: string
  severe_miles: number
  high_miles: number
  average_risk: number | null
  duration_seconds: number
  eligible: boolean
  blockers: string[]
}

export type AssessResponse = {
  routes: AssessedRoute[]
  recommendation: { route_id: string; reasons: string[]; eligible_ids: string[] } | null
  warning: string | null
  criteria: Criterion[]
}

export type CorridorPoint = {
  lat: number
  lon: number
  risk: number[]
  wind_mph: (number | null)[]
  rain_in_hr: (number | null)[]
  snow_in_hr: (number | null)[]
}

export type CorridorResponse = {
  times: string[]
  hour_count: number
  risk_scale: Record<string, string>
  points: CorridorPoint[]
  warning: string | null
  note: string
}

export type TripInput = {
  origin: string
  destination: string
  originPoint: Place | null
  destinationPoint: Place | null
  departure: string
  timezone: string
  loadLb: string
  spacing: 10 | 25 | 50
}
