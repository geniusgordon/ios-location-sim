import { useCallback, useEffect, useRef, useState } from "react"
import { PanelLeftOpen } from "lucide-react"
import type { LatLon, Place, Preset } from "@/api/types"
import { deletePlace, deletePreset, errorText, getPlaces, getPresets, pinLocation, stopWalk } from "@/api/client"
import MapView from "@/components/MapView"
import Sidebar, { type SidebarTab } from "@/components/Sidebar"
import { Button } from "@/components/ui/button"
import { useDeviceStatus } from "@/hooks/useDeviceStatus"
import { useIsMobile } from "@/hooks/use-mobile"
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
import { canStop, isRunning, showsLiveDock } from "@/state/walkReducer"

export default function App() {
  useWalkStream()
  const isMobile = useIsMobile()

  const [tab, setTab] = useState<SidebarTab>("location")
  // Open by default; collapsible. On mobile the sidebar overlays the map.
  const [sidebarOpen, setSidebarOpen] = useState(true)

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
  }, [])

  // Keeps a finished/lost run's summary on screen after the walk panel would
  // otherwise fall back to the editor (the waypoints are still there).
  // Dismissed by anything that means the user has moved on.
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
        // A places failure is not worth blanking the panel: /api/presets
        // already surfaces a broken config, and this call reads the same file.
      })
      .finally(() => setPlacesLoading(false))
  }, [])

  useEffect(() => {
    reloadPlaces()
  }, [reloadPlaces])

  const meta = useWalkMeta()
  // Map-first: editable whenever no walk holds the device.
  const editing = !isRunning(meta.state)

  // A running walk (or a finished/lost run whose summary is still up) belongs on
  // the Walk tab -- that is where the live view and Stop button live. Force it
  // so the live view is never hidden behind the Set-location tab.
  useEffect(() => {
    if (showsLiveDock(meta.state, showSummary)) setTab("walk")
  }, [meta.state, showSummary])

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

  // Selecting a saved thing on mobile collapses the overlay so the result is
  // visible on the map behind it; on desktop the inline sidebar leaves the map
  // uncovered, so there is nothing to collapse.
  const revealMap = useCallback(() => {
    if (isMobile) setSidebarOpen(false)
  }, [isMobile])

  const onMapClick = (point: LatLon) => {
    if (tab === "location") {
      // Stay on the tab: setting several locations in a row is the point.
      setShowSummary(false)
      setPinError(null)
      handlePinned(point) // pick: marker + fills save form (already on screen, no recenter)
      if (indicator.connected) {
        void pinLocation(point[0], point[1]).catch((error: unknown) => setPinError(errorText(error)))
      }
      return
    }
    setPinError(null)
    setShowSummary(false)
    setRoute((r) => addWaypoint(r, point))
  }

  return (
    <div className="flex h-full w-full">
      {sidebarOpen ? (
        <Sidebar
          tab={tab}
          onTabChange={setTab}
          onCollapse={() => setSidebarOpen(false)}
          overlay={isMobile}
          deviceIndicator={indicator}
          locationDisabled={isRunning(meta.state)}
          deviceConnected={indicator.connected}
          lastPin={lastPin}
          onPinned={handlePinned}
          onPlaceSaved={reloadPlaces}
          held={meta.state === "pinned"}
          onClearPin={handleClear}
          pinError={pinError}
          places={places}
          placesLoading={placesLoading}
          onSelectPlace={(place) => {
            const point: LatLon = [place.point[0], place.point[1]]
            setPinError(null)
            handlePinned(point, { recenter: true })
            if (indicator.connected) {
              void pinLocation(point[0], point[1]).catch((error: unknown) => setPinError(errorText(error)))
            }
            revealMap()
          }}
          onDeletePlace={async (name) => {
            await deletePlace(name)
            reloadPlaces()
          }}
          route={route}
          settings={settings}
          onSettingsChange={setSettings}
          lengthM={preview.lengthM}
          routePending={preview.pending}
          routeError={preview.error}
          loadError={loadError}
          profiles={profiles}
          offline={offline}
          onRemoveLast={() => {
            setShowSummary(false)
            setRoute((r) => removeLast(r))
          }}
          onClear={() => {
            setShowSummary(false)
            setRoute(clearRoute())
          }}
          onSaved={(name) => {
            setRoute((r) => ({ ...r, name }))
            reloadPresets()
          }}
          onStarted={() => {
            setShowSummary(false)
          }}
          showSummary={showSummary}
          presets={presets}
          loading={loading}
          onReloadPresets={reloadPresets}
          onSelectPreset={(preset) => {
            const next = loadPreset(preset, settings)
            setShowSummary(false)
            setRoute(next.route)
            setSettings(next.settings)
            revealMap()
          }}
          onDeletePreset={async (name) => {
            await deletePreset(name)
            // Deleting the loaded route drops its name but keeps its geometry:
            // starting by a name that no longer exists would 404 instead of
            // walking. Same rule every edit already follows.
            setRoute((r) => (r.name === name ? { ...r, name: null } : r))
            reloadPresets()
          }}
        />
      ) : null}

      <div className="relative min-h-0 flex-1">
        <MapView
          draftWaypoints={route.waypoints}
          draftRoute={preview.route}
          editing={editing}
          mode={tab === "location" ? "location" : "route"}
          centerOn={centerOn}
          pickedPoint={canStop(meta.state) ? null : lastPin}
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
        {!sidebarOpen ? (
          <Button
            variant="secondary"
            size="icon"
            className="absolute left-3 top-3 z-10 shadow-md"
            aria-label="Open sidebar"
            onClick={() => setSidebarOpen(true)}
          >
            <PanelLeftOpen className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  )
}
