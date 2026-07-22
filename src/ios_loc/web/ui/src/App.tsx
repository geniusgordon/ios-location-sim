import { useCallback, useEffect, useRef, useState } from "react"
import type { LatLon, Place, Preset } from "@/api/types"
import { deletePlace, deletePreset, errorText, getPlaces, getPresets, pinLocation, stopWalk } from "@/api/client"
import Dock from "@/components/Dock"
import MapView from "@/components/MapView"
import RouteLibrary from "@/components/RouteLibrary"
import { useDeviceStatus } from "@/hooks/useDeviceStatus"
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
import { deviceIndicator } from "@/lib/deviceIndicator"
import { canStop, isRunning } from "@/state/walkReducer"

export default function App() {
  useWalkStream()

  const [libraryOpen, setLibraryOpen] = useState(false)
  const [presets, setPresets] = useState<Preset[]>([])
  const [places, setPlaces] = useState<Place[]>([])
  // The last point the device was pinned at, from either pin path. Gates the
  // "save this place" form: there is never a save button with nothing to save.
  const [lastPin, setLastPin] = useState<LatLon | null>(null)
  const [profiles, setProfiles] = useState<string[]>([])
  const [offline, setOffline] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [route, setRoute] = useState<DraftRoute>(emptyRoute)
  const [settings, setSettings] = useState<DraftSettings>(defaultSettings)
  const [pinArmed, setPinArmed] = useState(false)
  const [pinError, setPinError] = useState<string | null>(null)
  const [placesLoading, setPlacesLoading] = useState(true)
  // Bumped on every typed/place set so MapView eases to the new point. A ref,
  // not state: only its value-at-set-time matters, paired into `centerOn`.
  const centerNonce = useRef(0)
  const [centerOn, setCenterOn] = useState<{ point: LatLon; nonce: number } | null>(null)

  const recenterTo = useCallback((point: LatLon) => {
    centerNonce.current += 1
    setCenterOn({ point, nonce: centerNonce.current })
  }, [])

  // The set-location paths funnel through here. `recenter` is set for typed and
  // saved-place sets (which may be off-screen) and omitted for a map tap.
  const handlePinned = useCallback(
    (point: LatLon, opts?: { recenter?: boolean }) => {
      setLastPin(point)
      if (opts?.recenter) recenterTo(point)
    },
    [recenterTo],
  )

  const handleClear = useCallback(async () => {
    await stopWalk()
    setLastPin(null)
    setPinArmed(false)
  }, [])
  // Keeps a finished/lost run's summary on screen after the dock would
  // otherwise fall back to the drawing branch (the waypoints are still
  // there). Dismissed by anything that means the user has moved on: editing
  // the route, loading a saved one, or starting a new walk.
  const [showSummary, setShowSummary] = useState(false)

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

  const reloadPlaces = useCallback(() => {
    setPlacesLoading(true)
    getPlaces()
      .then((data) => setPlaces(data.places))
      .catch(() => {
        // A places failure is not worth blanking the sheet: /api/presets
        // already surfaces a broken config, and this call reads the same file.
      })
      .finally(() => setPlacesLoading(false))
  }, [])

  useEffect(() => {
    reloadPlaces()
  }, [reloadPlaces])

  // Re-read places whenever the library opens so a save from a prior open is
  // reflected -- and so an early first open cannot show a stale empty list.
  useEffect(() => {
    if (libraryOpen) reloadPlaces()
  }, [libraryOpen, reloadPlaces])

  const meta = useWalkMeta()
  // Map-first: editable whenever no walk holds the device, library open or not.
  const editing = !isRunning(meta.state)

  // Paused while the service already holds the device: the walk state is the
  // truth then, and a probe would open a second tunnel.
  const deviceStatus = useDeviceStatus(canStop(meta.state))
  const indicator = deviceIndicator(meta.state, deviceStatus)

  // A finished run or a lost device is the most useful thing on screen until
  // the user does something that means they've moved past it.
  useEffect(() => {
    if (meta.state === "finished" || meta.state === "error") setShowSummary(true)
  }, [meta.state])

  // One debounced, server-cached Valhalla call, gated on the device being free
  // so a map-first route draws as a line rather than disconnected dots.
  const preview = useRoutePreview(route.waypoints, settings.costing, !offline && editing)

  const onMapClick = (point: LatLon) => {
    if (pinArmed) {
      // Stay armed: setting several locations in a row is the whole point.
      setPinError(null)
      setShowSummary(false)
      void pinLocation(point[0], point[1])
        .then(() => handlePinned(point))
        .catch((error: unknown) => {
          setPinError(errorText(error))
        })
      return
    }
    setPinError(null)
    setShowSummary(false)
    setRoute((r) => addWaypoint(r, point))
  }

  return (
    <div className="flex h-full w-full flex-col">
      <div className="min-h-0 flex-1">
        <MapView
          draftWaypoints={route.waypoints}
          draftRoute={preview.route}
          editing={editing}
          centerOn={centerOn}
          onMapClick={onMapClick}
          onWaypointDrag={(index, point) => {
            setShowSummary(false)
            setRoute((r) => moveWaypoint(r, index, point))
          }}
          onWaypointClick={(index) => {
            setShowSummary(false)
            setRoute((r) => removeWaypoint(r, index))
          }}
        />
      </div>
      <Dock
        deviceIndicator={indicator}
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
        lastPin={lastPin}
        held={meta.state === "pinned"}
        onPinned={handlePinned}
        onClearPin={handleClear}
        onPlaceSaved={reloadPlaces}
        showSummary={showSummary}
        onRemoveLast={() => {
          setShowSummary(false)
          setRoute((r) => removeLast(r))
        }}
        onClear={() => {
          setShowSummary(false)
          setRoute(clearRoute())
        }}
        onOpenLibrary={() => setLibraryOpen(true)}
        onSaved={(name) => {
          setRoute((r) => ({ ...r, name }))
          reloadPresets()
        }}
        onStarted={() => {
          setShowSummary(false)
          setLibraryOpen(false)
        }}
      />
      <RouteLibrary
        open={libraryOpen}
        onOpenChange={setLibraryOpen}
        presets={presets}
        places={places}
        placesLoading={placesLoading}
        selectedName={route.name}
        loading={loading}
        loadError={loadError}
        onReload={reloadPresets}
        onSelect={(preset) => {
          const next = loadPreset(preset, settings)
          setShowSummary(false)
          setRoute(next.route)
          setSettings(next.settings)
          setLibraryOpen(false)
        }}
        onSelectPlace={(place) => {
          const point: LatLon = [place.point[0], place.point[1]]
          setPinArmed(false)
          setPinError(null)
          setLibraryOpen(false)
          void pinLocation(point[0], point[1])
            .then(() => handlePinned(point, { recenter: true }))
            .catch((error: unknown) => {
              setPinError(errorText(error))
            })
        }}
        onDeletePreset={async (name) => {
          await deletePreset(name)
          // Deleting the loaded route drops its name but keeps its geometry:
          // starting by a name that no longer exists would 404 instead of
          // walking. Same rule every edit already follows.
          setRoute((r) => (r.name === name ? { ...r, name: null } : r))
          reloadPresets()
        }}
        onDeletePlace={async (name) => {
          await deletePlace(name)
          reloadPlaces()
        }}
      />
    </div>
  )
}
