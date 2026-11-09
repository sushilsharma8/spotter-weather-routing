import { useEffect, useMemo, useRef, useState } from "react"
import { assessTrip, getHealth, loadCorridor, planTrip } from "./api"
import { ForecastBar } from "./components/ForecastBar"
import { Results } from "./components/Results"
import { TripForm } from "./components/TripForm"
import { tomorrowMorning } from "./format"
import { MapPane } from "./map/MapPane"
import type { AssessResponse, CorridorResponse, PlanResponse, PlanRoute, TripInput } from "./types"

const EMPTY_ROUTES: PlanRoute[] = []

const INITIAL: TripInput = {
  origin: "",
  destination: "",
  originPoint: null,
  destinationPoint: null,
  departure: tomorrowMorning("America/Chicago"),
  timezone: "America/Chicago",
  loadLb: "25000",
  spacing: 25,
}

export function App() {
  const [form, setForm] = useState<TripInput>(INITIAL)
  const [phase, setPhase] = useState<"idle" | "planning" | "assessing" | "ready">("idle")
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<"unknown" | "ok" | "down">("unknown")
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [assessment, setAssessment] = useState<AssessResponse | null>(null)
  const [corridor, setCorridor] = useState<CorridorResponse | null>(null)
  const [corridorError, setCorridorError] = useState<string | null>(null)
  const [hour, setHour] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeCheckpoint, setActiveCheckpoint] = useState<number | null>(0)
  const [editing, setEditing] = useState(true)
  const requestId = useRef(0)

  useEffect(() => {
    getHealth()
      .then((body) => setHealth(body.backend === "django" && body.status === "ok" ? "ok" : "down"))
      .catch(() => setHealth("down"))
  }, [])

  async function submit(next: TripInput) {
    setForm(next)
    if (!next.origin.trim() || !next.destination.trim()) {
      setError("Enter an origin and a destination.")
      return
    }
    const load = Number(next.loadLb)
    if (!Number.isFinite(load) || load < 0) {
      setError("Load weight must be a number of pounds.")
      return
    }
    const id = ++requestId.current
    setError(null)
    setPhase("planning")
    setAssessment(null)
    setCorridor(null)
    setCorridorError(null)
    try {
      const planned = await planTrip(next)
      if (id !== requestId.current) return
      setPlan(planned)
      setEditing(false)
      setSelectedId(planned.routes[0]?.id ?? null)
      setActiveCheckpoint(0)
      setHour(0)
      setPhase("assessing")
      const [assessedResult, corridorResult] = await Promise.allSettled([assessTrip(planned), loadCorridor(planned)])
      if (id !== requestId.current) return
      if (assessedResult.status === "fulfilled") {
        setAssessment(assessedResult.value)
        const recommended = assessedResult.value.recommendation?.route_id
        if (recommended) setSelectedId(recommended)
      } else {
        setError(assessedResult.reason instanceof Error ? assessedResult.reason.message : "Weather assessment failed.")
      }
      if (corridorResult.status === "fulfilled") {
        setCorridor(corridorResult.value)
        setCorridorError(corridorResult.value.warning)
      } else {
        setCorridorError(corridorResult.reason instanceof Error ? corridorResult.reason.message : "Corridor forecast failed.")
      }
      setPhase("ready")
    } catch (caught) {
      if (id !== requestId.current) return
      setPhase(plan ? "ready" : "idle")
      setError(caught instanceof Error ? caught.message : "The trip could not be planned.")
    }
  }

  const selected = useMemo(
    () => plan?.routes.find((route) => route.id === selectedId) || plan?.routes[0] || null,
    [plan, selectedId],
  )

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <p className="mark">Headwind</p>
          <p>Weather-aware route desk</p>
        </div>
        <p className={`api-status is-${health}`}>
          {health === "ok" && "Django API connected"}
          {health === "down" && "Django API unreachable"}
          {health === "unknown" && "Checking Django API"}
        </p>
      </header>
      <aside className="sidebar">
        {editing ? (
          <TripForm value={form} busy={phase === "planning" || phase === "assessing"} onChange={setForm} onSubmit={submit} />
        ) : (
          <div className="trip-summary">
            <p>
              <strong>{plan?.origin.label || form.origin}</strong>
              <span> → </span>
              <strong>{plan?.destination.label || form.destination}</strong>
            </p>
            <button type="button" onClick={() => setEditing(true)}>
              Edit trip
            </button>
          </div>
        )}
        {error && (
          <p className="banner danger" role="alert">
            {error}
          </p>
        )}
        {!plan && !error && (
          <div className="empty">
            <h2>Three roads, scored at arrival.</h2>
            <p>
              Enter a departure. The desk asks a routing engine for distinct driving options, then reads wind, rain, and snow
              depth at the truck’s estimated arrival on each checkpoint.
            </p>
          </div>
        )}
        {phase === "planning" && <p className="banner">Requesting route geometry from the routing engine…</p>}
        {plan && (
          <Results
            plan={plan}
            assessment={assessment}
            assessing={phase === "assessing"}
            selectedId={selected?.id || plan.routes[0].id}
            activeCheckpoint={activeCheckpoint}
            onSelect={(id) => {
              setSelectedId(id)
              setActiveCheckpoint(0)
            }}
            onCheckpoint={setActiveCheckpoint}
            onUsePlace={(which, label, lat, lon) => {
              const point = { label, lat, lon, query: label }
              const next =
                which === "origin"
                  ? { ...form, origin: label, originPoint: point }
                  : { ...form, destination: label, destinationPoint: point }
              void submit(next)
            }}
          />
        )}
      </aside>
      <div className="map-frame">
        <MapPane
          planId={plan?.plan_id || null}
          routes={plan?.routes ?? EMPTY_ROUTES}
          assessed={assessment?.routes || null}
          corridor={corridor}
          spacingMiles={plan?.corridor.sample_spacing_miles || 16}
          hour={hour}
          selectedId={selected?.id || null}
          activeCheckpoint={activeCheckpoint}
          onSelect={(id) => {
            setSelectedId(id)
            setActiveCheckpoint(0)
          }}
          onCheckpoint={(_routeId, index) => setActiveCheckpoint(index)}
        />
        <div className="map-legend">
          <strong>Corridor forecast</strong>
          <span className="risk-low" /> Low
          <span className="risk-moderate" /> Moderate
          <span className="risk-high" /> High
          <span className="risk-severe" /> Severe
          <span className="risk-no_travel" /> No travel
          <span className="risk-unknown" /> Unknown
          <small>Shaded field follows the slider hour. Route dots follow driving arrival.</small>
        </div>
      </div>
      <ForecastBar
        corridor={corridor}
        hour={hour}
        onHour={setHour}
        timezone={plan?.timezone || form.timezone}
        departure={plan?.departure || null}
        selected={selected}
        warning={corridorError}
      />
    </div>
  )
}
