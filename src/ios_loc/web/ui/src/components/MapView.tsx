import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import { Crosshair } from "lucide-react"
import type { LatLon } from "@/api/types"
import CoordBox from "@/components/CoordBox"
import { Button } from "@/components/ui/button"
import { fromLngLat, toLngLat } from "@/lib/coords"
import { initialFollow, onRecenter, onUserPan, shouldCenter } from "@/lib/follow"
import { useWalkMeta, walkStore } from "@/hooks/useWalkStream"

const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] }

function lineOf(points: LatLon[]): GeoJSON.FeatureCollection {
  if (points.length < 2) return EMPTY
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: points.map(toLngLat) },
      },
    ],
  }
}

function pointsOf(points: LatLon[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: points.map((p, index) => ({
      type: "Feature",
      properties: { index, label: String(index + 1) },
      geometry: { type: "Point", coordinates: toLngLat(p) },
    })),
  }
}

export interface MapViewProps {
  draftWaypoints: LatLon[]
  draftRoute: LatLon[]
  editing: boolean
  onMapClick(point: LatLon): void
  onWaypointDrag(index: number, point: LatLon): void
  onWaypointClick(index: number): void
}

export default function MapView(props: MapViewProps) {
  const container = useRef<HTMLDivElement | null>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)
  const follow = useRef(initialFollow)
  const meta = useWalkMeta()

  // Latest props for the map's own event handlers, which are registered once
  // and would otherwise capture the first render's closures forever.
  const handlers = useRef(props)
  handlers.current = props

  // --- lifecycle ------------------------------------------------------------
  useEffect(() => {
    if (!container.current) return
    const m = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE,
      center: [121.5654, 25.033], // Taipei; replaced the moment anything is drawn
      zoom: 13,
      attributionControl: { compact: true },
    })
    map.current = m
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")

    m.on("load", () => {
      for (const id of ["route", "draft-route", "trail", "waypoints", "live"]) {
        m.addSource(id, { type: "geojson", data: EMPTY })
      }
      m.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        paint: { "line-color": "#2563eb", "line-width": 5, "line-opacity": 0.85 },
      })
      m.addLayer({
        id: "draft-route-line",
        type: "line",
        source: "draft-route",
        paint: { "line-color": "#7c3aed", "line-width": 4, "line-dasharray": [2, 1] },
      })
      m.addLayer({
        id: "trail-line",
        type: "line",
        source: "trail",
        paint: { "line-color": "#f97316", "line-width": 3, "line-opacity": 0.6 },
      })
      m.addLayer({
        id: "waypoint-dots",
        type: "circle",
        source: "waypoints",
        paint: {
          "circle-radius": 7,
          "circle-color": "#ffffff",
          "circle-stroke-color": "#7c3aed",
          "circle-stroke-width": 3,
        },
      })
      m.addLayer({
        id: "live-dot",
        type: "circle",
        source: "live",
        paint: {
          "circle-radius": 8,
          "circle-color": "#16a34a",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 3,
        },
      })
      setReady(true)
    })

    // `dragstart`/`zoomstart` with originalEvent set means a human did it; our
    // own easeTo has no originalEvent, so following never cancels itself.
    const detach = (event: { originalEvent?: unknown }) => {
      if (event.originalEvent) follow.current = onUserPan(follow.current)
    }
    m.on("dragstart", detach)
    m.on("zoomstart", detach)

    m.on("click", (event) => {
      if (!handlers.current.editing) return
      const hits = m.queryRenderedFeatures(event.point, { layers: ["waypoint-dots"] })
      const hit = hits[0]
      if (hit) {
        handlers.current.onWaypointClick(Number(hit.properties?.index ?? 0))
        return
      }
      handlers.current.onMapClick(fromLngLat(event.lngLat))
    })

    // Drag a waypoint: grab on mousedown over a dot, move with the pointer,
    // release to commit. Map panning is suppressed for the duration.
    let dragging: number | null = null
    m.on("mousedown", "waypoint-dots", (event) => {
      if (!handlers.current.editing) return
      event.preventDefault()
      dragging = Number(event.features?.[0]?.properties?.index ?? 0)
      m.getCanvas().style.cursor = "grabbing"
    })
    m.on("mousemove", (event) => {
      if (dragging === null) return
      handlers.current.onWaypointDrag(dragging, fromLngLat(event.lngLat))
    })
    const endDrag = () => {
      if (dragging === null) return
      dragging = null
      m.getCanvas().style.cursor = ""
    }
    m.on("mouseup", endDrag)
    // A release outside the canvas -- over the sidebar, past the window edge --
    // never reaches the map, and a window blur mid-drag never produces a
    // mouseup at all. Without these the waypoint keeps following the cursor
    // with no button held.
    window.addEventListener("mouseup", endDrag)
    window.addEventListener("blur", endDrag)

    return () => {
      window.removeEventListener("mouseup", endDrag)
      window.removeEventListener("blur", endDrag)
      m.remove()
      map.current = null
      setReady(false)
    }
  }, [])

  // --- the live dot: imperative, no React render per fix ---------------------
  useEffect(() => {
    if (!ready) return
    const m = map.current
    if (!m) return

    const draw = () => {
      const model = walkStore.getModel()
      const source = m.getSource("live") as maplibregl.GeoJSONSource | undefined
      const trail = m.getSource("trail") as maplibregl.GeoJSONSource | undefined
      if (!model.fix) {
        source?.setData(EMPTY)
        trail?.setData(EMPTY)
        return
      }
      const here: LatLon = [model.fix.lat, model.fix.lon]
      source?.setData(pointsOf([here]))
      trail?.setData(lineOf(model.trail.map((f): LatLon => [f.lat, f.lon])))
      if (shouldCenter(follow.current, true)) {
        m.easeTo({ center: toLngLat(here), duration: 400 })
      }
    }

    draw() // catch up with whatever the snapshot already delivered
    return walkStore.subscribeFix(draw)
  }, [ready])

  // --- committed route (from the store's meta channel) ----------------------
  useEffect(() => {
    if (!ready) return
    const source = map.current?.getSource("route") as maplibregl.GeoJSONSource | undefined
    source?.setData(lineOf(meta.route))
    if (meta.route.length >= 2) fitTo(map.current, meta.route)
  }, [ready, meta.route])

  // --- draft route + waypoints (from the editor) ----------------------------
  useEffect(() => {
    if (!ready) return
    const m = map.current
    ;(m?.getSource("draft-route") as maplibregl.GeoJSONSource | undefined)?.setData(
      lineOf(props.draftRoute),
    )
    ;(m?.getSource("waypoints") as maplibregl.GeoJSONSource | undefined)?.setData(
      pointsOf(props.draftWaypoints),
    )
  }, [ready, props.draftRoute, props.draftWaypoints])

  return (
    <div className="relative h-full w-full">
      <div ref={container} className="h-full w-full" />
      <CoordBox />
      <Button
        variant="secondary"
        size="icon"
        className="absolute right-3 top-20 shadow-md"
        aria-label="Recenter on the live position"
        onClick={() => {
          follow.current = onRecenter(follow.current)
          const model = walkStore.getModel()
          if (model.fix) {
            map.current?.easeTo({ center: toLngLat([model.fix.lat, model.fix.lon]), duration: 400 })
          }
        }}
      >
        <Crosshair className="size-4" />
      </Button>
    </div>
  )
}

function fitTo(m: maplibregl.Map | null, points: LatLon[]): void {
  if (!m || points.length === 0) return
  const bounds = new maplibregl.LngLatBounds(toLngLat(points[0]), toLngLat(points[0]))
  for (const p of points) bounds.extend(toLngLat(p))
  m.fitBounds(bounds, { padding: 80, duration: 0, maxZoom: 16 })
}
