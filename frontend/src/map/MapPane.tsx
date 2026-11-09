import { useEffect, useRef } from "react"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import type { AssessedRoute, CorridorResponse, PlanRoute } from "../types"
import { RISK_COLOR } from "./colors"

type Props = {
  planId: string | null
  routes: PlanRoute[]
  assessed: AssessedRoute[] | null
  corridor: CorridorResponse | null
  spacingMiles: number
  hour: number
  selectedId: string | null
  activeCheckpoint: number | null
  onSelect: (id: string) => void
  onCheckpoint: (routeId: string, index: number) => void
}

type HeatLayer = L.Layer & {
  setData: (points: CorridorResponse["points"], spacing: number) => void
  setHour: (hour: number) => void
}

const RISK_RGB: [number, number, number][] = [
  [109, 103, 95],
  [44, 138, 74],
  [184, 134, 11],
  [216, 101, 18],
  [210, 60, 52],
  [110, 22, 54],
]

function fieldColor(risk: number, wind: number | null, rain: number | null, snow: number | null): { fill: string; strength: number } {
  const rgb = RISK_RGB[risk] ?? RISK_RGB[0]
  const magnitude = Math.max(
    wind == null ? 0 : Math.min(1, wind / 40),
    rain == null ? 0 : Math.min(1, rain / 0.35),
    snow == null ? 0 : Math.min(1, snow / 1.5),
  )
  const floor = [0.5, 0.16, 0.58, 0.72, 0.84, 0.92][risk] ?? 0.4
  const strength = Math.max(floor, magnitude)
  const wash = (1 - strength) * 0.78
  const red = Math.round(rgb[0] + (244 - rgb[0]) * wash)
  const green = Math.round(rgb[1] + (239 - rgb[1]) * wash)
  const blue = Math.round(rgb[2] + (220 - rgb[2]) * wash)
  const alpha = 0.28 + 0.62 * strength
  return { fill: `rgba(${red},${green},${blue},${alpha.toFixed(3)})`, strength }
}

const CorridorCanvas = L.Layer.extend({
  initialize(this: HeatState) {
    this._points = []
    this._hour = 0
    this._spacing = 16
    this._projected = null
  },
  onAdd(this: HeatState, map: L.Map) {
    this._map = map
    this._canvas = L.DomUtil.create("canvas", "corridor-canvas", map.getPane("overlayPane") || undefined)
    map.on("moveend zoomend resize", this._reset, this)
    this._reset()
  },
  onRemove(this: HeatState, map: L.Map) {
    map.off("moveend zoomend resize", this._reset, this)
    if (this._canvas) L.DomUtil.remove(this._canvas)
  },
  setData(this: HeatState, points: CorridorResponse["points"], spacing: number) {
    this._points = points
    this._spacing = spacing
    this._projected = null
    this._reset()
  },
  setHour(this: HeatState, hour: number) {
    this._hour = hour
    this._draw()
  },
  _reset(this: HeatState) {
    if (!this._map || !this._canvas) return
    const size = this._map.getSize()
    const topLeft = this._map.containerPointToLayerPoint([0, 0])
    L.DomUtil.setPosition(this._canvas, topLeft)
    const ratio = window.devicePixelRatio || 1
    this._ratio = ratio
    this._canvas.width = Math.max(1, size.x * ratio)
    this._canvas.height = Math.max(1, size.y * ratio)
    this._canvas.style.width = `${size.x}px`
    this._canvas.style.height = `${size.y}px`
    this._projected = this._points.map((point) => {
      const projected = this._map.latLngToContainerPoint([point.lat, point.lon])
      return {
        x: projected.x * ratio,
        y: projected.y * ratio,
        risk: point.risk,
        wind: point.wind_mph,
        rain: point.rain_in_hr,
        snow: point.snow_in_hr,
      }
    })
    this._draw()
  },
  _draw(this: HeatState) {
    if (!this._canvas || !this._map || !this._projected) return
    const ctx = this._canvas.getContext("2d")
    if (!ctx) return
    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height)
    if (!this._projected.length) return
    const lat = this._points[0]?.lat ?? 40
    const zoom = this._map.getZoom()
    const metersPerPixel = (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom
    const radius = Math.max(18, Math.min(110, ((this._spacing * 1609.344) / metersPerPixel) * 0.72)) * (this._ratio || 1)
    const hour = this._hour
    const painted = this._projected
      .map((point) => {
        const risk = point.risk[hour] ?? 0
        const color = fieldColor(risk, point.wind[hour] ?? null, point.rain[hour] ?? null, point.snow[hour] ?? null)
        return { ...point, risk, ...color }
      })
      .sort((a, b) => a.strength - b.strength || a.risk - b.risk)
    for (const point of painted) {
      const gradient = ctx.createRadialGradient(point.x, point.y, radius * 0.08, point.x, point.y, radius)
      gradient.addColorStop(0, point.fill)
      gradient.addColorStop(1, "rgba(244, 239, 220, 0)")
      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2)
      ctx.fill()
    }
  },
})

type HeatState = {
  _points: CorridorResponse["points"]
  _hour: number
  _spacing: number
  _projected: {
    x: number
    y: number
    risk: number[]
    wind: (number | null)[]
    rain: (number | null)[]
    snow: (number | null)[]
  }[] | null
  _map: L.Map
  _canvas: HTMLCanvasElement
  _ratio: number
  _reset: () => void
  _draw: () => void
}

function sliceLine(coordinates: number[][], miles: number[], start: number, end: number): L.LatLngExpression[] {
  const line: L.LatLngExpression[] = []
  const push = (lon: number, lat: number) => line.push([lat, lon])
  for (let index = 0; index < miles.length; index += 1) {
    const previous = index > 0 ? miles[index - 1] : miles[index]
    if (index > 0 && miles[index] > start && previous < start && line.length === 0) {
      const span = miles[index] - previous
      const fraction = span <= 0 ? 0 : (start - previous) / span
      push(
        coordinates[index - 1][0] + (coordinates[index][0] - coordinates[index - 1][0]) * fraction,
        coordinates[index - 1][1] + (coordinates[index][1] - coordinates[index - 1][1]) * fraction,
      )
    }
    if (miles[index] + 1e-6 >= start && miles[index] - 1e-6 <= end) {
      push(coordinates[index][0], coordinates[index][1])
    }
    if (miles[index] >= end) {
      if (index > 0 && miles[index] > end && previous < end) {
        const span = miles[index] - previous
        const fraction = span <= 0 ? 0 : (end - previous) / span
        push(
          coordinates[index - 1][0] + (coordinates[index][0] - coordinates[index - 1][0]) * fraction,
          coordinates[index - 1][1] + (coordinates[index][1] - coordinates[index - 1][1]) * fraction,
        )
      }
      break
    }
  }
  return line
}

export function MapPane({
  planId,
  routes,
  assessed,
  corridor,
  spacingMiles,
  hour,
  selectedId,
  activeCheckpoint,
  onSelect,
  onCheckpoint,
}: Props) {
  const frame = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const heatRef = useRef<HeatLayer | null>(null)
  const routesRef = useRef<L.LayerGroup | null>(null)
  const fitted = useRef<string | null>(null)
  const selectRef = useRef(onSelect)
  const checkpointRef = useRef(onCheckpoint)
  selectRef.current = onSelect
  checkpointRef.current = onCheckpoint

  useEffect(() => {
    const node = frame.current
    if (!node || mapRef.current) return
    const map = L.map(node, {
      zoomControl: false,
      preferCanvas: true,
      attributionControl: true,
    }).setView([39.5, -96.5], 4)
    L.control.zoom({ position: "topright" }).addTo(map)
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 18,
      attribution: "Tiles &copy; Esri",
    }).addTo(map)
    const heat = new (CorridorCanvas as unknown as new () => HeatLayer)()
    heat.addTo(map)
    heatRef.current = heat
    routesRef.current = L.layerGroup().addTo(map)
    mapRef.current = map
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(node)
    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
      heatRef.current = null
      routesRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const group = routesRef.current
    if (!map || !group) return
    group.clearLayers()
    const bounds = L.latLngBounds([])
    const assessedById = new Map((assessed || []).map((route) => [route.id, route]))
    const ordered = [...routes].sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId))
    for (const route of ordered) {
      const selected = route.id === selectedId
      const detail = assessedById.get(route.id)
      const { coordinates, miles } = route.geometry
      coordinates.forEach(([lon, lat]) => bounds.extend([lat, lon]))
      const draw = (latlngs: L.LatLngExpression[], risk: string) => {
        if (latlngs.length < 2) return
        if (selected) {
          L.polyline(latlngs, { color: "#fbf7ef", weight: 10, opacity: 0.95, interactive: false }).addTo(group)
        }
        const color = RISK_COLOR[risk] || RISK_COLOR.pending
        const line = L.polyline(latlngs, {
          color,
          weight: selected ? 6 : 3.5,
          opacity: selected ? 0.96 : 0.62,
          dashArray: risk === "no_travel" ? "1 8" : risk === "unknown" ? "5 7" : undefined,
        })
        line.on("click", () => selectRef.current(route.id))
        line.addTo(group)
      }
      if (!detail) {
        draw(coordinates.map(([lon, lat]) => [lat, lon]), "pending")
      } else {
        detail.segments.forEach((segment) => {
          const from = detail.checkpoints[segment.from_index]
          const to = detail.checkpoints[segment.to_index]
          if (!from || !to) return
          draw(sliceLine(coordinates, miles, from.mile, to.mile), segment.risk)
        })
      }
      const midMile = (miles[miles.length - 1] || 0) / 2
      let mid = coordinates[Math.floor(coordinates.length / 2)] || coordinates[0]
      let best = Infinity
      miles.forEach((mile, index) => {
        const delta = Math.abs(mile - midMile)
        if (delta < best && coordinates[index]) {
          best = delta
          mid = coordinates[index]
        }
      })
      if (mid) {
        const icon = L.divIcon({
          className: `route-letter${selected ? " is-selected" : ""}`,
          html: `<span>${route.id}</span>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        })
        L.marker([mid[1], mid[0]], { icon, keyboard: false, interactive: true })
          .on("click", () => selectRef.current(route.id))
          .addTo(group)
      }
      const points = detail?.checkpoints || route.checkpoints
      points.forEach((point) => {
        const active = selected && point.index === activeCheckpoint
        const marker = L.circleMarker([point.lat, point.lon], {
          radius: active ? 8 : selected ? 5.5 : 3.5,
          color: "#fbf7ef",
          weight: active ? 3 : 2,
          fillColor: RISK_COLOR[point.risk || "pending"] || RISK_COLOR.pending,
          fillOpacity: selected ? 1 : 0.85,
        })
        marker.on("click", () => {
          selectRef.current(route.id)
          checkpointRef.current(route.id, point.index)
        })
        const title = point.risk
          ? `${route.id} · mile ${point.mile.toFixed(0)} · ${point.risk.replace("_", " ")}`
          : `${route.id} · mile ${point.mile.toFixed(0)}`
        marker.bindTooltip(title, { direction: "top", opacity: 0.95 })
        marker.addTo(group)
      })
    }
    if (planId && fitted.current !== planId && bounds.isValid()) {
      map.fitBounds(bounds.pad(0.12), { padding: [24, 24] })
      fitted.current = planId
    }
  }, [routes, assessed, selectedId, activeCheckpoint, planId])

  useEffect(() => {
    const heat = heatRef.current
    if (!heat) return
    heat.setData(corridor?.points || [], spacingMiles || corridor?.points.length ? spacingMiles : 16)
  }, [corridor, spacingMiles])

  useEffect(() => {
    heatRef.current?.setHour(hour)
  }, [hour])

  return <div ref={frame} className="map-canvas" />
}
