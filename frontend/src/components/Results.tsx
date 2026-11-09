import { formatClock, formatDuration, formatElapsed, formatMiles, kindName, riskName } from "../format"
import { RISK_COLOR } from "../map/colors"
import type { AssessedRoute, AssessResponse, PlanResponse } from "../types"

type Props = {
  plan: PlanResponse
  assessment: AssessResponse | null
  assessing: boolean
  selectedId: string
  activeCheckpoint: number | null
  onSelect: (id: string) => void
  onCheckpoint: (index: number) => void
  onUsePlace: (which: "origin" | "destination", label: string, lat: number, lon: number) => void
}

export function Results({
  plan,
  assessment,
  assessing,
  selectedId,
  activeCheckpoint,
  onSelect,
  onCheckpoint,
  onUsePlace,
}: Props) {
  const assessed = new Map((assessment?.routes || []).map((route) => [route.id, route]))
  const selected = plan.routes.find((route) => route.id === selectedId) || plan.routes[0]
  const selectedDetail = selected ? assessed.get(selected.id) : undefined
  const rank = new Map((assessment?.recommendation?.eligible_ids || []).map((id, index) => [id, index + 1]))

  return (
    <section className="results">
      <p className="resolved">
        <strong>{plan.origin.label}</strong>
        <span aria-hidden="true"> → </span>
        <strong>{plan.destination.label}</strong>
        <span className="resolved-meta">
          {formatClock(plan.departure, plan.timezone)} · {plan.load_lb.toLocaleString()} lb · every {plan.spacing_miles} mi
        </span>
      </p>
      <PlaceAlts label="Origin" places={plan.origin_alternatives} onPick={(place) => onUsePlace("origin", place.label, place.lat, place.lon)} />
      <PlaceAlts
        label="Destination"
        places={plan.destination_alternatives}
        onPick={(place) => onUsePlace("destination", place.label, place.lat, place.lon)}
      />
      {plan.notes.map((note) => (
        <p key={note} className={note.includes("Only") ? "banner warn" : "note"}>
          {note}
        </p>
      ))}
      {plan.provider_errors.length > 0 && (
        <p className="banner warn">Routing fallback: {plan.provider_errors.join(" ")}</p>
      )}
      {assessment?.warning && <p className="banner warn">{assessment.warning}</p>}

      <div className={assessment?.recommendation ? "recommend" : "recommend is-empty"} aria-live="polite">
        {assessing && !assessment ? (
          <p>Sampling weather at each checkpoint’s estimated arrival…</p>
        ) : assessment?.recommendation ? (
          <>
            <p className="eyebrow">Recommended</p>
            <h2>Route {assessment.recommendation.route_id}</h2>
            <ul>
              {assessment.recommendation.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </>
        ) : assessment ? (
          <>
            <p className="eyebrow">No route recommended</p>
            <h2>Every option is blocked</h2>
            <p>Each route has No Travel miles or a missing forecast. Missing weather is not treated as Low, and a blocked route is not quietly ranked.</p>
          </>
        ) : null}
      </div>

      <div className="route-list">
        {plan.routes.map((route) => {
          const detail = assessed.get(route.id)
          const blocked = detail ? !detail.summary.eligible : false
          return (
            <button
              key={route.id}
              type="button"
              className={`route-card${route.id === selectedId ? " is-selected" : ""}${blocked ? " is-blocked" : ""}`}
              onClick={() => onSelect(route.id)}
            >
              <div className="route-card-top">
                <span className="stamp">{route.id}</span>
                <span>
                  <strong>{route.road_name ? `via ${route.road_name}` : "Driving option"}</strong>
                  <small>
                    {kindName(route.kind)} · {route.provider} · {route.profile}
                    {route.has_toll ? " · tolls" : ""}
                    {route.has_highway ? " · highway" : ""}
                  </small>
                </span>
                {assessment?.recommendation?.route_id === route.id && <em>Recommended</em>}
                {blocked && <em className="danger">{detail?.summary.no_travel_miles ? "No travel" : "Forecast gap"}</em>}
              </div>
              <p className="route-metrics">
                <span>{formatMiles(route.distance_miles)}</span>
                <span>{formatDuration(route.duration_seconds)}</span>
                <span>{detail ? `${detail.checkpoints.length} checkpoints` : "Weather pending"}</span>
              </p>
              {detail && (
                <>
                  <RiskBar summary={detail.summary} />
                  <p className="mile-split">
                    Severe {formatMiles(detail.summary.severe_miles)} · High {formatMiles(detail.summary.high_miles)} · Avg{" "}
                    {detail.summary.average_risk == null ? "unavailable" : detail.summary.average_risk.toFixed(2)}
                  </p>
                  {detail.summary.blockers.map((blocker) => (
                    <p key={blocker} className="blocker">
                      {blocker}
                    </p>
                  ))}
                </>
              )}
            </button>
          )
        })}
      </div>

      {assessment && (
        <table className="criteria">
          <caption>Ranking uses severe miles, then high miles, then average risk, then travel time.</caption>
          <thead>
            <tr>
              <th>Route</th>
              <th>Severe</th>
              <th>High</th>
              <th>Avg risk</th>
              <th>Time</th>
              <th>Rank</th>
            </tr>
          </thead>
          <tbody>
            {assessment.criteria.map((row) => (
              <tr key={row.id} className={row.id === assessment.recommendation?.route_id ? "is-winner" : ""}>
                <th>{row.id}</th>
                <td>{row.severe_miles.toFixed(1)}</td>
                <td>{row.high_miles.toFixed(1)}</td>
                <td>{row.average_risk == null ? "—" : row.average_risk.toFixed(2)}</td>
                <td>{formatDuration(row.duration_seconds)}</td>
                <td>{row.eligible ? rank.get(row.id) : "Excluded"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <div className="checkpoints">
          <h3>
            Route {selected.id} checkpoints
            <small>Risk uses arrival time, not departure.</small>
          </h3>
          <ul>
            {(selectedDetail?.checkpoints || selected.checkpoints).map((point) => (
              <li key={point.index}>
                <button
                  type="button"
                  className={point.index === activeCheckpoint ? "is-active" : ""}
                  onClick={() => onCheckpoint(point.index)}
                >
                  <span className="swatch" style={{ background: RISK_COLOR[point.risk || "pending"] }} />
                  <span>
                    <strong>
                      Mile {point.mile.toFixed(1)}
                      {point.is_origin ? " · depart" : ""}
                      {point.is_destination ? " · arrive" : ""}
                    </strong>
                    <small>
                      {point.eta ? formatClock(point.eta, plan.timezone) : "ETA pending"} · {formatElapsed(point.elapsed_seconds)} driving
                    </small>
                  </span>
                  <em>{riskName(point.risk)}</em>
                </button>
                {point.index === activeCheckpoint && point.detail && (
                  <p className="detail">
                    {point.detail} Wind {point.wind_mph == null ? "—" : `${point.wind_mph.toFixed(1)} mph`}, rain{" "}
                    {point.rain_in_hr == null ? "—" : `${point.rain_in_hr.toFixed(3)} in/hr`}, snow depth{" "}
                    {point.snow_in_hr == null ? "—" : `${point.snow_in_hr.toFixed(3)} in/hr`}.
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="assumptions">
        <summary>Assumptions and scoring</summary>
        <ul>
          {plan.assumptions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </section>
  )
}

function PlaceAlts({
  label,
  places,
  onPick,
}: {
  label: string
  places: { label: string; lat: number; lon: number }[]
  onPick: (place: { label: string; lat: number; lon: number }) => void
}) {
  if (!places.length) return null
  return (
    <p className="alts">
      Other {label.toLowerCase()} matches:
      {places.map((place) => (
        <button key={place.label} type="button" onClick={() => onPick(place)}>
          {place.label}
        </button>
      ))}
    </p>
  )
}

function RiskBar({ summary }: { summary: AssessedRoute["summary"] }) {
  const total = summary.total_miles || 1
  const parts = [
    ["low", summary.low_miles],
    ["moderate", summary.moderate_miles],
    ["high", summary.high_miles],
    ["severe", summary.severe_miles],
    ["no_travel", summary.no_travel_miles],
    ["unknown", summary.unknown_miles],
  ] as const
  return (
    <div className="risk-bar" aria-hidden="true">
      {parts.map(([name, miles]) =>
        miles > 0.05 ? <span key={name} className={`risk-${name}`} style={{ width: `${(miles / total) * 100}%` }} /> : null,
      )}
    </div>
  )
}
