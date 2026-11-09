import { formatClock, formatDuration, riskName } from "../format"
import { RISK_COLOR } from "../map/colors"
import type { CorridorPoint, CorridorResponse, PlanRoute } from "../types"

const LEGEND = [
  ["low", "Low"],
  ["moderate", "Moderate"],
  ["high", "High"],
  ["severe", "Severe"],
  ["no_travel", "No travel"],
  ["unknown", "Unknown"],
] as const

type Props = {
  corridor: CorridorResponse | null
  hour: number
  onHour: (hour: number) => void
  timezone: string
  departure: string | null
  selected: PlanRoute | null
  warning: string | null
}

export function ForecastBar({ corridor, hour, onHour, timezone, departure, selected, warning }: Props) {
  const time = corridor?.times[hour]
  const sample = selected && corridor ? nearest(selected, corridor) : corridor?.points[0]
  const wind = sample?.wind_mph[hour]
  const rain = sample?.rain_in_hr[hour]
  const snow = sample?.snow_in_hr[hour]
  const risk = sample ? riskName(scaleName(sample.risk[hour])) : "Pending"
  const arrivalHours = selected ? selected.duration_seconds / 3600 : null

  return (
    <section className="forecast">
      <div className="forecast-head">
        <div>
          <p className="eyebrow">Corridor forecast</p>
          <h2>{time && departure ? formatClock(time, timezone) : "Plan a trip to load the corridor"}</h2>
          <p className="hint">
            Hour {hour} of 48 is a clock offset from departure
            {departure ? ` (${formatClock(departure, timezone)})` : ""}. It is not where the truck is. The teal bar is the
            selected route’s driving window. Checkpoint colors use driving time along the road.
          </p>
        </div>
        <p className="readout">
          <strong>{risk}</strong>
          <span>
            Wind {wind == null ? "—" : `${wind.toFixed(1)} mph`} · Rain {rain == null ? "—" : `${rain.toFixed(3)} in/hr`} ·
            Snow {snow == null ? "—" : `${snow.toFixed(3)} in/hr`}
          </span>
          <small>Sample nearest the middle of the selected route. Load rules are included.</small>
        </p>
      </div>
      {warning && <p className="banner warn">{warning}</p>}
      <div className="ruler" aria-hidden="true">
        {arrivalHours != null && arrivalHours > 0 && arrivalHours <= 48 && (
          <>
            <span className="drive-window" style={{ width: `${(arrivalHours / 48) * 100}%` }} />
            <i style={{ left: `${(arrivalHours / 48) * 100}%` }} title={`Arrives after ${formatDuration(selected?.duration_seconds || 0)} of driving`} />
          </>
        )}
      </div>
      <input
        type="range"
        min={0}
        max={48}
        step={1}
        value={hour}
        disabled={!corridor}
        aria-label="Forecast hour after departure"
        aria-valuetext={time ? formatClock(time, timezone) : "No forecast loaded"}
        onChange={(event) => onHour(Number(event.target.value))}
      />
      <div className="ticks">
        <span>Depart</span>
        <span>+12h</span>
        <span>+24h</span>
        <span>+36h</span>
        <span>+48h</span>
      </div>
      {arrivalHours != null && arrivalHours > 48 && (
        <p className="hint">This route arrives after 48 hours. Checkpoint risk still uses the full driving time, past the slider.</p>
      )}
      {sample && (
        <div className="sparks">
          <Spark label="Wind mph" values={sample.wind_mph} hour={hour} color="#0f6e62" />
          <Spark label="Rain in/hr" values={sample.rain_in_hr} hour={hour} color="#1d4e89" />
          <Spark label="Snow in/hr" values={sample.snow_in_hr} hour={hour} color="#6e1636" />
        </div>
      )}
      <ul className="legend">
        {LEGEND.map(([key, label]) => (
          <li key={key}>
            <span className={`swatch risk-${key}`} style={{ background: RISK_COLOR[key] }} />
            {label}
          </li>
        ))}
      </ul>
      <p className="hint">{corridor?.note || "The heatmap uses the same risk colors as the routes."}</p>
    </section>
  )
}

function scaleName(code: number | undefined): string {
  return ["unknown", "low", "moderate", "high", "severe", "no_travel"][code ?? 0] || "unknown"
}

function nearest(route: PlanRoute, corridor: CorridorResponse): CorridorPoint | undefined {
  const miles = route.geometry.miles
  const coordinates = route.geometry.coordinates
  if (!miles.length || !corridor.points.length) return undefined
  const target = miles[miles.length - 1] / 2
  let bestDelta = Infinity
  let mid = coordinates[0]
  miles.forEach((mile, index) => {
    const delta = Math.abs(mile - target)
    if (delta < bestDelta) {
      bestDelta = delta
      mid = coordinates[index]
    }
  })
  let chosen = corridor.points[0]
  let best = Infinity
  for (const point of corridor.points) {
    const distance = (point.lat - mid[1]) ** 2 + (point.lon - mid[0]) ** 2
    if (distance < best) {
      best = distance
      chosen = point
    }
  }
  return chosen
}

function Spark({
  label,
  values,
  hour,
  color,
}: {
  label: string
  values: (number | null)[]
  hour: number
  color: string
}) {
  const finite = values.filter((value): value is number => value != null)
  const max = Math.max(0.001, ...finite, 0)
  const paths: string[] = []
  let current: string[] = []
  values.forEach((value, index) => {
    if (value == null) {
      if (current.length > 1) paths.push(current.join(" "))
      current = []
      return
    }
    const y = 16 - (value / max) * 14
    current.push(`${index},${y.toFixed(2)}`)
  })
  if (current.length > 1) paths.push(current.join(" "))
  const currentValue = values[hour]
  return (
    <figure className="spark">
      <figcaption>
        {label}
        <strong>{currentValue == null ? "—" : currentValue.toFixed(label.startsWith("Wind") ? 1 : 3)}</strong>
      </figcaption>
      <svg viewBox="0 0 48 20" role="img" aria-label={`${label} across 48 hours`}>
        {paths.map((points) => (
          <polyline key={points.slice(0, 24)} fill="none" stroke={color} strokeWidth="1.3" points={points} />
        ))}
        <line x1={hour} x2={hour} y1="1" y2="19" stroke="#1d1a16" strokeWidth="0.5" />
      </svg>
    </figure>
  )
}
