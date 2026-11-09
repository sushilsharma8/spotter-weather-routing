import { useEffect, useState } from "react"
import { suggestPlaces } from "../api"
import { ZONES, zoneLabel } from "../format"
import type { Place, TripInput } from "../types"

type Props = {
  value: TripInput
  busy: boolean
  onChange: (next: TripInput) => void
  onSubmit: (next: TripInput) => void
}

const PRESETS: { label: string; origin: string; destination: string }[] = [
  { label: "Chicago → Detroit", origin: "Chicago, IL", destination: "Detroit, MI" },
  { label: "Dallas → Atlanta", origin: "Dallas, TX", destination: "Atlanta, GA" },
  { label: "Denver → Kansas City", origin: "Denver, CO", destination: "Kansas City, MO" },
]

export function TripForm({ value, busy, onChange, onSubmit }: Props) {
  return (
    <form
      className="trip-form"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(value)
      }}
    >
      <PlaceField
        id="origin"
        label="Origin"
        text={value.origin}
        point={value.originPoint}
        onText={(origin) => onChange({ ...value, origin, originPoint: null })}
        onPoint={(originPoint) => onChange({ ...value, origin: originPoint.label, originPoint })}
      />
      <PlaceField
        id="destination"
        label="Destination"
        text={value.destination}
        point={value.destinationPoint}
        onText={(destination) => onChange({ ...value, destination, destinationPoint: null })}
        onPoint={(destinationPoint) =>
          onChange({ ...value, destination: destinationPoint.label, destinationPoint })
        }
      />
      <div className="field-row">
        <label>
          Departure
          <input
            type="datetime-local"
            value={value.departure}
            onChange={(event) => onChange({ ...value, departure: event.target.value })}
            required
          />
        </label>
        <label>
          Timezone
          <select
            value={value.timezone}
            onChange={(event) => onChange({ ...value, timezone: event.target.value })}
          >
            {ZONES.map((zone) => (
              <option key={zone.id} value={zone.id}>
                {zone.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="hint">
        The clock is {zoneLabel(value.timezone)} wall time. It is not taken from the browser timezone.
      </p>
      <label>
        Load weight (lb)
        <input
          type="number"
          min={0}
          max={200000}
          step={100}
          inputMode="decimal"
          value={value.loadLb}
          onChange={(event) => onChange({ ...value, loadLb: event.target.value })}
          required
        />
      </label>
      <p className="hint">
        Above 30,000 lb, wind from 45 up to 55 mph is No Travel. Above 40,000 lb, wind from 35 up to 45 mph is Severe.
        30,000 and 40,000 themselves do not trigger those steps.
      </p>
      <fieldset>
        <legend>Checkpoint spacing</legend>
        <div className="segmented" role="radiogroup" aria-label="Checkpoint spacing">
          {([10, 25, 50] as const).map((miles) => (
            <label key={miles} className={value.spacing === miles ? "is-selected" : ""}>
              <input
                type="radio"
                name="spacing"
                value={miles}
                checked={value.spacing === miles}
                onChange={() => onChange({ ...value, spacing: miles })}
              />
              {miles} mi
            </label>
          ))}
        </div>
      </fieldset>
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Working…" : "Plan routes"}
      </button>
      <div className="presets">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() =>
              onSubmit({
                ...value,
                origin: preset.origin,
                destination: preset.destination,
                originPoint: null,
                destinationPoint: null,
              })
            }
          >
            {preset.label}
          </button>
        ))}
      </div>
      <p className="disclaimer">
        Routes are car-profile driving paths, not certified truck routes. They do not apply height, weight, or restricted-road rules.
      </p>
    </form>
  )
}

function PlaceField({
  id,
  label,
  text,
  point,
  onText,
  onPoint,
}: {
  id: string
  label: string
  text: string
  point: Place | null
  onText: (value: string) => void
  onPoint: (place: Place) => void
}) {
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<Place[]>([])

  useEffect(() => {
    if (!open || point || text.trim().length < 2) {
      setResults([])
      return
    }
    const handle = window.setTimeout(() => {
      suggestPlaces(text)
        .then(setResults)
        .catch(() => setResults([]))
    }, 220)
    return () => window.clearTimeout(handle)
  }, [text, open, point])

  return (
    <label className="place-field">
      {label}
      <input
        id={id}
        value={text}
        autoComplete="off"
        placeholder="City, address, or lat, lon"
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onChange={(event) => {
          setOpen(true)
          onText(event.target.value)
        }}
        required
      />
      {open && results.length > 0 && (
        <ul className="suggestions">
          {results.map((place) => (
            <li key={`${place.label}-${place.lat}`}>
              <button
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault()
                  onPoint(place)
                  setOpen(false)
                }}
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </label>
  )
}
