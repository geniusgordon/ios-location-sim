import { useCallback, useEffect, useRef, useState } from "react"
import type { LatLon, Preset } from "@/api/types"
import { errorText, getPresets, pinLocation } from "@/api/client"
import Dock from "@/components/Dock"
import MapView from "@/components/MapView"
import RouteLibrary from "@/components/RouteLibrary"
import { useRoutePreview } from "@/hooks/useRoutePreview"
import { useWalkStream, useWalkMeta } from "@/hooks/useWalkStream"
import {
  addWaypoint,
  clearRoute,
  defaultSettings,
  emptyRoute,
  loadPreset,
  moveWaypoint,
  removeLast,
  removeWaypoint,
  type DraftRoute,
  type DraftSettings,
} from "@/lib/draft"
import { isRunning } from "@/state/walkReducer"

export default function App() {
  useWalkStream()

  const [libraryOpen, setLibraryOpen] = useState(false)
  const [presets, setPresets] = useState<Preset[]>([])
  const [profiles, setProfiles] = useState<string[]>([])
  const [offline, setOffline] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [route, setRoute] = useState<DraftRoute>(emptyRoute)
  const [settings, setSettings] = useState<DraftSettings>(defaultSettings)
  const [pinArmed, setPinArmed] = useState(false)
  const [pinError, setPinError] = useState<string | null>(null)

  // Only the newest load may write state. Two overlapping fetches (StrictMode
  // double-invokes the mount effect in dev) would otherwise let whichever
  // RESOLVES last win, stranding a stale error beside freshly loaded presets.
  const loadId = useRef(0)

  const reloadPresets = useCallback(() => {
    const mine = ++loadId.current
    setLoading(true)
    setLoadError(null)
    getPresets()
      .then((data) => {
        if (mine !== loadId.current) return
        setPresets(data.presets)
        setProfiles(data.profiles)
        setOffline(data.offline)
      })
      .catch((error: unknown) => {
        if (mine !== loadId.current) return
        setLoadError(errorText(error))
      })
      .finally(() => {
        if (mine === loadId.current) setLoading(false)
      })
  }, [])

  useEffect(() => {
    reloadPresets()
  }, [reloadPresets])

  const meta = useWalkMeta()
  // Map-first: editable whenever no walk holds the device, library open or not.
  const editing = !isRunning(meta.state)

  // One debounced, server-cached Valhalla call, gated on the device being free
  // so a map-first route draws as a line rather than disconnected dots.
  const preview = useRoutePreview(route.waypoints, settings.costing, !offline && editing)

  const onMapClick = (point: LatLon) => {
    if (pinArmed) {
      setPinArmed(false)
      setPinError(null)
      // A 409 (walk already running) never broadcasts a state message, and
      // even a broadcast failure lands in `meta.error`, which only renders
      // inside LiveDock -- invisible while the dock is showing the route
      // editor. Surface the server's own text here instead.
      void pinLocation(point[0], point[1]).catch((error: unknown) => {
        setPinError(errorText(error))
      })
      return
    }
    setPinError(null)
    setRoute((r) => addWaypoint(r, point))
  }

  return (
    <div className="flex h-full w-full flex-col">
      <div className="min-h-0 flex-1">
        <MapView
          draftWaypoints={route.waypoints}
          draftRoute={preview.route}
          editing={editing}
          onMapClick={onMapClick}
          onWaypointDrag={(index, point) => setRoute((r) => moveWaypoint(r, index, point))}
          onWaypointClick={(index) => setRoute((r) => removeWaypoint(r, index))}
        />
      </div>
      <Dock
        route={route}
        settings={settings}
        onSettingsChange={setSettings}
        lengthM={preview.lengthM}
        routePending={preview.pending}
        routeError={preview.error}
        loadError={loadError}
        profiles={profiles}
        offline={offline}
        pinArmed={pinArmed}
        onPinArmedChange={setPinArmed}
        pinError={pinError}
        onRemoveLast={() => setRoute((r) => removeLast(r))}
        onClear={() => setRoute(clearRoute())}
        onOpenLibrary={() => setLibraryOpen(true)}
        onSaved={(name) => {
          setRoute((r) => ({ ...r, name }))
          reloadPresets()
        }}
        onStarted={() => setLibraryOpen(false)}
      />
      <RouteLibrary
        open={libraryOpen}
        onOpenChange={setLibraryOpen}
        presets={presets}
        selectedName={route.name}
        loading={loading}
        loadError={loadError}
        onReload={reloadPresets}
        onSelect={(preset) => {
          const next = loadPreset(preset, settings)
          setRoute(next.route)
          setSettings(next.settings)
          setLibraryOpen(false)
        }}
      />
    </div>
  )
}
