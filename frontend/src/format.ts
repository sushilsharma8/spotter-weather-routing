export const ZONES: { id: string; label: string }[] = [
  { id: "America/New_York", label: "Eastern" },
  { id: "America/Chicago", label: "Central" },
  { id: "America/Denver", label: "Mountain" },
  { id: "America/Phoenix", label: "Arizona" },
  { id: "America/Los_Angeles", label: "Pacific" },
  { id: "America/Anchorage", label: "Alaska" },
  { id: "Pacific/Honolulu", label: "Hawaii" },
  { id: "UTC", label: "UTC" },
]

export function zoneLabel(timeZone: string): string {
  return ZONES.find((zone) => zone.id === timeZone)?.label || timeZone
}

export function tomorrowMorning(timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date())
  const year = Number(parts.find((part) => part.type === "year")?.value)
  const month = Number(parts.find((part) => part.type === "month")?.value)
  const day = Number(parts.find((part) => part.type === "day")?.value)
  const next = new Date(Date.UTC(year, month - 1, day + 1))
  return `${next.toISOString().slice(0, 10)}T07:00`
}

export function formatClock(iso: string, timeZone: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date)
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.round((total % 3600) / 60)
  if (hours <= 0) return `${minutes}m`
  return `${hours}h ${String(minutes).padStart(2, "0")}m`
}

export function formatElapsed(seconds: number): string {
  const sign = seconds < 0 ? "-" : "+"
  return `${sign}${formatDuration(Math.abs(seconds))}`
}

export function formatMiles(miles: number): string {
  return `${miles.toFixed(1)} mi`
}

export function riskName(risk: string | null | undefined): string {
  switch (risk) {
    case "low":
      return "Low"
    case "moderate":
      return "Moderate"
    case "high":
      return "High"
    case "severe":
      return "Severe"
    case "no_travel":
      return "No travel"
    case "unknown":
      return "Unknown"
    default:
      return "Pending"
  }
}

export function kindName(kind: string): string {
  if (kind === "primary") return "Engine primary"
  if (kind === "alternate") return "Engine alternate"
  if (kind === "via") return "Via-constrained"
  return kind
}

export const RISK_ORDER = ["low", "moderate", "high", "severe", "no_travel", "unknown"] as const
