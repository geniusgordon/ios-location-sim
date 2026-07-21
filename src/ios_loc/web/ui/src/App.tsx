import { useCallback, useEffect, useRef, useState } from "react"
import type { LatLon, Preset } from "@/api/types"
import { ApiError, getPresets } from "@/api/client"
import MapView from "@/components/MapView"
import Sidebar, { type SidebarMode } from "@/components/Sidebar"
import StatusBar from "@/components/StatusBar"
import { useRoutePreview } from "@/hooks/useRoutePreview"
import { useWalkStream } from "@/hooks/useWalkStream"

export default function App() {
  useWalkStream()

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mode, setMode] = useState<SidebarMode>("presets")

  const [presets, setPresets] = useState<Preset[]>([])
  const [profiles, setProfiles] = useState<string[]>([])
  const [offline, setOffline] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [draftWaypoints, setDraftWaypoints] = useState<LatLon[]>([])

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
        setLoadError(error instanceof ApiError ? error.detail : String(error))
      })
      .finally(() => {
        if (mine === loadId.current) setLoading(false)
      })
  }, [])

  useEffect(() => {
    reloadPresets()
  }, [reloadPresets])

  const editing = mode === "editor" && sidebarOpen

  const [costing, setCosting] = useState("pedestrian")
  const preview = useRoutePreview(draftWaypoints, costing, editing && !offline)

  return (
    <div className="flex h-full w-full flex-col">
      <div className="min-h-0 flex-1">
        <MapView
          draftWaypoints={draftWaypoints}
          draftRoute={preview.route}
          editing={editing}
          onMapClick={(point) => setDraftWaypoints((w) => [...w, point])}
          onWaypointDrag={(index, point) =>
            setDraftWaypoints((w) => w.map((p, i) => (i === index ? point : p)))
          }
          onWaypointClick={(index) => setDraftWaypoints((w) => w.filter((_, i) => i !== index))}
        />
      </div>
      <StatusBar onOpenSidebar={() => setSidebarOpen(true)} />
      <Sidebar
        open={sidebarOpen}
        onOpenChange={setSidebarOpen}
        mode={mode}
        onModeChange={setMode}
        presets={presets}
        profiles={profiles}
        offline={offline}
        loading={loading}
        loadError={loadError}
        onReloadPresets={reloadPresets}
        selectedPreset={selectedPreset}
        onSelectPreset={(preset) => {
          setSelectedPreset(preset.name)
          setDraftWaypoints(preset.waypoints as LatLon[])
          setMode("start")
        }}
        draftWaypoints={draftWaypoints}
        onClearWaypoints={() => setDraftWaypoints([])}
        onRemoveLast={() => setDraftWaypoints((w) => w.slice(0, -1))}
        route={preview.route}
        lengthM={preview.lengthM}
        routeError={preview.error}
        routePending={preview.pending}
        costing={costing}
        onCostingChange={setCosting}
        onPresetSaved={(name) => {
          setSelectedPreset(name)
          reloadPresets()
          setMode("start")
        }}
      />
    </div>
  )
}
